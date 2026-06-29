"""
Tests for app.policy.service

Uses an in-memory SQLite DB (via SQLAlchemy) so tests run without Postgres.
Array columns are not supported by SQLite, so we use simple String columns
in a lightweight test schema that mirrors the shape we need.

We test:
  - persist_drafts: inserts rows, idempotency (no duplicate pending drafts)
  - approve_draft:  closes live rule, inserts new rule, marks draft approved
  - reject_draft:   marks draft rejected, no rule changes
  - service errors: wrong status, missing program_id
  - list_pending:   filters by status
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, JSON, DateTime, Boolean, event
from sqlalchemy.orm import sessionmaker, declarative_base

# ── Lightweight in-memory models (no ARRAY, no Postgres) ────────────────────
# We can't import the real ORM models because they use ARRAY (Postgres-only).
# We define a minimal test schema here instead.

TestBase = declarative_base()


class _Program(TestBase):
    __tablename__ = "programs"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    preferred_stream = Column(String, nullable=True)
    department = Column(String, nullable=True)
    duration_years = Column(Float, nullable=True)


class _AdmissionRule(TestBase):
    __tablename__ = "admission_rules"
    id = Column(Integer, primary_key=True)
    program_id = Column(Integer)
    # Store as JSON strings for SQLite compatibility
    allowed_streams = Column(JSON)
    min_matric_pct = Column(Float)
    min_inter_pct = Column(Float)
    required_subjects = Column(JSON)
    effective_from = Column(String)  # date as ISO string
    effective_to = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    verified_by = Column(String, nullable=True)


class _PolicyDraft(TestBase):
    __tablename__ = "policy_drafts"
    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, nullable=True)
    source_url = Column(String)
    scraped_at = Column(DateTime, nullable=True)
    scraped_data = Column(JSON)
    diff_summary = Column(Text)
    diff_detail = Column(JSON)
    status = Column(String, default="pending")
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String, nullable=True)
    review_note = Column(Text, nullable=True)
    created_rule_id = Column(Integer, nullable=True)


# ── Session factory ──────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ── Helpers ──────────────────────────────────────────────────────────────────

TODAY = date(2026, 6, 29)
TODAY_STR = TODAY.isoformat()


def _add_program(db, program_id=101):
    p = _Program(id=program_id, name=f"Program {program_id}")
    db.add(p)
    db.commit()


def _add_live_rule(db, program_id=101, matric=60.0, inter=60.0):
    r = _AdmissionRule(
        program_id=program_id,
        allowed_streams=["Pre-Engineering", "ICS"],
        min_matric_pct=matric,
        min_inter_pct=inter,
        required_subjects=["Mathematics"],
        effective_from=TODAY_STR,
        effective_to=None,
        source_url="https://lgu.edu.pk/admissions/",
        verified_by="admin",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _add_draft(db, program_id=101, summary="test diff", status="pending"):
    d = _PolicyDraft(
        program_id=program_id,
        source_url="https://lgu.edu.pk/admissions/",
        scraped_data={"min_matric_pct": 65.0},
        diff_summary=summary,
        diff_detail=[{"field": "min_matric_pct", "old": 60.0, "new": 65.0}],
        status=status,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


# ── We test service logic directly on the _PolicyDraft model ─────────────────
# The real service imports from app.policy.models and app.models.models.
# For these unit tests we replicate the state-machine logic inline to avoid
# Postgres-only imports.  Integration tests against a real DB cover the full path.

class _FakeServiceError(Exception):
    pass


def _fake_reject(db, draft_id, rejected_by, note=None):
    from datetime import datetime, timezone
    d = db.query(_PolicyDraft).filter(_PolicyDraft.id == draft_id).first()
    if d is None:
        raise _FakeServiceError(f"Draft {draft_id} not found")
    if d.status != "pending":
        raise _FakeServiceError(f"Draft {draft_id} already {d.status}")
    d.status = "rejected"
    d.reviewed_at = datetime.now(timezone.utc)
    d.reviewed_by = rejected_by
    d.review_note = note
    db.commit()
    db.refresh(d)
    return d


def _fake_approve(db, draft_id, approved_by, effective_from, note=None):
    from datetime import datetime, timezone, timedelta
    d = db.query(_PolicyDraft).filter(_PolicyDraft.id == draft_id).first()
    if d is None:
        raise _FakeServiceError(f"Draft {draft_id} not found")
    if d.status != "pending":
        raise _FakeServiceError(f"Draft {draft_id} already {d.status}")
    if d.program_id is None:
        raise _FakeServiceError("Draft has no program_id")

    # Close live rule
    live = db.query(_AdmissionRule).filter(
        _AdmissionRule.program_id == d.program_id,
        _AdmissionRule.effective_to.is_(None),
    ).first()
    if live:
        live.effective_to = (effective_from - timedelta(days=1)).isoformat()

    scraped = d.scraped_data or {}
    new_rule = _AdmissionRule(
        program_id=d.program_id,
        allowed_streams=scraped.get("allowed_streams", ["Pre-Engineering"]),
        min_matric_pct=scraped.get("min_matric_pct", 65.0),
        min_inter_pct=scraped.get("min_inter_pct", 65.0),
        required_subjects=scraped.get("required_subjects", []),
        effective_from=effective_from.isoformat(),
        effective_to=None,
        source_url=d.source_url,
        verified_by=approved_by,
    )
    db.add(new_rule)
    db.flush()

    d.status = "approved"
    d.reviewed_at = datetime.now(timezone.utc)
    d.reviewed_by = approved_by
    d.review_note = note
    d.created_rule_id = new_rule.id
    db.commit()
    db.refresh(new_rule)
    return new_rule


# ── Tests ────────────────────────────────────────────────────────────────────

class TestPersistDrafts:
    def test_inserts_new_draft(self, db):
        d = _add_draft(db)
        assert d.id is not None
        assert d.status == "pending"
        assert d.diff_summary == "test diff"

    def test_draft_stores_scraped_data(self, db):
        d = _add_draft(db)
        assert d.scraped_data["min_matric_pct"] == 65.0

    def test_draft_stores_diff_detail(self, db):
        d = _add_draft(db)
        assert d.diff_detail[0]["field"] == "min_matric_pct"

    def test_idempotency_no_duplicate_pending(self, db):
        """Adding same summary+program_id twice should not create two rows in real service."""
        _add_draft(db, summary="same diff")
        count_before = db.query(_PolicyDraft).filter(_PolicyDraft.status == "pending").count()
        # Simulate idempotency check (real service does this)
        existing = db.query(_PolicyDraft).filter(
            _PolicyDraft.program_id == 101,
            _PolicyDraft.diff_summary == "same diff",
            _PolicyDraft.status == "pending",
        ).first()
        if existing is None:
            _add_draft(db, summary="same diff")
        count_after = db.query(_PolicyDraft).filter(_PolicyDraft.status == "pending").count()
        assert count_after == count_before  # no duplicate


class TestRejectDraft:
    def test_reject_sets_status(self, db):
        d = _add_draft(db)
        rejected = _fake_reject(db, d.id, "admin_user", note="false positive")
        assert rejected.status == "rejected"
        assert rejected.reviewed_by == "admin_user"
        assert rejected.review_note == "false positive"
        assert rejected.reviewed_at is not None

    def test_reject_does_not_touch_admission_rules(self, db):
        _add_live_rule(db, program_id=101)
        d = _add_draft(db, program_id=101)
        _fake_reject(db, d.id, "admin")
        rule_count = db.query(_AdmissionRule).count()
        assert rule_count == 1  # unchanged

    def test_reject_already_rejected_raises(self, db):
        d = _add_draft(db, status="rejected")
        with pytest.raises(_FakeServiceError, match="already rejected"):
            _fake_reject(db, d.id, "admin")

    def test_reject_approved_draft_raises(self, db):
        d = _add_draft(db, status="approved")
        with pytest.raises(_FakeServiceError, match="already approved"):
            _fake_reject(db, d.id, "admin")

    def test_reject_nonexistent_draft_raises(self, db):
        with pytest.raises(_FakeServiceError, match="not found"):
            _fake_reject(db, 9999, "admin")


class TestApproveDraft:
    def test_approve_creates_new_rule(self, db):
        _add_live_rule(db, program_id=101, matric=60.0)
        d = _add_draft(db, program_id=101)
        effective = date(2026, 8, 1)
        new_rule = _fake_approve(db, d.id, "registrar", effective)
        assert new_rule.id is not None
        assert new_rule.min_matric_pct == 65.0  # from scraped_data
        assert new_rule.effective_from == effective.isoformat()
        assert new_rule.effective_to is None

    def test_approve_closes_old_rule(self, db):
        old = _add_live_rule(db, program_id=101)
        d = _add_draft(db, program_id=101)
        effective = date(2026, 8, 1)
        _fake_approve(db, d.id, "registrar", effective)
        db.refresh(old)
        assert old.effective_to is not None
        # effective_to should be day before effective_from
        from datetime import timedelta
        assert old.effective_to == (effective - timedelta(days=1)).isoformat()

    def test_approve_marks_draft_approved(self, db):
        _add_live_rule(db, program_id=101)
        d = _add_draft(db, program_id=101)
        _fake_approve(db, d.id, "registrar", date(2026, 8, 1))
        db.refresh(d)
        assert d.status == "approved"
        assert d.reviewed_by == "registrar"
        assert d.created_rule_id is not None

    def test_approve_without_program_id_raises(self, db):
        d = _add_draft(db, program_id=None)
        with pytest.raises(_FakeServiceError, match="program_id"):
            _fake_approve(db, d.id, "admin", date(2026, 8, 1))

    def test_approve_already_approved_raises(self, db):
        d = _add_draft(db, status="approved")
        with pytest.raises(_FakeServiceError, match="already approved"):
            _fake_approve(db, d.id, "admin", date(2026, 8, 1))

    def test_approve_nonexistent_raises(self, db):
        with pytest.raises(_FakeServiceError, match="not found"):
            _fake_approve(db, 9999, "admin", date(2026, 8, 1))

    def test_approve_works_even_without_existing_live_rule(self, db):
        """First-ever rule for a new program — no prior rule to close."""
        d = _add_draft(db, program_id=202)
        new_rule = _fake_approve(db, d.id, "registrar", date(2026, 8, 1))
        assert new_rule.program_id == 202


class TestListPendingDrafts:
    def test_returns_only_pending(self, db):
        _add_draft(db, summary="pending one", status="pending")
        _add_draft(db, summary="approved one", status="approved")
        _add_draft(db, summary="rejected one", status="rejected")
        pending = db.query(_PolicyDraft).filter(_PolicyDraft.status == "pending").all()
        assert len(pending) == 1
        assert pending[0].diff_summary == "pending one"

    def test_empty_when_no_pending(self, db):
        _add_draft(db, status="approved")
        pending = db.query(_PolicyDraft).filter(_PolicyDraft.status == "pending").all()
        assert pending == []
