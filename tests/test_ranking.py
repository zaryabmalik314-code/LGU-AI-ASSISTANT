from app.rules.ranking import ProgramScoreInput, rank_programs, score_program

CS = ProgramScoreInput(
    program_id=101, interest_tags=["coding", "ai", "math"], career_keywords=["software engineer", "developer"],
    stream_match=True,
)
MED = ProgramScoreInput(
    program_id=102, interest_tags=["biology", "helping people"], career_keywords=["doctor", "surgeon"],
    stream_match=False,
)
BBA = ProgramScoreInput(
    program_id=103, interest_tags=["business", "finance"], career_keywords=["manager", "entrepreneur"],
    stream_match=False,
)


def test_stream_match_boosts_score():
    r = score_program(CS, student_interests=[], student_career_goals=[])
    assert r.breakdown["stream_match"] == 1.0
    assert r.score > 0


def test_interest_overlap_detected_case_insensitive():
    r = score_program(CS, student_interests=["AI", "Coding"], student_career_goals=[])
    assert r.breakdown["interest_overlap"] > 0


def test_no_overlap_zero_score_component():
    r = score_program(MED, student_interests=["coding"], student_career_goals=[])
    assert r.breakdown["interest_overlap"] == 0.0


def test_ranking_deterministic_same_input_same_output():
    programs = [CS, MED, BBA]
    interests = ["coding", "ai"]
    goals = ["software engineer"]
    r1 = rank_programs(programs, interests, goals)
    r2 = rank_programs(programs, interests, goals)
    assert [p.program_id for p in r1] == [p.program_id for p in r2]


def test_ranking_top_n_respected():
    programs = [CS, MED, BBA]
    result = rank_programs(programs, ["coding"], [], top_n=2)
    assert len(result) == 2


def test_tie_broken_by_program_id_ascending():
    # Two programs, identical everything except id -> lower id wins tie
    a = ProgramScoreInput(program_id=5, interest_tags=[], career_keywords=[], stream_match=False)
    b = ProgramScoreInput(program_id=3, interest_tags=[], career_keywords=[], stream_match=False)
    result = rank_programs([a, b], [], [])
    assert result[0].program_id == 3


def test_cs_ranks_above_med_for_cs_leaning_student():
    result = rank_programs([CS, MED, BBA], ["coding", "ai", "math"], ["software engineer"])
    assert result[0].program_id == 101
