"""Reset utility and configuration fail-closed tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config.settings import ConfigurationError, load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_reset_requires_explicit_allow(tmp_path: Path):
    db = tmp_path / "orion.sqlite3"
    db.write_text("demo", encoding="utf-8")
    env = {
        **os.environ,
        "ORION_ENV": "development",
        "ORION_DATA_DIR": str(tmp_path),
        "ORION_DATABASE_PATH": str(db),
    }
    env.pop("ORION_ALLOW_DATA_RESET", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "reset_data.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert db.exists()


def test_reset_refuses_production(tmp_path: Path):
    db = tmp_path / "orion.sqlite3"
    db.write_text("demo", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "reset_data.py")],
        env={
            **os.environ,
            "ORION_ENV": "production",
            "ORION_ALLOW_DATA_RESET": "true",
            "ORION_DATA_DIR": str(tmp_path),
            "ORION_DATABASE_PATH": str(db),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert db.exists()


def test_reset_succeeds_when_allowed_under_repo_data(tmp_path: Path, monkeypatch):
    # Use a directory under the repository data tree via symlink-free temp inside repo.
    data_dir = ROOT / "data" / ".tmp-reset-test"
    data_dir.mkdir(exist_ok=True)
    db = data_dir / "orion.sqlite3"
    db.write_text("demo", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "reset_data.py")],
            env={
                **os.environ,
                "ORION_ENV": "development",
                "ORION_ALLOW_DATA_RESET": "true",
                "ORION_DATA_DIR": str(data_dir),
                "ORION_DATABASE_PATH": str(db),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert not db.exists()
    finally:
        if db.exists():
            db.unlink()
        if data_dir.exists():
            data_dir.rmdir()


def test_production_cannot_enable_dev_idp():
    with pytest.raises(ConfigurationError):
        load_settings(
            environ={
                "ORION_ENV": "production",
                "ORION_TOKEN_SIGNING_KEY": "production-key",
                "ORION_ENABLE_DEV_IDP": "true",
            }
        )
