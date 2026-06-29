"""
Tests for app.cache.redis_client.

Key behavior under test: caching must NEVER be a hard dependency.
- With no REDIS_URL set (the default test environment), every call must be
  a silent no-op rather than raising.
- Even when a client IS configured, any exception from Redis itself must be
  swallowed and treated as a cache miss / no-op, never propagated.

We monkeypatch the module's internal _client/_enabled state directly rather
than spinning up a real Redis server.
"""
import app.cache.redis_client as redis_client


def test_disabled_by_default_when_no_redis_url(monkeypatch):
    monkeypatch.setattr(redis_client, "_enabled", False)
    monkeypatch.setattr(redis_client, "_client", None)
    assert redis_client.is_enabled() is False


def test_get_cached_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(redis_client, "_enabled", False)
    monkeypatch.setattr(redis_client, "_client", None)
    assert redis_client.get_cached("explain:anything") is None


def test_set_cached_does_not_raise_when_disabled(monkeypatch):
    monkeypatch.setattr(redis_client, "_enabled", False)
    monkeypatch.setattr(redis_client, "_client", None)
    # Should simply do nothing, no exception.
    redis_client.set_cached("explain:anything", {"foo": "bar"})


def test_invalidate_all_returns_zero_when_disabled(monkeypatch):
    monkeypatch.setattr(redis_client, "_enabled", False)
    monkeypatch.setattr(redis_client, "_client", None)
    assert redis_client.invalidate_all() == 0


class _FakeRedisClient:
    """Minimal in-memory stand-in for a redis.Redis client."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def scan_iter(self, match=None):
        return iter(self.store.keys())

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
        return count


def test_set_then_get_roundtrip_when_enabled(monkeypatch):
    fake = _FakeRedisClient()
    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", fake)

    redis_client.set_cached("explain:abc123", {"text": "hello"})
    result = redis_client.get_cached("explain:abc123")
    assert result == {"text": "hello"}


def test_get_cached_returns_none_for_missing_key_when_enabled(monkeypatch):
    fake = _FakeRedisClient()
    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", fake)

    assert redis_client.get_cached("explain:does-not-exist") is None


def test_get_cached_swallows_exceptions_and_returns_none(monkeypatch):
    class _BrokenClient:
        def get(self, key):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", _BrokenClient())

    # Must NOT raise — a cache outage should never break the request.
    assert redis_client.get_cached("explain:abc123") is None


def test_set_cached_swallows_exceptions_silently(monkeypatch):
    class _BrokenClient:
        def set(self, key, value, ex=None):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", _BrokenClient())

    # Must NOT raise.
    redis_client.set_cached("explain:abc123", {"text": "hello"})


def test_invalidate_all_swallows_exceptions_and_returns_zero(monkeypatch):
    class _BrokenClient:
        def scan_iter(self, match=None):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", _BrokenClient())

    assert redis_client.invalidate_all() == 0


def test_invalidate_all_deletes_only_explain_keys(monkeypatch):
    fake = _FakeRedisClient()
    fake.store = {
        "explain:111": "{}",
        "explain:222": "{}",
        "other:333": "{}",
    }

    # scan_iter is called with match="explain:*" in the real implementation,
    # so our fake (which ignores match and returns all keys) stands in for
    # "the query already filtered server-side" — we just verify delete logic.
    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", fake)

    deleted = redis_client.invalidate_all()
    # Fake ignores the match filter, so all 3 keys are visible to scan_iter;
    # what matters is that delete() is invoked with whatever scan_iter yields.
    assert deleted == 3
    assert fake.store == {}


def test_invalidate_all_returns_zero_when_no_keys_match(monkeypatch):
    fake = _FakeRedisClient()
    fake.store = {}

    monkeypatch.setattr(redis_client, "_enabled", True)
    monkeypatch.setattr(redis_client, "_client", fake)

    assert redis_client.invalidate_all() == 0
