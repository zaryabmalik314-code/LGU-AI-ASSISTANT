from datetime import date
from app.rules.engine import (
    StudentProfile, RuleRow, check_eligibility, filter_eligible_programs, eligible_program_ids
)

CS_RULE = RuleRow(
    id=1, program_id=101, allowed_streams=["Pre-Engineering", "ICS"],
    min_matric_pct=60, min_inter_pct=60, required_subjects=["Mathematics"],
    effective_from=date(2024, 1, 1), effective_to=None,
)

MED_RULE = RuleRow(
    id=2, program_id=102, allowed_streams=["Pre-Medical"],
    min_matric_pct=80, min_inter_pct=80, required_subjects=["Biology"],
    effective_from=date(2024, 1, 1), effective_to=None,
)

EXPIRED_RULE = RuleRow(
    id=3, program_id=103, allowed_streams=["ICS"],
    min_matric_pct=50, min_inter_pct=50, required_subjects=[],
    effective_from=date(2020, 1, 1), effective_to=date(2023, 1, 1),
)


def test_eligible_student_passes():
    s = StudentProfile(matric_pct=75, inter_pct=70, inter_stream="ICS", subjects=["Mathematics", "Physics"])
    r = check_eligibility(s, CS_RULE)
    assert r.eligible
    assert r.reasons_failed == []


def test_wrong_stream_rejected():
    s = StudentProfile(matric_pct=90, inter_pct=90, inter_stream="Pre-Medical", subjects=["Mathematics"])
    r = check_eligibility(s, CS_RULE)
    assert not r.eligible
    assert "stream" in r.reasons_failed[0]


def test_low_percentage_rejected():
    s = StudentProfile(matric_pct=50, inter_pct=55, inter_stream="ICS", subjects=["Mathematics"])
    r = check_eligibility(s, CS_RULE)
    assert not r.eligible


def test_missing_subject_rejected():
    s = StudentProfile(matric_pct=85, inter_pct=85, inter_stream="Pre-Medical", subjects=["Chemistry"])
    r = check_eligibility(s, MED_RULE)
    assert not r.eligible
    assert "Biology" in r.reasons_failed[0]


def test_expired_rule_excluded_from_active_set():
    s = StudentProfile(matric_pct=99, inter_pct=99, inter_stream="ICS", subjects=[])
    results = filter_eligible_programs(s, [CS_RULE, MED_RULE, EXPIRED_RULE], as_of=date(2026, 6, 29))
    ids = [r.program_id for r in results]
    assert 103 not in ids  # expired rule never evaluated


def test_eligible_program_ids_helper():
    s = StudentProfile(matric_pct=90, inter_pct=90, inter_stream="ICS", subjects=["Mathematics"])
    results = filter_eligible_programs(s, [CS_RULE, MED_RULE])
    assert eligible_program_ids(results) == [101]
