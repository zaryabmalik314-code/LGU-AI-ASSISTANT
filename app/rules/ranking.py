"""
Deterministic Ranking — decides Top 3 order BEFORE LLM sees anything.
LLM later only explains this ranking, never re-orders it.
Pure function, fully testable, same input -> same output always.
"""
from dataclasses import dataclass
from typing import List


@dataclass
class ProgramScoreInput:
    program_id: int
    interest_tags: List[str]      # from program_content
    career_keywords: List[str]    # from program_content
    stream_match: bool            # student's stream is the program's "preferred" stream (not just eligible)


@dataclass
class RankedProgram:
    program_id: int
    score: float
    breakdown: dict  # transparent — shows exactly how score was built


# Weights are explicit constants, not magic numbers buried in code.
W_STREAM = 0.35
W_INTEREST = 0.40
W_CAREER = 0.25


def _overlap_ratio(a: List[str], b: List[str]) -> float:
    """Case-insensitive overlap ratio, 0.0-1.0. Empty inputs -> 0.0 (no false positives)."""
    if not a or not b:
        return 0.0
    set_a = {x.lower().strip() for x in a}
    set_b = {x.lower().strip() for x in b}
    overlap = set_a & set_b
    return len(overlap) / len(set_b)  # ratio of program's tags matched by student


def score_program(
    program: ProgramScoreInput,
    student_interests: List[str],
    student_career_goals: List[str],
) -> RankedProgram:
    stream_score = 1.0 if program.stream_match else 0.0
    interest_score = _overlap_ratio(student_interests, program.interest_tags)
    career_score = _overlap_ratio(student_career_goals, program.career_keywords)

    total = (
        W_STREAM * stream_score
        + W_INTEREST * interest_score
        + W_CAREER * career_score
    )

    return RankedProgram(
        program_id=program.program_id,
        score=round(total, 4),
        breakdown={
            "stream_match": stream_score,
            "interest_overlap": round(interest_score, 4),
            "career_overlap": round(career_score, 4),
            "weights": {"stream": W_STREAM, "interest": W_INTEREST, "career": W_CAREER},
        },
    )


def rank_programs(
    programs: List[ProgramScoreInput],
    student_interests: List[str],
    student_career_goals: List[str],
    top_n: int = 3,
) -> List[RankedProgram]:
    """
    Stable sort: ties broken by program_id ascending, so result is 100% deterministic
    — same student profile always produces same ranking, run to run.
    """
    scored = [
        score_program(p, student_interests, student_career_goals)
        for p in programs
    ]
    scored.sort(key=lambda r: (-r.score, r.program_id))
    return scored[:top_n]
