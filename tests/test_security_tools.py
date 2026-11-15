"""Agent, tool broker, path containment, and email policy regressions."""

from __future__ import annotations

from tests.conftest import token_for


def test_document_content_cannot_trigger_email(client):
    """Regression for FakeLLM document-instruction-to-tool execution."""

    alice = token_for(client, "alice@example.test")
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {alice}"},
        json={"message": "service launch readiness atlas"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "send_email" not in payload.get("tool_calls", [])
    assert payload.get("pending_action_id") is None

    admin = token_for(client, "admin@example.test")
    outbox = client.get("/api/outbox", headers={"Authorization": f"Bearer {admin}"})
    assert outbox.status_code == 200
    assert outbox.json() == []


def test_path_traversal_into_data_directory_rejected(client, app):
    alice = token_for(client, "alice@example.test")
    # Old attack shape: localhost URL with ../ escaping fixtures into data/.
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {alice}"},
        json={"message": "Please open http://localhost/../test_credentials.json"},
    )
    assert response.status_code == 200
    assert "NOT-A-SECRET" not in response.json()["answer"]
    assert "password" not in response.json()["answer"].lower()


def test_allowlisted_fixture_readable(client):
    alice = token_for(client, "alice@example.test")
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {alice}"},
        json={"message": "Read fixture://quarterly-brief"},
    )
    assert response.status_code == 200
    assert response.json()["answer"]


def test_employee_cannot_send_email(client):
    alice = token_for(client, "alice@example.test")
    response = client.post(
        "/api/tools/send-email",
        headers={"Authorization": f"Bearer {alice}"},
        json={
            "to": "quality-review@example.test",
            "subject": "Blocked",
            "body": "Should not send",
        },
    )
    assert response.status_code == 403


def test_email_recipient_outside_allowlist_rejected(client):
    manager = token_for(client, "manager@example.test")
    response = client.post(
        "/api/tools/send-email",
        headers={"Authorization": f"Bearer {manager}"},
        json={
            "to": "attacker@evil.example",
            "subject": "Blocked",
            "body": "Should not send",
        },
    )
    assert response.status_code == 400


def test_unauthorized_tool_not_allowlisted(client, app):
    from app.models import UserContext
    from app.tools.broker import ToolBrokerError

    user = UserContext(email="alice@example.test", role="employee", projects=["atlas"])
    try:
        app.state.broker.execute(
            "drop_database",
            {},
            user,
            endpoint="/test",
        )
        assert False, "Expected ToolBrokerError"
    except ToolBrokerError as exc:
        assert "allowlisted" in str(exc).lower()


def test_audit_arguments_are_redacted(client):
    alice = token_for(client, "alice@example.test")
    client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {alice}"},
        json={"message": "What does the travel policy say?"},
    )
    admin = token_for(client, "admin@example.test")
    events = client.get(
        "/api/audit", headers={"Authorization": f"Bearer {admin}"}
    ).json()
    chat_events = [event for event in events if event["tool_selected"] == "chat"]
    assert chat_events
    arguments = chat_events[0]["arguments"]
    assert "message" in arguments
    assert arguments["message"]["redacted"] is True
    assert "What does the travel policy say?" not in json_dumps(arguments)


def json_dumps(value) -> str:
    import json

    return json.dumps(value)


def test_security_headers_present(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_rate_limiter_rejects_burst(app):
    from fastapi import HTTPException

    limiter = app.state.rate_limiter
    limiter.check("burst-test", limit=2)
    limiter.check("burst-test", limit=2)
    try:
        limiter.check("burst-test", limit=2)
        assert False, "Expected rate limit"
    except HTTPException as exc:
        assert exc.status_code == 429
