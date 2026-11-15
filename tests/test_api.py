"""Functional API compatibility tests."""

from tests.conftest import token_for


def test_health_endpoint_is_available(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "orion"


def test_authenticated_chat_returns_an_answer(client):
    token = token_for(client, "alice@example.test")
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "What does the travel policy say?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "travel" in payload["answer"].lower() or "expense" in payload["answer"].lower()
    assert "search_documents" in payload["tool_calls"]


def test_document_search_returns_matching_documents(client):
    token = token_for(client, "alice@example.test")
    response = client.get(
        "/api/documents",
        params={"q": "travel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    titles = [item["title"].lower() for item in response.json()]
    assert any("travel" in title for title in titles)


def test_simulated_email_requires_approval_then_queues(client):
    manager_token = token_for(client, "manager@example.test")
    response = client.post(
        "/api/tools/send-email",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={
            "to": "quality-review@example.test",
            "subject": "Atlas readiness review",
            "body": "Synthetic readiness note",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_approval"
    action_id = payload["pending_action_id"]

    decision = client.post(
        f"/api/approvals/{action_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"decision": "approve"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "executed"

    admin_token = token_for(client, "admin@example.test")
    outbox = client.get(
        "/api/outbox",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert outbox.status_code == 200
    assert any(
        item["subject"] == "Atlas readiness review" for item in outbox.json()
    )
