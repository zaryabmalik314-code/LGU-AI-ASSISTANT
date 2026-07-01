"""
PolicyDraft — stores detected diffs between scraped admission policy data
and the current live admission_rules rows.

State machine:
  pending  →  approved  (admin reviews and approves → new AdmissionRule row inserted)
  pending  →  rejected  (admin dismisses as false positive / irrelevant change)
  approved →  (terminal)
  rejected →  (terminal)

Key invariant: this table is APPEND-ONLY for the scraper. Only the approval
service writes to status/reviewed_at/reviewed_by. The scraper only inserts.
"""
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, func
from app.db.session import Base


class PolicyDraft(Base):
    __tablename__ = "policy_drafts"

    id = Column(Integer, primary_key=True)

    # Which program and source this diff concerns
    program_id = Column(Integer, nullable=True)     # null = new/unknown program
    source_url = Column(String, nullable=False)

    # What the scraper saw
    scraped_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    scraped_data = Column(JSON, nullable=False)      # raw normalised dict from scraper

    # Human-readable diff against current live rule (if one exists)
    diff_summary = Column(Text, nullable=False)      # e.g. "min_inter_pct changed 60→65"
    diff_detail = Column(JSON, nullable=False)       # {"field": "min_inter_pct", "old": 60, "new": 65}

    # Review state
    status = Column(String, nullable=False, default="pending")  # pending | approved | rejected
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String, nullable=True)
    review_note = Column(Text, nullable=True)        # optional note from reviewer

    # If approved, points to the AdmissionRule row that was created
    created_rule_id = Column(Integer, nullable=True)
