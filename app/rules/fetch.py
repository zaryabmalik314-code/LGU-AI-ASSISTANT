"""
Structured fetch — replaces classic vector-RAG step.
Eligible program_ids known already (from Rule Engine) → fetch full rows directly.
No embeddings. No semantic search. Can't retrieve wrong document.
"""
from typing import List
from sqlalchemy.orm import Session
from app.models.models import Program, ProgramContent


def fetch_program_details(db: Session, program_ids: List[int]) -> List[dict]:
    if not program_ids:
        return []

    rows = (
        db.query(Program, ProgramContent)
        .join(ProgramContent, ProgramContent.program_id == Program.id)
        .filter(Program.id.in_(program_ids), Program.is_active.is_(True))
        .all()
    )

    results = []
    for program, content in rows:
        results.append({
            "program_id": program.id,
            "name": program.name,
            "department": program.department,
            "duration_years": program.duration_years,
            "preferred_stream": program.preferred_stream,
            "description": content.description,
            "curriculum": content.curriculum,
            "career_opportunities": content.career_opportunities,
            "required_skills": content.required_skills,
            "interest_tags": content.interest_tags,
            "career_keywords": content.career_keywords,
        })

    # Preserve caller's order (e.g. ranked order) instead of DB's arbitrary order.
    order = {pid: i for i, pid in enumerate(program_ids)}
    results.sort(key=lambda r: order.get(r["program_id"], 999))
    return results
