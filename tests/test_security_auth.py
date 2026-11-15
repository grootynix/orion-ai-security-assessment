"""Authentication and authorization security regression tests."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt

from tests.conftest import token_for


def test_unsigned_token_rejected(client, app):
    payload = {
        "sub": "alice@example.test",
        "iss": app.state.settings.token_issuer,
        "aud": app.state.settings.token_audience,
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iat": datetime.now(UTC),
        "nbf": datetime.now(UTC),
        "jti": "unsigned-test",
    }
    unsigned = jwt.encode(payload, key="", algorithm="none")
    response = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {unsigned}"},
    )
    assert response.status_code == 401


def test_forged_base64_json_token_rejected(client):
    forged = base64.urlsafe_b64encode(
        json.dumps(
            {
                "email": "alice@example.test",
                "role": "administrator",
                "projects": ["atlas", "prism"],
            }
        ).encode()
    ).decode().rstrip("=")
    response = client.get(
        "/api/audit",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401


def test_role_escalation_via_token_claims_rejected(client, app):
    # Issue a valid token for alice, then mint a signed JWT with admin role claim.
    # Server must rebind from identity directory and deny audit access.
    now = datetime.now(UTC)
    escalated = jwt.encode(
        {
            "sub": "alice@example.test",
            "role": "administrator",
            "projects": ["atlas", "prism"],
            "iss": app.state.settings.token_issuer,
            "aud": app.state.settings.token_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(hours=1),
            "jti": "escalation-test",
        },
        app.state.settings.token_signing_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/audit",
        headers={"Authorization": f"Bearer {escalated}"},
    )
    assert response.status_code == 403


def test_expired_token_rejected(client, app):
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "alice@example.test",
            "iss": app.state.settings.token_issuer,
            "aud": app.state.settings.token_audience,
            "iat": now - timedelta(hours=2),
            "nbf": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": "expired-test",
        },
        app.state.settings.token_signing_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401


def test_invalid_issuer_rejected(client, app):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "alice@example.test",
            "iss": "evil-issuer",
            "aud": app.state.settings.token_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(hours=1),
            "jti": "issuer-test",
        },
        app.state.settings.token_signing_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_invalid_audience_rejected(client, app):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "alice@example.test",
            "iss": app.state.settings.token_issuer,
            "aud": "wrong-audience",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(hours=1),
            "jti": "audience-test",
        },
        app.state.settings.token_signing_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_production_disables_dev_idp(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_ENV", "production")
    monkeypatch.setenv("ORION_ENABLE_DEV_IDP", "false")
    monkeypatch.setenv("ORION_TOKEN_SIGNING_KEY", "production-test-key-32chars-min")
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.config.settings import load_settings
    from app.main import create_app

    settings = load_settings(
        data_directory=Path(__file__).resolve().parents[1] / "data",
        database_path=tmp_path / "prod.sqlite3",
    )
    assert settings.enable_dev_idp is False
    application = create_app(
        database_path=tmp_path / "prod.sqlite3",
        data_directory=Path(__file__).resolve().parents[1] / "data",
        settings=settings,
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/token", json={"email": "alice@example.test"}
        )
        assert response.status_code == 403


def test_production_rejects_missing_signing_key(monkeypatch):
    from app.config.settings import ConfigurationError, load_settings

    monkeypatch.setenv("ORION_ENV", "production")
    monkeypatch.delenv("ORION_TOKEN_SIGNING_KEY", raising=False)
    monkeypatch.setenv("ORION_ENABLE_DEV_IDP", "false")
    try:
        load_settings(environ={
            "ORION_ENV": "production",
            "ORION_ENABLE_DEV_IDP": "false",
        })
        assert False, "Expected ConfigurationError"
    except ConfigurationError:
        pass


def test_cross_user_customer_access_denied(client):
    alice = token_for(client, "alice@example.test")
    response = client.get(
        "/api/customers/customer-orbit-219",
        headers={"Authorization": f"Bearer {alice}"},
    )
    assert response.status_code == 404


def test_assignee_can_read_own_customer(client):
    alice = token_for(client, "alice@example.test")
    response = client.get(
        "/api/customers/customer-cinder-104",
        headers={"Authorization": f"Bearer {alice}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "customer-cinder-104"


def test_unauthorized_audit_access_denied(client):
    alice = token_for(client, "alice@example.test")
    response = client.get(
        "/api/audit",
        headers={"Authorization": f"Bearer {alice}"},
    )
    assert response.status_code == 403
