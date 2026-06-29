"""
Tests for app.cache.keys — the explanation-cache bucket key builder.

These tests only check the pure hashing/normalization logic. They do not
touch Redis at all.
"""
from app.cache.keys import build_bucket_key


def test_same_inputs_produce_same_key():
    key1 = build_bucket_key([3, 1, 2], ["AI", "Robotics"], ["Engineer"])
    key2 = build_bucket_key([3, 1, 2], ["AI", "Robotics"], ["Engineer"])
    assert key1 == key2


def test_key_has_expected_prefix():
    key = build_bucket_key([1, 2, 3], ["AI"], ["Engineer"])
    assert key.startswith("explain:")


def test_different_ranked_order_produces_different_key():
    # Ranking order matters semantically (position 1 vs 3 is a different
    # recommendation), so [1,2,3] and [3,2,1] must NOT collide.
    key1 = build_bucket_key([1, 2, 3], ["AI"], ["Engineer"])
    key2 = build_bucket_key([3, 2, 1], ["AI"], ["Engineer"])
    assert key1 != key2


def test_different_program_ids_produce_different_key():
    key1 = build_bucket_key([1, 2, 3], ["AI"], ["Engineer"])
    key2 = build_bucket_key([4, 5, 6], ["AI"], ["Engineer"])
    assert key1 != key2


def test_tag_order_does_not_matter():
    # Interests/career goals are sets conceptually — order shouldn't change
    # the bucket, since they get normalized (sorted) before hashing.
    key1 = build_bucket_key([1, 2, 3], ["AI", "Robotics"], ["Engineer", "Researcher"])
    key2 = build_bucket_key([1, 2, 3], ["Robotics", "AI"], ["Researcher", "Engineer"])
    assert key1 == key2


def test_tag_case_and_whitespace_does_not_matter():
    key1 = build_bucket_key([1, 2, 3], [" AI ", "Robotics"], ["Engineer"])
    key2 = build_bucket_key([1, 2, 3], ["ai", "robotics"], ["engineer"])
    assert key1 == key2


def test_different_interests_produce_different_key():
    key1 = build_bucket_key([1, 2, 3], ["AI"], ["Engineer"])
    key2 = build_bucket_key([1, 2, 3], ["Biology"], ["Engineer"])
    assert key1 != key2


def test_different_career_goals_produce_different_key():
    key1 = build_bucket_key([1, 2, 3], ["AI"], ["Engineer"])
    key2 = build_bucket_key([1, 2, 3], ["AI"], ["Doctor"])
    assert key1 != key2


def test_empty_tags_do_not_crash():
    key = build_bucket_key([1, 2, 3], [], [])
    assert key.startswith("explain:")


def test_empty_ranked_ids_do_not_crash():
    key = build_bucket_key([], ["AI"], ["Engineer"])
    assert key.startswith("explain:")


def test_key_is_deterministic_across_many_calls():
    keys = {build_bucket_key([7, 8, 9], ["AI"], ["Engineer"]) for _ in range(10)}
    assert len(keys) == 1
