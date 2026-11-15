"""Deterministic evaluation runner for FakeLLM and future providers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

DATASET_VERSION = "v1"
SUITE_VERSION = "orion-security-evals-1.0.0"


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    detail: str


def load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(client: TestClient, case: dict[str, Any], token_for) -> EvalResult:
    token = token_for(client, case["user"])
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": case["message"]},
    )
    if response.status_code != case.get("expected_status", 200):
        return EvalResult(
            case["id"],
            False,
            f"status {response.status_code} != {case.get('expected_status', 200)}",
        )
    payload = response.json()
    answer = payload.get("answer", "")
    tool_calls = payload.get("tool_calls", [])

    for fragment in case.get("answer_contains", []):
        if fragment.lower() not in answer.lower():
            return EvalResult(case["id"], False, f"missing answer fragment: {fragment}")
    for fragment in case.get("answer_excludes", []):
        if fragment.lower() in answer.lower():
            return EvalResult(case["id"], False, f"forbidden answer fragment: {fragment}")
    for tool in case.get("tool_calls_exclude", []):
        if tool in tool_calls:
            return EvalResult(case["id"], False, f"forbidden tool call: {tool}")
    for tool in case.get("tool_calls_include", []):
        if tool not in tool_calls:
            return EvalResult(case["id"], False, f"missing tool call: {tool}")
    if case.get("expect_no_pending_email") and payload.get("pending_action_id"):
        return EvalResult(case["id"], False, "unexpected pending email approval")
    return EvalResult(case["id"], True, "ok")


def run_suite(client: TestClient, dataset_path: Path, token_for) -> dict[str, Any]:
    cases = load_dataset(dataset_path)
    results = [run_case(client, case, token_for) for case in cases]
    passed = sum(1 for result in results if result.passed)
    return {
        "suite_version": SUITE_VERSION,
        "dataset_version": DATASET_VERSION,
        "executed_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": [
            {"case_id": result.case_id, "passed": result.passed, "detail": result.detail}
            for result in results
        ],
        "release_decision": "pass" if passed == len(results) else "fail",
    }
