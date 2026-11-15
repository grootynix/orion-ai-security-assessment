"""Regression tests for the next-wave hardening backlog."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import load_settings
from app.main import create_app
from app.prompts.registry import PromptRegistry
from tests.conftest import DATA_DIR, token_for


def test_prompt_loaded_from_disk_with_stable_hash():
    registry = PromptRegistry()
    prompt = registry.get("orion.chat.default", require_approved=True)
    root = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "prompts"
        / "templates"
        / "orion.chat.default"
        / "v1.0.0"
    )
    system = (root / "system.md").read_text(encoding="utf-8").strip()
    developer = (root / "developer.md").read_text(encoding="utf-8").strip()
    assert prompt.system_instructions == system
    assert prompt.developer_instructions == developer
    assert prompt.status == "approved"
    assert "untrusted" in prompt.system_instructions.lower()


def test_token_revocation_blocks_reuse(client):
    token = token_for(client, "alice@example.test")
    logout = client.post(
        "/api/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 200
    denied = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 401


def test_oversized_request_rejected(tmp_path):
    settings = load_settings(
        data_directory=DATA_DIR,
        database_path=tmp_path / "body.sqlite3",
        environ={
            **os.environ,
            "ORION_ENV": "test",
            "ORION_ENABLE_DEV_IDP": "true",
            "ORION_TOKEN_SIGNING_KEY": "orion-test-signing-key-not-for-production",
            "ORION_MAX_REQUEST_BODY_BYTES": "64",
        },
    )
    application = create_app(
        database_path=tmp_path / "body.sqlite3",
        data_directory=DATA_DIR,
        settings=settings,
    )
    with TestClient(application) as test_client:
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


def test_audit_events_are_hash_chained(client):
    token = token_for(client, "alice@example.test")
    client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "What does the travel policy say?"},
    )
    admin = token_for(client, "admin@example.test")
    events = client.get(
        "/api/audit", headers={"Authorization": f"Bearer {admin}"}
    ).json()
    assert events
    assert events[0].get("event_hash")
    assert events[0].get("prev_hash")


def test_dockerfile_digest_assertion_script():
    from scripts.assert_dockerfile_digests import main

    assert main() == 0
