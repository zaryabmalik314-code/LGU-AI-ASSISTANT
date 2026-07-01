"""
Integration tests for Phase 9 — Production Readiness.
"""
import logging
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.main import app, get_db, request_id_ctx_var
from app.config import Settings
import app.cache.redis_client as redis_client

# ---------------------------------------------------------------------------
# Mock Database & Session for Production Tests
# ---------------------------------------------------------------------------

class ProductionMockSession:
    def __init__(self, should_fail_db=False):
        self.should_fail_db = should_fail_db
        self.executed_queries = []

    def execute(self, statement, *args, **kwargs):
        if self.should_fail_db:
            raise Exception("Database connection failure")
        self.executed_queries.append(statement)
        # Return a mock result
        mock_result = MagicMock()
        return mock_result

    def query(self, *args, **kwargs):
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        return mock_query


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_settings_overrides_via_env(monkeypatch):
    """Verify Settings load variables from environment variables correctly."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://testuser:testpass@testhost:5432/testdb")
    monkeypatch.setenv("REDIS_URL", "redis://testredis:6379/1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("POLICY_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()
    assert settings.database_url == "postgresql://testuser:testpass@testhost:5432/testdb"
    assert settings.redis_url == "redis://testredis:6379/1"
    assert settings.groq_api_key == "gsk_test_key"
    assert settings.policy_scheduler_enabled is True
    assert settings.log_level == "DEBUG"


def test_health_check_healthy(monkeypatch):
    """Verify /health returns HTTP 200 and 'connected' when db and cache are healthy."""
    session = ProductionMockSession(should_fail_db=False)
    app.dependency_overrides[get_db] = lambda: session

    # Enable and mock healthy Redis
    monkeypatch.setattr(redis_client, "is_enabled", lambda: True)
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    monkeypatch.setattr(redis_client, "_client", mock_redis)

    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["cache"] == "connected"
    assert "timestamp" in data

    app.dependency_overrides.clear()


def test_health_check_redis_degraded(monkeypatch):
    """Verify /health returns HTTP 200 and 'unreachable' cache status when Redis ping fails."""
    session = ProductionMockSession(should_fail_db=False)
    app.dependency_overrides[get_db] = lambda: session

    # Enable Redis but simulate crash on ping
    monkeypatch.setattr(redis_client, "is_enabled", lambda: True)
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("Redis connection timeout")
    monkeypatch.setattr(redis_client, "_client", mock_redis)

    client = TestClient(app)
    response = client.get("/health")
    
    # DB is healthy, so health check should still succeed with HTTP 200 (graceful degradation)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "unreachable" in data["cache"]

    app.dependency_overrides.clear()


def test_health_check_db_unhealthy(monkeypatch):
    """Verify /health returns HTTP 503 when the critical DB dependency fails."""
    session = ProductionMockSession(should_fail_db=True)
    app.dependency_overrides[get_db] = lambda: session

    # Disable Redis for simplicity in this test
    monkeypatch.setattr(redis_client, "is_enabled", lambda: False)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    
    # Database is critical, must fail with HTTP 503
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "disconnected" in data["database"]
    assert data["cache"] == "disabled"

    app.dependency_overrides.clear()


def test_request_id_generation_and_headers():
    """Verify that every request generates a request ID and returns it in headers."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Check it is a valid UUID structure
    req_id = response.headers["X-Request-ID"]
    assert len(req_id) == 36


def test_request_id_passed_from_client():
    """Verify that if the client passes X-Request-ID, the API preserves it."""
    client = TestClient(app)
    custom_id = "test-custom-request-id-12345"
    response = client.get("/", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_logger_picks_up_request_id(monkeypatch):
    """Verify logger prints request ID inside the logged line during request lifecycle."""
    client = TestClient(app)
    
    # Capture root log outputs
    from io import StringIO
    log_stream = StringIO()
    root_logger = logging.getLogger()
    
    # Add a temporary stream handler to capture root logs
    temp_handler = logging.StreamHandler(log_stream)
    from app.main import RequestIdFilter
    temp_handler.addFilter(RequestIdFilter())
    formatter = logging.Formatter("[ReqID: %(request_id)s] %(message)s")
    temp_handler.setFormatter(formatter)
    
    root_logger.addHandler(temp_handler)
    
    try:
        custom_id = "logger-check-id-abc"
        response = client.get("/", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        
        # Check logs
        log_output = log_stream.getvalue()
        assert f"[ReqID: {custom_id}]" in log_output
        assert "Incoming Request:" in log_output
        assert "Outgoing Response:" in log_output
    finally:
        root_logger.removeHandler(temp_handler)
