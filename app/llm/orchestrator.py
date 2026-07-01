"""
Phase 5 entrypoint. Single function the API layer calls.
Tries LLM explanation -> validates -> falls back to template on ANY failure.
Never raises — always returns something usable, with a flag showing which path was used.
"""
import logging
from typing import List, Dict
from dataclasses import dataclass

from app.llm.client import call_llm, LLMError
from app.llm.prompt import SYSTEM_PROMPT, build_user_prompt
from app.llm.validate import parse_and_validate, ValidationError, ValidatedExplanation
from app.llm.fallback import build_fallback_explanations

logger = logging.getLogger(__name__)


@dataclass
class ExplanationResult:
    explanations: List[ValidatedExplanation]
    source: str  # "llm" or "fallback_template"


def generate_explanations(student_profile: dict, ranked_programs: List[Dict]) -> ExplanationResult:
    expected_ids = [p["program_id"] for p in ranked_programs]

    if not ranked_programs:
        return ExplanationResult(explanations=[], source="fallback_template")

    try:
        user_prompt = build_user_prompt(student_profile, ranked_programs)
        raw = call_llm(SYSTEM_PROMPT, user_prompt)
        validated = parse_and_validate(raw, expected_ids)
        return ExplanationResult(explanations=validated, source="llm")

    except LLMError as e:
        logger.warning(f"LLM call failed, using fallback: {e}")
    except ValidationError as e:
        logger.warning(f"LLM output failed validation, using fallback: {e}")

    fallback = build_fallback_explanations(ranked_programs)
    return ExplanationResult(explanations=fallback, source="fallback_template")
