"""Evaluation release gate. Failures block the suite."""

from __future__ import annotations

from pathlib import Path

from evals.runner import run_suite
from tests.conftest import token_for

DATASET = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "datasets"
    / "v1"
    / "security_cases.json"
)


def test_security_evaluation_suite_passes(client):
    report = run_suite(client, DATASET, token_for)
    assert report["release_decision"] == "pass", report
    assert report["failed"] == 0
    assert report["total"] == report["passed"]
