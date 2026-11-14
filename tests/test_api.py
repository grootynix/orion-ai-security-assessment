from fastapi.testclient import TestClient
import pytest

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(database_path=tmp_path / "orion.sqlite3")
    with TestClient(app) as test_client:
        yield test_client


def token_for(client: TestClient, email: str = "alice@example.test") -> str:
    response = client.post("/api/token", json={"email": email})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_endpoint_is_available(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_authenticated_chat_returns_an_answer(client: TestClient):
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token_for(client)}"},
        json={"message": "What does the travel policy say?"},
    )

    assert response.status_code == 200
    assert "travel" in response.json()["answer"].lower()


def test_document_search_returns_matching_documents(client: TestClient):
    response = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {token_for(client)}"},
        params={"q": "travel policy"},
    )

    assert response.status_code == 200
    assert any(item["id"] == "doc-travel-policy" for item in response.json())


def test_simulated_email_is_written_to_the_local_outbox(client: TestClient):
    response = client.post(
        "/api/tools/send-email",
        headers={
            "Authorization": f"Bearer {token_for(client, 'manager@example.test')}"
        },
        json={
            "to": "recipient@example.test",
            "subject": "Local review",
            "body": "Synthetic message body",
        },
    )

    assert response.status_code == 200
    outbox = client.get("/api/outbox", headers={"Authorization": f"Bearer {token_for(client, 'admin@example.test')}"} )

    assert outbox.status_code == 200
    assert any(message["subject"] == "Local review" for message in outbox.json())
