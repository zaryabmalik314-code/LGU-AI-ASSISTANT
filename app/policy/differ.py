"""
Policy Differ — Phase 7.

Compares a ScrapedRule (fresh from the web) against the current live
AdmissionRule in the DB for the same program.

Returns a DiffResult which is either:
  - no_change  : scraped data matches live rule within tolerance → no action
  - changed    : specific fields differ → insert a PolicyDraft for review
  - new_program: program_id is None or has no active rule → flag for review

Design principles:
  - Pure function: diff_rule() takes data structs, not DB sessions.
    The scheduler/service wires persistence.  Easy to unit test.
  - Float comparison uses a tolerance (FLOAT_TOLERANCE) to avoid
    noise from parsing imprecision (e.g. 60.0 vs 60.00001).
  - Missing fields on the scraped side are NOT treated as a change —
    the scraper couldn't find the value, which is a parse failure,
    not a policy change.  Only present-and-different fields trigger diffs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.policy.scraper import ScrapedRule

logger = logging.getLogger(__name__)

FLOAT_TOLERANCE = 0.5   # percentage points — treat diff < this as noise


# ---------------------------------------------------------------------------
# Input: current live rule snapshot (decoupled from ORM)
# ---------------------------------------------------------------------------

@dataclass
class LiveRuleSnapshot:
    """
    Mirror of AdmissionRule fields needed for diffing.
    Decoupled from ORM so differ stays pure/testable.
    """
    rule_id: int
    program_id: int
    allowed_streams: list[str]
    min_matric_pct: float
    min_inter_pct: float
    required_subjects: list[str]
    source_url: Optional[str]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass
class FieldDiff:
    field: str
    old_value: object
    new_value: object

    def human_summary(self) -> str:
        return f"{self.field}: {self.old_value!r} → {self.new_value!r}"


@dataclass
class DiffResult:
    kind: str                           # "no_change" | "changed" | "new_program"
    scraped: ScrapedRule
    live: Optional[LiveRuleSnapshot]    # None for new_program
    field_diffs: list[FieldDiff] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return self.kind != "no_change"

    @property
    def diff_summary(self) -> str:
        if self.kind == "new_program":
            return f"New program detected: {self.scraped.program_name} (no live rule found)"
        if not self.field_diffs:
            return "No changes"
        return "; ".join(d.human_summary() for d in self.field_diffs)

    @property
    def diff_detail(self) -> list[dict]:
        return [
            {"field": d.field, "old": d.old_value, "new": d.new_value}
            for d in self.field_diffs
        ]


# ---------------------------------------------------------------------------
# Core diff logic
# ---------------------------------------------------------------------------

def _floats_differ(a: float, b: float) -> bool:
    return abs(a - b) > FLOAT_TOLERANCE


def _lists_differ(a: list[str], b: list[str]) -> bool:
    return set(a) != set(b)


def diff_rule(scraped: ScrapedRule, live: Optional[LiveRuleSnapshot]) -> DiffResult:
    """
    Compare one ScrapedRule against the current live rule.

    Rules:
      1. If live is None → kind="new_program" (no comparison possible).
      2. Only compare fields where the scraper actually found a value
         (None scraped field = parse failure, not a detected change).
      3. Float fields use FLOAT_TOLERANCE to suppress noise.
      4. List fields compare as sets (order-independent).
    """
    if live is None:
        return DiffResult(kind="new_program", scraped=scraped, live=None)

    diffs: list[FieldDiff] = []

    # --- min_matric_pct ---
    if scraped.min_matric_pct is not None:
        if _floats_differ(scraped.min_matric_pct, live.min_matric_pct):
            diffs.append(FieldDiff(
                field="min_matric_pct",
                old_value=live.min_matric_pct,
                new_value=scraped.min_matric_pct,
            ))

    # --- min_inter_pct ---
    if scraped.min_inter_pct is not None:
        if _floats_differ(scraped.min_inter_pct, live.min_inter_pct):
            diffs.append(FieldDiff(
                field="min_inter_pct",
                old_value=live.min_inter_pct,
                new_value=scraped.min_inter_pct,
            ))

    # --- allowed_streams ---
    if scraped.allowed_streams:
        if _lists_differ(scraped.allowed_streams, live.allowed_streams):
            diffs.append(FieldDiff(
                field="allowed_streams",
                old_value=sorted(live.allowed_streams),
                new_value=sorted(scraped.allowed_streams),
            ))

    # --- required_subjects ---
    if scraped.required_subjects:
        if _lists_differ(scraped.required_subjects, live.required_subjects):
            diffs.append(FieldDiff(
                field="required_subjects",
                old_value=sorted(live.required_subjects),
                new_value=sorted(scraped.required_subjects),
            ))

    if diffs:
        return DiffResult(kind="changed", scraped=scraped, live=live, field_diffs=diffs)

    return DiffResult(kind="no_change", scraped=scraped, live=live)


# ---------------------------------------------------------------------------
# Batch differ (used by scheduler)
# ---------------------------------------------------------------------------

def diff_all(
    scraped_rules: list[ScrapedRule],
    live_rules_by_program: dict[int, LiveRuleSnapshot],
) -> list[DiffResult]:
    """
    Diff a batch of scraped rules against a lookup of live rules.
    Returns only results that have_changes (no_change results are discarded).
    """
    results: list[DiffResult] = []

    for scraped in scraped_rules:
        live = live_rules_by_program.get(scraped.program_id) if scraped.program_id else None
        result = diff_rule(scraped, live)

        if result.has_changes:
            logger.info(
                f"Diff detected for program_id={scraped.program_id} "
                f"({scraped.program_name}): {result.diff_summary}"
            )
            results.append(result)
        else:
            logger.debug(f"No change for program_id={scraped.program_id}")

    return results
