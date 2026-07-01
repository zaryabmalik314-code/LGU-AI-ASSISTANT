"""
Validates LLM output. This is the gate — if the LLM invents a program, drops one,
reorders, or returns malformed JSON, we reject it and fall back to the template.
The LLM's output never reaches the user unchecked.
"""
import json
from dataclasses import dataclass
from typing import List, Dict


class ValidationError(Exception):
    pass


@dataclass
class ValidatedExplanation:
    program_id: int
    academic_compatibility: str
    interest_compatibility: str
    career_compatibility: str
    future_opportunities: str
    summary: str


def parse_and_validate(raw_text: str, expected_program_ids_in_order: List[int]) -> List[ValidatedExplanation]:
    """
    expected_program_ids_in_order: the program_ids from the deterministic ranking, in order.
    Raises ValidationError on any mismatch — caller should catch and use fallback template.
    """
    text = raw_text.strip()
    # Defensive: strip markdown fences if the model added them despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"LLM output is not valid JSON: {e}")

    if not isinstance(parsed, dict) or "explanations" not in parsed:
        raise ValidationError("Missing 'explanations' key in LLM output")

    explanations = parsed["explanations"]
    if not isinstance(explanations, list):
        raise ValidationError("'explanations' is not a list")

    returned_ids = [e.get("program_id") for e in explanations]

    # Hard rule: returned ids must be EXACTLY the expected set, same order, no extras, no drops.
    if returned_ids != expected_program_ids_in_order:
        raise ValidationError(
            f"Program ID mismatch — expected {expected_program_ids_in_order}, got {returned_ids}. "
            "LLM may have invented, dropped, or reordered programs."
        )

    required_fields = [
        "academic_compatibility", "interest_compatibility",
        "career_compatibility", "future_opportunities", "summary",
    ]
    validated = []
    for e in explanations:
        missing = [f for f in required_fields if f not in e or not isinstance(e[f], str)]
        if missing:
            raise ValidationError(f"Explanation for program_id={e.get('program_id')} missing/invalid fields: {missing}")
        validated.append(ValidatedExplanation(
            program_id=e["program_id"],
            academic_compatibility=e["academic_compatibility"],
            interest_compatibility=e["interest_compatibility"],
            career_compatibility=e["career_compatibility"],
            future_opportunities=e["future_opportunities"],
            summary=e["summary"],
        ))

    return validated
