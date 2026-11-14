import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = Path(os.environ.get("ORION_DATA_DIR", ROOT / "data")).resolve()
DATABASE_PATH = Path(
    os.environ.get("ORION_DATABASE_PATH", DATA_DIRECTORY / "orion.sqlite3")
)

for database_file in (
    DATABASE_PATH,
    Path(f"{DATABASE_PATH}-shm"),
    Path(f"{DATABASE_PATH}-wal"),
):
    database_file.unlink(missing_ok=True)

print(f"Reset local Orion database at {DATABASE_PATH}")
