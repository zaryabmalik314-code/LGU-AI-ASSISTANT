"""
Buckets requests into cache keys for the LLM EXPLANATION step only.

IMPORTANT: Rule Engine eligibility and ranking are NEVER cached — they run fresh
on every request, because percentage-band bucketing could straddle an actual
eligibility cutoff (e.g. band "70-74" could contain both a 71% who fails a 72%
cutoff and a 74% who passes it). Caching that would silently misinform someone.

What IS safe to cache: once eligibility+ranking produced an exact, correct
ranked_program_ids list for this student, the explanation text for that exact
list + the student's interest/career tags is reusable by anyone else who lands
on the exact same ranked list with similar interests.
"""
import hashlib
from typing import List


def _normalize_tags(tags: List[str]) -> str:
    return ",".join(sorted(t.strip().lower() for t in tags)) if tags else ""


def build_bucket_key(
    ranked_program_ids: List[int],
    interests: List[str],
    career_goals: List[str],
) -> str:
    raw = "|".join([
        ",".join(str(i) for i in ranked_program_ids),
        _normalize_tags(interests),
        _normalize_tags(career_goals),
    ])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"explain:{digest}"
