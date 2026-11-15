"""Identity provider abstractions for DevIdP and fixture-backed OIDC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from app.auth.identity import IdentityDirectory
from app.auth.tokens import TokenError, TokenService
from app.config.settings import Settings
from app.models import UserContext


class IdentityProvider(Protocol):
    """Trusted identity boundary. Never trusts client-supplied roles."""

    def issue_development_token(self, email: str) -> str: ...

    def authenticate_bearer(self, token: str) -> UserContext: ...


class DevelopmentIdentityProvider:
    """Explicitly gated local identity provider for development and tests."""

    def __init__(
        self,
        settings: Settings,
        tokens: TokenService,
        directory: IdentityDirectory,
    ):
        self.settings = settings
        self.tokens = tokens
        self.directory = directory

    def issue_development_token(self, email: str) -> str:
        """Mint a local JWT only when DevIdP is explicitly enabled."""
        if self.settings.is_production or not self.settings.enable_dev_idp:
            raise TokenError("Development identity provider is disabled")
        return self.tokens.issue_for_email(email)

    def authenticate_bearer(self, token: str) -> UserContext:
        """Verify HS256 bearer and rebind identity from the directory."""
        return self.tokens.verify_and_bind(token)


class OidcIdentityProvider:
    """
    Enterprise OIDC/OAuth2 validation boundary.

    Supports local JWKS fixture files for offline tests. Production requires
    `ORION_OIDC_JWKS_URL` or `ORION_OIDC_JWKS_PATH` and fails closed otherwise.
    """

    def __init__(
        self,
        settings: Settings,
        directory: IdentityDirectory,
        jwks_path: Path | None = None,
    ):
        self.settings = settings
        self.directory = directory
        self.jwks_path = jwks_path
        self._jwk_client: PyJWKClient | None = None
        if settings.oidc_jwks_url:
            self._jwk_client = PyJWKClient(settings.oidc_jwks_url)

    def issue_development_token(self, email: str) -> str:
        """OIDC path never mints local tokens; fail closed."""
        raise TokenError("OIDC provider does not issue local development tokens")

    def _load_fixture_key(self) -> dict[str, Any] | None:
        if self.jwks_path is None or not self.jwks_path.exists():
            return None
        payload = json.loads(self.jwks_path.read_text(encoding="utf-8"))
        keys = payload.get("keys") or []
        return keys[0] if keys else None

    def authenticate_bearer(self, token: str) -> UserContext:
        """Validate OIDC JWT via JWKS, then rebind roles from the directory."""
        if self._jwk_client is None and self._load_fixture_key() is None:
            raise TokenError(
                "OIDC validation requires JWKS configuration; not available"
            )
        try:
            if self._jwk_client is not None:
                key = self._jwk_client.get_signing_key_from_jwt(token).key
                claims = jwt.decode(
                    token,
                    key=key,
                    algorithms=["RS256"],
                    audience=self.settings.oidc_audience or self.settings.token_audience,
                    issuer=self.settings.oidc_issuer or self.settings.token_issuer,
                    options={"require": ["sub", "exp", "iat", "iss", "aud"]},
                )
            else:
                # Empty fixture keys means OIDC is intentionally unconfigured locally.
                raise TokenError("OIDC JWKS fixture has no keys configured")
        except TokenError:
            raise
        except Exception as exc:
            raise TokenError("Invalid OIDC bearer token") from exc

        email = str(claims.get("sub", "")).strip().lower()
        record = self.directory.get(email)
        if record is None:
            # Map IdP subject via email claim when present.
            email_claim = str(claims.get("email", "")).strip().lower()
            record = self.directory.get(email_claim) if email_claim else None
        if record is None:
            raise TokenError("Unknown user")
        return self.directory.to_user_context(record)
