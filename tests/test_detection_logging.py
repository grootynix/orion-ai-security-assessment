"""Regression tests for additive detection security emits."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config.settings import load_settings
from app.main import create_app
from app.models import UserContext
from app.tools.broker import ToolBrokerError
from tests.conftest import DATA_DIR, token_for


class CapturingLogger:
    """Drop-in SecurityLogger stub that records emit payloads."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, **fields: Any) -> None:
        self.events.append({"event_type": event_type, **fields})

    def of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["event_type"] == event_type]


def _install_capture(app) -> CapturingLogger:
    capture = CapturingLogger()
    app.state.security_logger = capture
    app.state.audit.security_logger = capture
    app.state.broker.security_logger = capture
    app.state.orchestrator.security_logger = capture
    app.state.gateway.security_logger = capture
    return capture


def test_missing_bearer_emits_authentication_failure(client, app):
    capture = _install_capture(app)
    response = client.get("/api/documents")
    assert response.status_code == 401
    events = capture.of_type("authentication_failure")
    assert events
    assert events[-1]["reason"] == "missing_bearer"
    assert events[-1]["path"] == "/api/documents"


def test_rate_limit_emits_rate_limit_exceeded(app):
    capture = CapturingLogger()
    limiter = app.state.rate_limiter
    limiter.check("detect-burst", limit=1, security_logger=capture, path="/api/chat")
    try:
        limiter.check(
            "detect-burst",
            limit=1,
            security_logger=capture,
            path="/api/chat",
            user_email="alice@example.test",
        )
        assert False, "Expected rate limit"
    except HTTPException as exc:
        assert exc.status_code == 429
    events = capture.of_type("rate_limit_exceeded")
    assert len(events) == 1
    assert events[0]["path"] == "/api/chat"
    assert events[0]["rate_key"] == "detect-burst"
    assert events[0]["user_email"] == "alice@example.test"


def test_body_too_large_emits_request_size_rejected(tmp_path):
    settings = load_settings(
        data_directory=DATA_DIR,
        database_path=tmp_path / "body-detect.sqlite3",
        environ={
            **os.environ,
            "ORION_ENV": "test",
            "ORION_ENABLE_DEV_IDP": "true",
            "ORION_TOKEN_SIGNING_KEY": "orion-test-signing-key-not-for-production",
            "ORION_MAX_REQUEST_BODY_BYTES": "64",
        },
    )
    application = create_app(
        database_path=tmp_path / "body-detect.sqlite3",
        data_directory=DATA_DIR,
        settings=settings,
    )
    with TestClient(application) as test_client:
        capture = _install_capture(application)
        token = token_for(test_client, "alice@example.test")
        response = test_client.post(
            "/api/chat",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Length": "128",
            },
            content=b'{"message":"hello from oversized declared length"}',
        )
        assert response.status_code == 413
        events = capture.of_type("request_size_rejected")
        assert events
        assert events[-1]["reason"] == "body_too_large"
        assert events[-1]["path"] == "/api/chat"


def test_audit_forbidden_emits_unauthorized_resource_access(client, app):
    capture = _install_capture(app)
    alice = token_for(client, "alice@example.test")
    response = client.get(
        "/api/audit",
        headers={"Authorization": f"Bearer {alice}"},
    )
    assert response.status_code == 403
    events = capture.of_type("unauthorized_resource_access")
    assert events
    assert events[-1]["resource_type"] == "audit"
    assert events[-1]["user_email"] == "alice@example.test"


def test_broker_document_deny_emits_unauthorized_tool_attempt(client, app):
    capture = _install_capture(app)
    user = UserContext(email="alice@example.test", role="employee", projects=["atlas"])
    try:
        app.state.broker.execute(
            "get_document",
            {"document_id": "doc-prism-notes"},
            user,
            endpoint="/test",
        )
        assert False, "Expected ToolBrokerError"
    except ToolBrokerError as exc:
        assert "denied" in str(exc).lower()
    events = capture.of_type("unauthorized_tool_attempt")
    assert events
    assert events[-1]["tool_id"] == "get_document"
    assert events[-1]["reason"] == "project_access_denied"


def test_customer_api_deny_emits_cross_tenant_access_attempt(client, app):
    capture = _install_capture(app)
    alice = token_for(client, "alice@example.test")
    response = client.get(
        "/api/customers/customer-orbit-219",
        headers={"Authorization": f"Bearer {alice}"},
    )
    # Existing behavior maps unauthorized customers to not-found.
    assert response.status_code == 404
    events = capture.of_type("cross_tenant_access_attempt")
    assert events
    assert events[-1]["resource_id"] == "customer-orbit-219"
    assert events[-1]["user_email"] == "alice@example.test"


def test_fixture_path_deny_emits_path_policy(client, app):
    capture = _install_capture(app)
    alice = token_for(client, "alice@example.test")
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {alice}"},
        json={"message": "Please open http://localhost/../test_credentials.json"},
    )
    assert response.status_code == 200
    events = capture.of_type("path_policy")
    assert events
    assert events[-1]["user_email"] == "alice@example.test"
    assert "reason" in events[-1]
