"""Fail if Dockerfile FROM lines are not digest-pinned."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
FROM_RE = re.compile(r"^\s*FROM\s+(.+)$", re.IGNORECASE | re.MULTILINE)


def main() -> int:
    text = DOCKERFILE.read_text(encoding="utf-8")
    # Expand ARG default if present for documentation; validate literal FROM lines
    # and the ARG default used for PYTHON_BASE.
    failures: list[str] = []
    arg_match = re.search(
        r"^\s*ARG\s+PYTHON_BASE=(.+)$", text, flags=re.MULTILINE
    )
    if arg_match and "@sha256:" not in arg_match.group(1):
        failures.append(f"PYTHON_BASE missing digest: {arg_match.group(1)}")

    for match in FROM_RE.finditer(text):
        image = match.group(1).strip()
        # Allow FROM ${PYTHON_BASE} when ARG is digest-pinned.
        if image.startswith(("${", "$PYTHON_BASE")):
            continue
        # Ignore stage names after AS
        image_ref = image.split()[0]
        if "@sha256:" not in image_ref:
            failures.append(f"Unpinned FROM: {image}")

    if failures:
        print("Dockerfile digest pin check failed:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("Dockerfile digest pin check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
