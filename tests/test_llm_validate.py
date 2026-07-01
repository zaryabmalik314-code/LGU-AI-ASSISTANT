import json
import pytest
from app.llm.validate import parse_and_validate, ValidationError

VALID_RESPONSE = json.dumps({
    "explanations": [
        {
            "program_id": 101, "academic_compatibility": "a", "interest_compatibility": "b",
            "career_compatibility": "c", "future_opportunities": "d", "summary": "e",
        },
        {
            "program_id": 102, "academic_compatibility": "a", "interest_compatibility": "b",
            "career_compatibility": "c", "future_opportunities": "d", "summary": "e",
        },
    ]
})


def test_valid_response_parses():
    result = parse_and_validate(VALID_RESPONSE, expected_program_ids_in_order=[101, 102])
    assert len(result) == 2
    assert result[0].program_id == 101


def test_markdown_fence_stripped():
    fenced = "```json\n" + VALID_RESPONSE + "\n```"
    result = parse_and_validate(fenced, expected_program_ids_in_order=[101, 102])
    assert len(result) == 2


def test_invalid_json_rejected():
    with pytest.raises(ValidationError):
        parse_and_validate("not json at all", expected_program_ids_in_order=[101])


def test_invented_program_rejected():
    """Critical: LLM adds a program not in the eligible list -> must reject."""
    bad = json.dumps({
        "explanations": [
            {"program_id": 101, "academic_compatibility": "a", "interest_compatibility": "b",
             "career_compatibility": "c", "future_opportunities": "d", "summary": "e"},
            {"program_id": 999, "academic_compatibility": "a", "interest_compatibility": "b",
             "career_compatibility": "c", "future_opportunities": "d", "summary": "e"},
        ]
    })
    with pytest.raises(ValidationError):
        parse_and_validate(bad, expected_program_ids_in_order=[101, 102])


def test_dropped_program_rejected():
    """LLM drops a program from the list -> must reject."""
    bad = json.dumps({
        "explanations": [
            {"program_id": 101, "academic_compatibility": "a", "interest_compatibility": "b",
             "career_compatibility": "c", "future_opportunities": "d", "summary": "e"},
        ]
    })
    with pytest.raises(ValidationError):
        parse_and_validate(bad, expected_program_ids_in_order=[101, 102])


def test_reordered_programs_rejected():
    """LLM returns same programs but in wrong order -> must reject (order = ranking, not negotiable)."""
    bad = json.dumps({
        "explanations": [
            {"program_id": 102, "academic_compatibility": "a", "interest_compatibility": "b",
             "career_compatibility": "c", "future_opportunities": "d", "summary": "e"},
            {"program_id": 101, "academic_compatibility": "a", "interest_compatibility": "b",
             "career_compatibility": "c", "future_opportunities": "d", "summary": "e"},
        ]
    })
    with pytest.raises(ValidationError):
        parse_and_validate(bad, expected_program_ids_in_order=[101, 102])


def test_missing_required_field_rejected():
    bad = json.dumps({
        "explanations": [
            {"program_id": 101, "academic_compatibility": "a"},  # missing other fields
        ]
    })
    with pytest.raises(ValidationError):
        parse_and_validate(bad, expected_program_ids_in_order=[101])


def test_missing_explanations_key_rejected():
    with pytest.raises(ValidationError):
        parse_and_validate(json.dumps({"foo": "bar"}), expected_program_ids_in_order=[101])
