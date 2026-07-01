from app.llm.orchestrator import generate_explanations

SAMPLE_PROGRAM = {
    "program_id": 101, "name": "BS Computer Science", "department": "CS",
    "duration_years": 4, "description": "...", "curriculum": "...",
    "career_opportunities": "Software Engineer, Data Scientist",
    "required_skills": ["math"], "interest_tags": ["coding"], "career_keywords": ["engineer"],
}

STUDENT_PROFILE = {
    "matric_pct": 80, "inter_pct": 75, "inter_stream": "ICS",
    "subjects": ["Mathematics"], "interests": ["coding"], "career_goals": ["software engineer"],
}


def test_no_api_key_falls_back_to_template(monkeypatch):
    """Without ANTHROPIC_API_KEY, should never crash — must use fallback."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_explanations(STUDENT_PROFILE, [SAMPLE_PROGRAM])
    assert result.source == "fallback_template"
    assert len(result.explanations) == 1
    assert result.explanations[0].program_id == 101


def test_empty_program_list_returns_empty_no_crash():
    result = generate_explanations(STUDENT_PROFILE, [])
    assert result.explanations == []
    assert result.source == "fallback_template"


def test_fallback_explanation_has_all_required_fields(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_explanations(STUDENT_PROFILE, [SAMPLE_PROGRAM])
    exp = result.explanations[0]
    assert exp.academic_compatibility
    assert exp.interest_compatibility
    assert exp.career_compatibility
    assert exp.future_opportunities
    assert exp.summary
