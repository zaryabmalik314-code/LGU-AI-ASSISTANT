"""
Fallback explanation generator. No LLM call. Used when:
- ANTHROPIC_API_KEY missing / API down / timeout
- LLM output fails validation (invented/dropped/reordered programs, bad JSON)
Guarantees the user always gets a response, even if less eloquent.
"""
from typing import List, Dict
from app.llm.validate import ValidatedExplanation


def build_fallback_explanations(ranked_programs: List[Dict]) -> List[ValidatedExplanation]:
    result = []
    for p in ranked_programs:
        name = p.get("name", "this program")
        dept = p.get("department", "")
        result.append(ValidatedExplanation(
            program_id=p["program_id"],
            academic_compatibility=f"{name} matches the eligibility requirements you meet.",
            interest_compatibility="Based on the interest tags associated with this program.",
            career_compatibility=f"{name} aligns with career paths in {dept or 'this field'}.",
            future_opportunities=p.get("career_opportunities") or "See program details for career outcomes.",
            summary=f"{name} is recommended based on your academic profile and stated interests.",
        ))
    return result
