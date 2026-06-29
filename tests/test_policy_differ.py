"""
Tests for app.policy.differ

Pure unit tests — no DB, no network.
Covers: no_change, changed (each field), new_program, multi-field diff,
float tolerance, missing scraped fields (parse failures), batch differ.
"""
from datetime import date

import pytest

from app.policy.differ import (
    DiffResult,
    FieldDiff,
    LiveRuleSnapshot,
    FLOAT_TOLERANCE,
    diff_rule,
    diff_all,
)
from app.policy.scraper import ScrapedRule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TODAY = date(2026, 6, 29)


def make_scraped(**overrides) -> ScrapedRule:
    defaults = dict(
        source_url="https://lgu.edu.pk/admissions/",
        program_id=101,
        program_name="BS Computer Science",
        min_matric_pct=60.0,
        min_inter_pct=60.0,
        allowed_streams=["Pre-Engineering", "ICS"],
        required_subjects=["Mathematics"],
        scraped_on=TODAY,
        raw_text="some page text",
        parse_warnings=[],
    )
    defaults.update(overrides)
    return ScrapedRule(**defaults)


def make_live(**overrides) -> LiveRuleSnapshot:
    defaults = dict(
        rule_id=1,
        program_id=101,
        allowed_streams=["Pre-Engineering", "ICS"],
        min_matric_pct=60.0,
        min_inter_pct=60.0,
        required_subjects=["Mathematics"],
        source_url="https://lgu.edu.pk/admissions/",
    )
    defaults.update(overrides)
    return LiveRuleSnapshot(**defaults)


# ---------------------------------------------------------------------------
# no_change
# ---------------------------------------------------------------------------

def test_no_change_when_data_matches():
    result = diff_rule(make_scraped(), make_live())
    assert result.kind == "no_change"
    assert not result.has_changes
    assert result.field_diffs == []


def test_no_change_within_float_tolerance():
    """A difference smaller than FLOAT_TOLERANCE is NOT a change."""
    result = diff_rule(
        make_scraped(min_matric_pct=60.0),
        make_live(min_matric_pct=60.0 + FLOAT_TOLERANCE - 0.01),
    )
    assert result.kind == "no_change"


def test_no_change_when_stream_order_differs():
    """Stream comparison is set-based, order should not matter."""
    result = diff_rule(
        make_scraped(allowed_streams=["ICS", "Pre-Engineering"]),
        make_live(allowed_streams=["Pre-Engineering", "ICS"]),
    )
    assert result.kind == "no_change"


# ---------------------------------------------------------------------------
# new_program
# ---------------------------------------------------------------------------

def test_new_program_when_live_is_none():
    result = diff_rule(make_scraped(program_id=None), live=None)
    assert result.kind == "new_program"
    assert result.has_changes
    assert result.live is None


def test_new_program_diff_summary_contains_program_name():
    result = diff_rule(make_scraped(program_name="BS AI"), live=None)
    assert "BS AI" in result.diff_summary


# ---------------------------------------------------------------------------
# changed — individual fields
# ---------------------------------------------------------------------------

def test_detects_matric_pct_change():
    result = diff_rule(
        make_scraped(min_matric_pct=65.0),
        make_live(min_matric_pct=60.0),
    )
    assert result.kind == "changed"
    assert any(d.field == "min_matric_pct" for d in result.field_diffs)
    field = next(d for d in result.field_diffs if d.field == "min_matric_pct")
    assert field.old_value == 60.0
    assert field.new_value == 65.0


def test_detects_inter_pct_change():
    result = diff_rule(
        make_scraped(min_inter_pct=70.0),
        make_live(min_inter_pct=60.0),
    )
    assert result.kind == "changed"
    assert any(d.field == "min_inter_pct" for d in result.field_diffs)


def test_detects_stream_change():
    result = diff_rule(
        make_scraped(allowed_streams=["Pre-Engineering"]),
        make_live(allowed_streams=["Pre-Engineering", "ICS"]),
    )
    assert result.kind == "changed"
    assert any(d.field == "allowed_streams" for d in result.field_diffs)


def test_detects_subject_change():
    result = diff_rule(
        make_scraped(required_subjects=["Mathematics", "Physics"]),
        make_live(required_subjects=["Mathematics"]),
    )
    assert result.kind == "changed"
    assert any(d.field == "required_subjects" for d in result.field_diffs)


def test_detects_multi_field_change():
    result = diff_rule(
        make_scraped(min_matric_pct=70.0, min_inter_pct=75.0),
        make_live(min_matric_pct=60.0, min_inter_pct=60.0),
    )
    assert result.kind == "changed"
    assert len(result.field_diffs) == 2


# ---------------------------------------------------------------------------
# Parse failure (None scraped fields) — must NOT trigger a change
# ---------------------------------------------------------------------------

def test_none_scraped_matric_not_a_change():
    """Scraper couldn't find matric_pct — should not flag a diff."""
    result = diff_rule(
        make_scraped(min_matric_pct=None),
        make_live(min_matric_pct=60.0),
    )
    assert result.kind == "no_change"


def test_none_scraped_inter_not_a_change():
    result = diff_rule(
        make_scraped(min_inter_pct=None),
        make_live(min_inter_pct=60.0),
    )
    assert result.kind == "no_change"


def test_empty_scraped_streams_not_a_change():
    """Empty list = scraper found no stream keywords = parse failure, not a diff."""
    result = diff_rule(
        make_scraped(allowed_streams=[]),
        make_live(allowed_streams=["Pre-Engineering"]),
    )
    assert result.kind == "no_change"


# ---------------------------------------------------------------------------
# diff_summary / diff_detail shape
# ---------------------------------------------------------------------------

def test_diff_summary_human_readable():
    result = diff_rule(
        make_scraped(min_matric_pct=65.0),
        make_live(min_matric_pct=60.0),
    )
    assert "min_matric_pct" in result.diff_summary
    assert "60" in result.diff_summary
    assert "65" in result.diff_summary


def test_diff_detail_is_list_of_dicts():
    result = diff_rule(
        make_scraped(min_inter_pct=70.0),
        make_live(min_inter_pct=60.0),
    )
    assert isinstance(result.diff_detail, list)
    assert result.diff_detail[0]["field"] == "min_inter_pct"
    assert result.diff_detail[0]["old"] == 60.0
    assert result.diff_detail[0]["new"] == 70.0


# ---------------------------------------------------------------------------
# diff_all (batch)
# ---------------------------------------------------------------------------

def test_diff_all_filters_out_no_change():
    scraped_list = [
        make_scraped(program_id=101),   # matches live
        make_scraped(program_id=102, min_matric_pct=75.0),  # differs
    ]
    live_map = {
        101: make_live(program_id=101, min_matric_pct=60.0, min_inter_pct=60.0),
        102: make_live(program_id=102, min_matric_pct=60.0, min_inter_pct=60.0),
    }
    results = diff_all(scraped_list, live_map)
    assert len(results) == 1
    assert results[0].scraped.program_id == 102


def test_diff_all_treats_missing_program_id_as_new_program():
    scraped_list = [make_scraped(program_id=None)]
    results = diff_all(scraped_list, live_rules_by_program={})
    assert len(results) == 1
    assert results[0].kind == "new_program"


def test_diff_all_empty_input_returns_empty():
    results = diff_all([], {})
    assert results == []
