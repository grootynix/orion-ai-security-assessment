"""Safely reset the local Orion SQLite database in non-production environments."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    environment = os.environ.get("ORION_ENV", "development").strip().lower()
    allow_reset = os.environ.get("ORION_ALLOW_DATA_RESET", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if environment == "production":
        print("Refusing to reset data in production.", file=sys.stderr)
        return 2
    if not allow_reset:
        print(
            "Refusing to reset data without ORION_ALLOW_DATA_RESET=true.",
            file=sys.stderr,
        )
        return 2

    data_directory = Path(
        os.environ.get("ORION_DATA_DIR", ROOT / "data")
    ).resolve()
    repo_root = ROOT.resolve()
    # Deletion is constrained to paths under the repository root.
    if data_directory != repo_root and repo_root not in data_directory.parents:
        print(
            f"Refusing to reset outside the repository: {data_directory}",
            file=sys.stderr,
        )
        return 2

    database_path = Path(
        os.environ.get("ORION_DATABASE_PATH", data_directory / "orion.sqlite3")
    ).resolve()
    if data_directory not in database_path.parents and database_path != data_directory:
        print(
            f"Refusing to delete database outside data directory: {database_path}",
            file=sys.stderr,
        )
        return 2

    for database_file in (
        database_path,
        Path(f"{database_path}-shm"),
        Path(f"{database_path}-wal"),
    ):
        if database_file.exists():
            # Final containment check before unlink.
            resolved = database_file.resolve()
            if data_directory not in resolved.parents and resolved.parent != data_directory:
                print(f"Refusing unsafe path: {resolved}", file=sys.stderr)
                return 2
            database_file.unlink()

    print(f"Reset local Orion database at {database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
