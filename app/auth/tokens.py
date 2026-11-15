"""Signed JWT issuance and verification."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.auth.identity import IdentityDirectory
from app.config.settings import Settings
from app.models import UserContext


class TokenError(Exception):
    """Raised when a bearer token is invalid."""


class TokenService:
    """
    Issues and verifies short-lived HS256 JWTs.

    Trust assumptions:
    - Roles/projects are never taken from token claims for authorization.
    - After verify, identity is rebound from IdentityDirectory.
    - Production requires an explicit signing key (fail closed via Settings).
    """

    ALLOWED_ALGORITHMS = ("HS256",)

    def __init__(
        self,
        settings: Settings,
        directory: IdentityDirectory,
        revocation: Any | None = None,
    ):
        self.settings = settings
        self.directory = directory
        self.revocation = revocation

    def issue_for_email(self, email: str) -> str:
        """Issue a signed JWT for a known directory identity (DevIdP only)."""
        record = self.directory.get(email)
        if record is None:
            raise TokenError("Unknown identity")
        now = datetime.now(UTC)
        ttl = self.settings.token_ttl_seconds
        if self.settings.is_production:
            ttl = min(ttl, self.settings.production_token_ttl_seconds)
        payload = {
            "sub": record.email,
            "iss": self.settings.token_issuer,
            "aud": self.settings.token_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=ttl),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(
            payload,
            self.settings.token_signing_key,
            algorithm="HS256",
        )

    def verify_and_bind(self, token: str) -> UserContext:
        """Verify signature and claims, then rebind role/projects from directory."""

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("Invalid bearer token") from exc
        if header.get("alg") not in self.ALLOWED_ALGORITHMS:
            raise TokenError("Disallowed token algorithm")

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self.settings.token_signing_key,
                algorithms=list(self.ALLOWED_ALGORITHMS),
                audience=self.settings.token_audience,
                issuer=self.settings.token_issuer,
                options={
                    "require": ["sub", "exp", "iat", "nbf", "iss", "aud", "jti"],
                    "verify_signature": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise TokenError("Invalid bearer token") from exc

        jti = str(claims.get("jti", ""))
        if self.revocation is not None and jti:
            self.revocation.assert_not_revoked(jti)

        email = str(claims.get("sub", "")).strip().lower()
        record = self.directory.get(email)
        if record is None:
            raise TokenError("Unknown user")
        return self.directory.to_user_context(record)

    def extract_jti(self, token: str) -> str:
        """Return jti after signature/expiry checks; rejects revoked tokens."""
        try:
            claims = jwt.decode(
                token,
                self.settings.token_signing_key,
                algorithms=list(self.ALLOWED_ALGORITHMS),
                audience=self.settings.token_audience,
                issuer=self.settings.token_issuer,
                options={
                    "require": ["jti"],
                    "verify_exp": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise TokenError("Invalid bearer token") from exc
        jti = str(claims.get("jti", ""))
        if not jti:
            raise TokenError("Token missing jti")
        if self.revocation is not None:
            self.revocation.assert_not_revoked(jti)
        return jti
