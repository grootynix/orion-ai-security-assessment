"""SQLite persistence for documents, customers, audit, outbox, and approvals."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    """Parameterized SQLite access for Orion runtime data."""

    def __init__(self, database_path: Path, seed_directory: Path):
        self.database_path = database_path
        self.seed_directory = seed_directory

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.database_path.parent.chmod(0o700)
        except OSError:
            pass
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
                    event_id TEXT NOT NULL,
                    correlation_id TEXT,
                    user_email TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    tool_selected TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    status TEXT NOT NULL,
                    authorization_decision TEXT,
                    resource_type TEXT,
                    resource_id TEXT,
                    approval_status TEXT,
                    model_version TEXT,
                    prompt_version TEXT,
                    prev_hash TEXT,
                    event_hash TEXT,
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
                CREATE TABLE IF NOT EXISTS pending_actions (
                    action_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decided_by TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS revoked_jtis (
                    jti TEXT PRIMARY KEY,
                    revoked_at TEXT NOT NULL,
                    revoked_by TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_trajectories (
                    run_id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    events TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            documents = json.loads(
                (self.seed_directory / "documents.json").read_text(encoding="utf-8")
            )
            customers = json.loads(
                (self.seed_directory / "customers.json").read_text(encoding="utf-8")
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO documents
                    (id, title, classification, project, content)
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
        try:
            if self.database_path.exists():
                self.database_path.chmod(0o600)
        except OSError:
            pass

    def documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, title, classification, project, content "
                "FROM documents ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, title, classification, project, content "
                "FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT content FROM customers WHERE id = ?",
                (customer_id,),
            ).fetchone()
        return json.loads(row["content"]) if row else None

    def write_audit(
        self,
        user_email: str,
        endpoint: str,
        tool_selected: str,
        arguments: dict[str, Any],
        status: str,
        correlation_id: str | None = None,
        authorization_decision: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        approval_status: str | None = None,
        model_version: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        event_id = str(uuid.uuid4())
        created_at = utc_now()
        args_json = json.dumps(arguments, sort_keys=True)
        with self.connect() as connection:
            prev = connection.execute(
                "SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev["event_hash"] if prev and prev["event_hash"] else "genesis"
            material = f"{prev_hash}|{event_id}|{user_email}|{endpoint}|{tool_selected}|{args_json}|{status}|{created_at}"
            event_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, correlation_id, user_email, endpoint, tool_selected,
                    arguments, status, authorization_decision, resource_type,
                    resource_id, approval_status, model_version, prompt_version,
                    prev_hash, event_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    correlation_id,
                    user_email,
                    endpoint,
                    tool_selected,
                    args_json,
                    status,
                    authorization_decision,
                    resource_type,
                    resource_id,
                    approval_status,
                    model_version,
                    prompt_version,
                    prev_hash,
                    event_hash,
                    created_at,
                ),
            )

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, correlation_id, user_email, endpoint, tool_selected,
                       arguments, status, authorization_decision, resource_type,
                       resource_id, approval_status, model_version, prompt_version,
                       prev_hash, event_hash, created_at
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

    def revoke_jti(self, jti: str, revoked_by: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO revoked_jtis (jti, revoked_at, revoked_by)
                VALUES (?, ?, ?)
                """,
                (jti, utc_now(), revoked_by),
            )

    def is_jti_revoked(self, jti: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM revoked_jtis WHERE jti = ?", (jti,)
            ).fetchone()
        return row is not None

    def write_trajectory(
        self, run_id: str, user_email: str, events: list[dict[str, Any]]
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO agent_trajectories
                    (run_id, user_email, events, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, user_email, json.dumps(events), utc_now()),
            )

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

    def create_pending_action(
        self, tool_name: str, arguments: dict[str, Any], requested_by: str
    ) -> str:
        action_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_actions
                    (action_id, tool_name, arguments, requested_by, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    action_id,
                    tool_name,
                    json.dumps(arguments, sort_keys=True),
                    requested_by,
                    utc_now(),
                ),
            )
        return action_id

    def get_pending_action(self, action_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT action_id, tool_name, arguments, requested_by, status,
                       decided_by, created_at, decided_at
                FROM pending_actions WHERE action_id = ?
                """,
                (action_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["arguments"] = json.loads(payload["arguments"])
        return payload

    def list_pending_actions(
        self, status: str = "pending", limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT action_id, tool_name, arguments, requested_by, status,
                       decided_by, created_at, decided_at
                FROM pending_actions
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        results = []
        for row in rows:
            payload = dict(row)
            payload["arguments"] = json.loads(payload["arguments"])
            results.append(payload)
        return results

    def decide_pending_action(
        self, action_id: str, status: str, decided_by: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pending_actions
                SET status = ?, decided_by = ?, decided_at = ?
                WHERE action_id = ? AND status = 'pending'
                """,
                (status, decided_by, utc_now(), action_id),
            )
        return self.get_pending_action(action_id)
