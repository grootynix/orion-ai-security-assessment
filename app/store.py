import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, database_path: Path, seed_directory: Path):
        self.database_path = database_path
        self.seed_directory = seed_directory

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    project TEXT,
                    content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    assigned_to TEXT NOT NULL,
                    content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    tool_selected TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            documents = json.loads((self.seed_directory / "documents.json").read_text())
            customers = json.loads((self.seed_directory / "customers.json").read_text())
            connection.executemany(
                """
                INSERT OR IGNORE INTO documents (id, title, classification, project, content)
                VALUES (:id, :title, :classification, :project, :content)
                """,
                documents,
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO customers (id, assigned_to, content)
                VALUES (:id, :assigned_to, :content)
                """,
                [
                    {
                        "id": customer["id"],
                        "assigned_to": customer["assigned_to"],
                        "content": json.dumps(customer),
                    }
                    for customer in customers
                ],
            )

    def documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, title, classification, project, content FROM documents ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, title, classification, project, content FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT content FROM customers WHERE id = ?", (customer_id,)
            ).fetchone()
        return json.loads(row["content"]) if row else None

    def write_audit(
        self,
        user_email: str,
        endpoint: str,
        tool_selected: str,
        arguments: dict[str, Any],
        status: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events
                    (user_email, endpoint, tool_selected, arguments, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_email,
                    endpoint,
                    tool_selected,
                    json.dumps(arguments, sort_keys=True),
                    status,
                    utc_now(),
                ),
            )

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT user_email, endpoint, tool_selected, arguments, status, created_at
                FROM audit_events ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                **dict(row),
                "arguments": json.loads(row["arguments"]),
            }
            for row in rows
        ]

    def write_email(
        self, sender: str, recipient: str, subject: str, body: str
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO outbox (sender, recipient, subject, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sender, recipient, subject, body, utc_now()),
            )
            return int(cursor.lastrowid)

    def outbox_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, sender, recipient, subject, body, created_at
                FROM outbox ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
