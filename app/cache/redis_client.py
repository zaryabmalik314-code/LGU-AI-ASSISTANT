"""
Thin Redis wrapper. If REDIS_URL isn't set, or Redis is unreachable, every
call becomes a silent no-op — caching is a pure optimization, never a
hard dependency. A cache outage must never take down recommendations.
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL")
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 7

_client = None
_enabled = False

if REDIS_URL:
    try:
        import redis
        _client = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        _client.ping()
        _enabled = True
    except Exception as e:
        logger.warning(f"Redis unavailable, caching disabled: {e}")
        _client = None
        _enabled = False


def is_enabled() -> bool:
    return _enabled


def get_cached(key: str) -> dict | None:
    if not _enabled:
        return None
    try:
        raw = _client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Cache get failed, treating as miss: {e}")
        return None


def set_cached(key: str, value: dict, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    if not _enabled:
        return
    try:
        _client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as e:
        logger.warning(f"Cache set failed, continuing without cache: {e}")


def invalidate_all() -> int:
    if not _enabled:
        return 0
    try:
        keys = list(_client.scan_iter(match="explain:*"))
        if keys:
            return _client.delete(*keys)
        return 0
    except Exception as e:
        logger.warning(f"Cache invalidation failed: {e}")
        return 0
