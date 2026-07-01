"""
Rule Engine — ONLY component allowed to decide eligibility.
Pure, deterministic. No LLM. No fuzzy matching.
"""
from dataclasses import dataclass
from datetime import date
from typing import List


@dataclass
class StudentProfile:
    matric_pct: float
    inter_pct: float
    inter_stream: str          # e.g. "Pre-Engineering"
    subjects: List[str]
    interests: List[str] = None
    career_goals: List[str] = None


@dataclass
class RuleRow:
    """Mirrors AdmissionRule DB row — kept decoupled from ORM so engine stays pure/testable."""
    id: int
    program_id: int
    allowed_streams: List[str]
    min_matric_pct: float
    min_inter_pct: float
    required_subjects: List[str]
    effective_from: date
    effective_to: date | None


@dataclass
class EligibilityResult:
    program_id: int
    rule_id: int
    eligible: bool
    reasons_failed: List[str]   # empty if eligible


def is_rule_active(rule: RuleRow, as_of: date) -> bool:
    if rule.effective_from > as_of:
        return False
    if rule.effective_to is not None and rule.effective_to < as_of:
        return False
    return True


def check_eligibility(student: StudentProfile, rule: RuleRow) -> EligibilityResult:
    fails = []

    if rule.allowed_streams and student.inter_stream not in rule.allowed_streams:
        fails.append(f"stream '{student.inter_stream}' not in allowed {rule.allowed_streams}")

    if student.matric_pct < rule.min_matric_pct:
        fails.append(f"matric {student.matric_pct}% < required {rule.min_matric_pct}%")

    if student.inter_pct < rule.min_inter_pct:
        fails.append(f"inter {student.inter_pct}% < required {rule.min_inter_pct}%")

    missing_subjects = [s for s in rule.required_subjects if s not in student.subjects]
    if missing_subjects:
        fails.append(f"missing required subjects: {missing_subjects}")

    return EligibilityResult(
        program_id=rule.program_id,
        rule_id=rule.id,
        eligible=len(fails) == 0,
        reasons_failed=fails,
    )


def filter_eligible_programs(
    student: StudentProfile,
    active_rules: List[RuleRow],
    as_of: date | None = None,
) -> List[EligibilityResult]:
    """
    Run student against every active rule, return ALL results (eligible + rejected w/ reasons).
    Caller decides what to do with rejected ones (e.g. log for debugging, never shown to LLM).
    """
    as_of = as_of or date.today()
    results = []
    for rule in active_rules:
        if not is_rule_active(rule, as_of):
            continue
        results.append(check_eligibility(student, rule))
    return results


def eligible_program_ids(results: List[EligibilityResult]) -> List[int]:
    return [r.program_id for r in results if r.eligible]
