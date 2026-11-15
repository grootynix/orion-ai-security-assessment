"""JTI denylist for short-lived token revocation."""

from __future__ import annotations

from typing import Protocol


class RevocationStore(Protocol):
    """Persistence port for JWT jti denylist entries."""

    def revoke_jti(self, jti: str, revoked_by: str) -> None: ...

    def is_jti_revoked(self, jti: str) -> bool: ...


class TokenRevocationService:
    """
    Session revocation via JWT jti denylist.

    Fail-closed: revoked JTIs are rejected even if signature and expiry are valid.
    """

    def __init__(self, store: RevocationStore):
        self.store = store

    def revoke(self, jti: str, revoked_by: str) -> None:
        """Add jti to the denylist after logout or forced session kill."""
        self.store.revoke_jti(jti, revoked_by)

    def assert_not_revoked(self, jti: str) -> None:
        """Raise TokenError when jti is on the denylist."""
        if self.store.is_jti_revoked(jti):
            from app.auth.tokens import TokenError

            raise TokenError("Token has been revoked")
