"""Shared pytest fixtures. Forces non-production DevIdP for local tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure fail-closed production paths are not accidentally engaged in unit tests.
os.environ.setdefault("ORION_ENV", "test")
os.environ.setdefault("ORION_ENABLE_DEV_IDP", "true")
os.environ.setdefault(
    "ORION_TOKEN_SIGNING_KEY", "orion-test-signing-key-not-for-production"
)

from app.config.settings import load_settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture()
def app(tmp_path: Path):
    database_path = tmp_path / "orion.sqlite3"
    settings = load_settings(
        data_directory=DATA_DIR,
        database_path=database_path,
        environ={
            **os.environ,
            "ORION_ENV": "test",
            "ORION_ENABLE_DEV_IDP": "true",
            "ORION_TOKEN_SIGNING_KEY": "orion-test-signing-key-not-for-production",
        },
    )
    application = create_app(
        database_path=database_path,
        data_directory=DATA_DIR,
        settings=settings,
    )
    return application


@pytest.fixture()
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def token_for(client: TestClient, email: str) -> str:
    response = client.post("/api/token", json={"email": email})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
