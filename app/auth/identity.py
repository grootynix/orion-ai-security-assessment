"""Server-side identity directory. Client role claims are never trusted."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Role, UserContext

SYNTHETIC_USERS: dict[str, dict[str, object]] = {
    "alice@example.test": {"role": "employee", "projects": ["atlas"]},
    "bob@example.test": {"role": "employee", "projects": ["prism"]},
    "manager@example.test": {
        "role": "manager",
        "projects": ["atlas", "prism"],
    },
    "admin@example.test": {
        "role": "administrator",
        "projects": ["atlas", "prism"],
    },
}


@dataclass(frozen=True)
class IdentityRecord:
    """Server-side canonical identity; never accept this shape from the client."""

    email: str
    role: Role
    projects: tuple[str, ...]
    tenant_id: str = "orion-local"


class IdentityDirectory:
    """Canonical identity source used after token signature verification."""

    def __init__(self, records: dict[str, dict[str, object]] | None = None):
        source = records or SYNTHETIC_USERS
        self._records = {
            email.lower(): IdentityRecord(
                email=email.lower(),
                role=str(payload["role"]),  # type: ignore[arg-type]
                projects=tuple(payload.get("projects", [])),  # type: ignore[arg-type]
            )
            for email, payload in source.items()
        }

    def get(self, email: str) -> IdentityRecord | None:
        """Lookup by email; returns None for unknown identities."""
        return self._records.get(email.strip().lower())

    def known_emails(self) -> set[str]:
        """All directory emails (used by DevIdP and tests only)."""
        return set(self._records)

    def to_user_context(self, record: IdentityRecord) -> UserContext:
        """Map a directory record into a request-scoped UserContext."""
        return UserContext(
            email=record.email,
            role=record.role,
            projects=list(record.projects),
            tenant_id=record.tenant_id,
        )
