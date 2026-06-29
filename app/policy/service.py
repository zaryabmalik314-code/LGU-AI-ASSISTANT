"""
Policy Service — Phase 7.

DB-aware layer between the differ (pure) and the API/scheduler (I/O).

Responsibilities:
  1. persist_drafts()   — save DiffResults as PolicyDraft rows (scraper → DB).
  2. approve_draft()    — validate pending draft, close old rule, insert new
                          versioned AdmissionRule, mark draft approved.
  3. reject_draft()     — mark draft rejected with note.
  4. list_pending()     — query pending drafts for the admin review endpoint.
  5. build_live_snapshot_map() — load current active AdmissionRules for differ.

Key invariant: approve_draft() is the ONLY place that writes to admission_rules.
The scraper and differ never touch admission_rules directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import AdmissionRule
from app.policy.models import PolicyDraft
from app.policy.differ import DiffResult, LiveRuleSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot loader (for differ)
# ---------------------------------------------------------------------------

def build_live_snapshot_map(db: Session) -> dict[int, LiveRuleSnapshot]:
    """
    Load all currently active AdmissionRules and return as a program_id → snapshot map.
    Used by the scheduler so the differ doesn't need DB access.
    """
    today = date.today()
    rows = db.query(AdmissionRule).filter(
        AdmissionRule.effective_from <= today,
        (AdmissionRule.effective_to.is_(None)) | (AdmissionRule.effective_to >= today),
    ).all()

    return {
        r.program_id: LiveRuleSnapshot(
            rule_id=r.id,
            program_id=r.program_id,
            allowed_streams=r.allowed_streams or [],
            min_matric_pct=r.min_matric_pct,
            min_inter_pct=r.min_inter_pct,
            required_subjects=r.required_subjects or [],
            source_url=r.source_url,
        )
        for r in rows
    }


# ---------------------------------------------------------------------------
# Persist drafts
# ---------------------------------------------------------------------------

def persist_drafts(db: Session, diff_results: list[DiffResult]) -> list[PolicyDraft]:
    """
    Insert a PolicyDraft row for each DiffResult that has_changes.
    Idempotent per (program_id, diff_summary, status=pending): skips exact
    duplicates that are already pending, so re-runs don't flood the review queue.
    """
    created: list[PolicyDraft] = []

    for result in diff_results:
        if not result.has_changes:
            continue

        summary = result.diff_summary

        # Idempotency check: skip if identical pending draft already exists
        existing = db.query(PolicyDraft).filter(
            PolicyDraft.program_id == result.scraped.program_id,
            PolicyDraft.diff_summary == summary,
            PolicyDraft.status == "pending",
        ).first()

        if existing:
            logger.debug(
                f"Skipping duplicate pending draft for program_id="
                f"{result.scraped.program_id}: {summary}"
            )
            continue

        draft = PolicyDraft(
            program_id=result.scraped.program_id,
            source_url=result.scraped.source_url,
            scraped_data={
                "program_name": result.scraped.program_name,
                "min_matric_pct": result.scraped.min_matric_pct,
                "min_inter_pct": result.scraped.min_inter_pct,
                "allowed_streams": result.scraped.allowed_streams,
                "required_subjects": result.scraped.required_subjects,
                "scraped_on": result.scraped.scraped_on.isoformat(),
                "raw_text_excerpt": result.scraped.raw_text[:500],
                "parse_warnings": result.scraped.parse_warnings,
            },
            diff_summary=summary,
            diff_detail=result.diff_detail,
            status="pending",
        )
        db.add(draft)
        created.append(draft)

    db.commit()
    for d in created:
        db.refresh(d)

    logger.info(f"Persisted {len(created)} new policy drafts")
    return created


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

@dataclass
class ApproveRequest:
    approved_by: str
    effective_from: date
    note: str | None = None


class PolicyServiceError(Exception):
    pass


def approve_draft(db: Session, draft_id: int, req: ApproveRequest) -> AdmissionRule:
    """
    Approve a pending PolicyDraft:
      1. Validate draft exists and is pending.
      2. Validate program_id is set (can't approve new_program drafts without it).
      3. Close the current live rule (set effective_to = req.effective_from - 1 day).
      4. Insert new versioned AdmissionRule from scraped_data.
      5. Mark draft approved with reviewer info and pointer to new rule.

    All DB writes are in a single transaction — either everything commits or nothing.
    """
    draft = db.query(PolicyDraft).filter(PolicyDraft.id == draft_id).first()
    if draft is None:
        raise PolicyServiceError(f"Draft {draft_id} not found")
    if draft.status != "pending":
        raise PolicyServiceError(
            f"Draft {draft_id} is already {draft.status!r} — cannot approve again"
        )
    if draft.program_id is None:
        raise PolicyServiceError(
            f"Draft {draft_id} has no program_id — assign the program first, "
            "then approve. (New-program drafts require manual program creation.)"
        )

    scraped = draft.scraped_data
    today = date.today()

    # Step 3: Close current live rule for this program (if any)
    live_rule = db.query(AdmissionRule).filter(
        AdmissionRule.program_id == draft.program_id,
        AdmissionRule.effective_from <= today,
        (AdmissionRule.effective_to.is_(None)) | (AdmissionRule.effective_to >= today),
    ).first()

    if live_rule:
        from datetime import timedelta
        live_rule.effective_to = req.effective_from - timedelta(days=1)
        logger.info(
            f"Closed rule {live_rule.id} for program {draft.program_id}, "
            f"effective_to set to {live_rule.effective_to}"
        )

    # Step 4: Insert new versioned rule
    new_rule = AdmissionRule(
        program_id=draft.program_id,
        allowed_streams=scraped.get("allowed_streams") or (live_rule.allowed_streams if live_rule else []),
        min_matric_pct=scraped.get("min_matric_pct") or (live_rule.min_matric_pct if live_rule else 0),
        min_inter_pct=scraped.get("min_inter_pct") or (live_rule.min_inter_pct if live_rule else 0),
        required_subjects=scraped.get("required_subjects") or (live_rule.required_subjects if live_rule else []),
        effective_from=req.effective_from,
        effective_to=None,
        source_url=draft.source_url,
        verified_by=req.approved_by,
    )
    db.add(new_rule)
    db.flush()  # get new_rule.id before commit

    # Step 5: Mark draft approved
    draft.status = "approved"
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.reviewed_by = req.approved_by
    draft.review_note = req.note
    draft.created_rule_id = new_rule.id

    db.commit()
    db.refresh(new_rule)

    logger.info(
        f"Draft {draft_id} approved by {req.approved_by}. "
        f"New AdmissionRule id={new_rule.id} for program {draft.program_id}."
    )
    return new_rule


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------

def reject_draft(db: Session, draft_id: int, rejected_by: str, note: str | None = None) -> PolicyDraft:
    """Mark a pending draft as rejected. No admission_rules changes."""
    draft = db.query(PolicyDraft).filter(PolicyDraft.id == draft_id).first()
    if draft is None:
        raise PolicyServiceError(f"Draft {draft_id} not found")
    if draft.status != "pending":
        raise PolicyServiceError(f"Draft {draft_id} is already {draft.status!r}")

    draft.status = "rejected"
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.reviewed_by = rejected_by
    draft.review_note = note

    db.commit()
    db.refresh(draft)
    logger.info(f"Draft {draft_id} rejected by {rejected_by}")
    return draft


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def list_pending_drafts(db: Session, limit: int = 50) -> list[PolicyDraft]:
    return (
        db.query(PolicyDraft)
        .filter(PolicyDraft.status == "pending")
        .order_by(PolicyDraft.scraped_at.desc())
        .limit(limit)
        .all()
    )


def get_draft(db: Session, draft_id: int) -> PolicyDraft | None:
    return db.query(PolicyDraft).filter(PolicyDraft.id == draft_id).first()
