"""
Policy Admin Router — Phase 7.

Endpoints:
  GET  /policy/drafts           — list pending drafts for staff review
  GET  /policy/drafts/{id}      — get single draft detail
  POST /policy/run-check        — manually trigger a scrape+diff cycle (staff only)
  PATCH /policy/drafts/{id}/approve  — approve a draft (creates new AdmissionRule)
  PATCH /policy/drafts/{id}/reject   — reject a draft

These endpoints are admin-only by convention — add your auth middleware
(e.g. HTTP Basic, API key header, or JWT) at the app layer.
They are intentionally NOT wired into the student-facing recommendation flow.

No auto-update: approve_draft() is the ONLY path that writes to admission_rules,
requires a human to explicitly hit this endpoint with their name.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.policy import service as policy_service
from app.policy.scheduler import run_policy_check

router = APIRouter(prefix="/policy", tags=["policy-admin"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DraftOut(BaseModel):
    id: int
    program_id: int | None
    source_url: str
    scraped_at: str
    diff_summary: str
    diff_detail: list[dict]
    status: str
    reviewed_at: str | None
    reviewed_by: str | None
    review_note: str | None
    created_rule_id: int | None
    scraped_data: dict

    @classmethod
    def from_orm(cls, d) -> "DraftOut":
        return cls(
            id=d.id,
            program_id=d.program_id,
            source_url=d.source_url,
            scraped_at=d.scraped_at.isoformat() if d.scraped_at else None,
            diff_summary=d.diff_summary,
            diff_detail=d.diff_detail or [],
            status=d.status,
            reviewed_at=d.reviewed_at.isoformat() if d.reviewed_at else None,
            reviewed_by=d.reviewed_by,
            review_note=d.review_note,
            created_rule_id=d.created_rule_id,
            scraped_data=d.scraped_data or {},
        )


class ApproveBody(BaseModel):
    approved_by: str = Field(..., min_length=2, description="Name of approving staff member")
    effective_from: date = Field(..., description="Date the new rule takes effect")
    note: str | None = Field(None, description="Optional approval note")


class RejectBody(BaseModel):
    rejected_by: str = Field(..., min_length=2, description="Name of rejecting staff member")
    note: str | None = Field(None, description="Reason for rejection (recommended)")


class ApproveOut(BaseModel):
    message: str
    new_rule_id: int
    draft_id: int


class RejectOut(BaseModel):
    message: str
    draft_id: int


class RunCheckOut(BaseModel):
    started_at: str
    finished_at: str | None = None
    sources_attempted: int = 0
    sources_parsed: int = 0
    diffs_detected: int = 0
    drafts_created: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/drafts", response_model=list[DraftOut])
def list_drafts(limit: int = 50, db: Session = Depends(get_db)):
    """List pending policy drafts awaiting staff review."""
    drafts = policy_service.list_pending_drafts(db, limit=limit)
    return [DraftOut.from_orm(d) for d in drafts]


@router.get("/drafts/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int, db: Session = Depends(get_db)):
    """Get full detail for a single draft (any status)."""
    draft = policy_service.get_draft(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    return DraftOut.from_orm(draft)


@router.patch("/drafts/{draft_id}/approve", response_model=ApproveOut)
def approve_draft(draft_id: int, body: ApproveBody, db: Session = Depends(get_db)):
    """
    Approve a pending draft.

    This is the ONLY endpoint that writes to admission_rules.
    It closes the current live rule and inserts a new versioned row.
    Requires: approved_by (staff name) and effective_from date.
    """
    try:
        req = policy_service.ApproveRequest(
            approved_by=body.approved_by,
            effective_from=body.effective_from,
            note=body.note,
        )
        new_rule = policy_service.approve_draft(db, draft_id, req)
    except policy_service.PolicyServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return ApproveOut(
        message=f"Draft {draft_id} approved. New AdmissionRule {new_rule.id} is now live.",
        new_rule_id=new_rule.id,
        draft_id=draft_id,
    )


@router.patch("/drafts/{draft_id}/reject", response_model=RejectOut)
def reject_draft(draft_id: int, body: RejectBody, db: Session = Depends(get_db)):
    """Reject a pending draft (no changes to admission_rules)."""
    try:
        policy_service.reject_draft(db, draft_id, body.rejected_by, body.note)
    except policy_service.PolicyServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RejectOut(message=f"Draft {draft_id} rejected.", draft_id=draft_id)


@router.post("/run-check", response_model=RunCheckOut)
def trigger_policy_check(db: Session = Depends(get_db)):
    """
    Manually trigger a full scrape + diff + draft-creation cycle.
    Useful for staff to force a check outside the scheduled window.
    """
    summary = run_policy_check(db=db)
    return RunCheckOut(**{k: summary.get(k) for k in RunCheckOut.model_fields})
