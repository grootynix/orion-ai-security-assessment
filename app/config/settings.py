"""Central configuration with fail-closed production validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Documented development-only signing key. Never used when ORION_ENV=production.
_DEV_ONLY_SIGNING_KEY = "orion-dev-only-signing-key-not-for-production"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings for Orion."""

    environment: str
    data_directory: Path
    database_path: Path
    token_signing_key: str
    token_issuer: str
    token_audience: str
    token_ttl_seconds: int
    enable_dev_idp: bool
    allow_data_reset: bool
    rate_limit_token_per_minute: int
    rate_limit_api_per_minute: int
    max_agent_steps: int
    max_tool_calls: int
    max_agent_duration_seconds: float
    email_recipient_allowlist_suffix: str
    model_provider: str
    approved_model_id: str
    production_token_ttl_seconds: int
    max_request_body_bytes: int
    oidc_jwks_url: str
    oidc_jwks_path: str
    oidc_issuer: str
    oidc_audience: str

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_non_production(self) -> bool:
        return self.environment in {"development", "test"}


class ConfigurationError(RuntimeError):
    """Raised when required security configuration is missing or unsafe."""


def load_settings(
    *,
    data_directory: Path | None = None,
    database_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> Settings:
    """Load and validate settings. Production fails closed on missing secrets."""

    env = environ if environ is not None else dict(os.environ)
    environment = env.get("ORION_ENV", "development").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise ConfigurationError(
            f"Unsupported ORION_ENV={environment!r}; "
            "expected development, test, or production"
        )

    configured_data = (
        data_directory
        if data_directory is not None
        else Path(env.get("ORION_DATA_DIR", PROJECT_ROOT / "data"))
    ).resolve()
    configured_database = (
        database_path
        if database_path is not None
        else Path(
            env.get("ORION_DATABASE_PATH", str(configured_data / "orion.sqlite3"))
        )
    ).resolve()

    signing_key = env.get("ORION_TOKEN_SIGNING_KEY", "").strip()
    enable_dev_idp_raw = env.get("ORION_ENABLE_DEV_IDP", "").strip().lower()
    allow_reset_raw = env.get("ORION_ALLOW_DATA_RESET", "").strip().lower()

    if environment == "production":
        if not signing_key:
            raise ConfigurationError(
                "ORION_TOKEN_SIGNING_KEY is required in production"
            )
        if enable_dev_idp_raw in {"1", "true", "yes"}:
            raise ConfigurationError(
                "ORION_ENABLE_DEV_IDP cannot be enabled in production"
            )
        enable_dev_idp = False
        if allow_reset_raw in {"1", "true", "yes"}:
            raise ConfigurationError(
                "ORION_ALLOW_DATA_RESET cannot be enabled in production"
            )
        allow_data_reset = False
    else:
        if not signing_key:
            signing_key = _DEV_ONLY_SIGNING_KEY
        # DevIdP defaults on for development/test unless explicitly disabled.
        if enable_dev_idp_raw == "":
            enable_dev_idp = True
        else:
            enable_dev_idp = enable_dev_idp_raw in {"1", "true", "yes"}
        allow_data_reset = allow_reset_raw in {"1", "true", "yes"}

    return Settings(
        environment=environment,
        data_directory=configured_data,
        database_path=configured_database,
        token_signing_key=signing_key,
        token_issuer=env.get("ORION_TOKEN_ISSUER", "orion-local"),
        token_audience=env.get("ORION_TOKEN_AUDIENCE", "orion-api"),
        token_ttl_seconds=int(
            env.get(
                "ORION_TOKEN_TTL_SECONDS",
                "900" if environment == "production" else "3600",
            )
        ),
        enable_dev_idp=enable_dev_idp,
        allow_data_reset=allow_data_reset,
        rate_limit_token_per_minute=int(
            env.get("ORION_RATE_LIMIT_TOKEN_PER_MINUTE", "20")
        ),
        rate_limit_api_per_minute=int(
            env.get("ORION_RATE_LIMIT_API_PER_MINUTE", "60")
        ),
        max_agent_steps=int(env.get("ORION_MAX_AGENT_STEPS", "5")),
        max_tool_calls=int(env.get("ORION_MAX_TOOL_CALLS", "3")),
        max_agent_duration_seconds=float(
            env.get("ORION_MAX_AGENT_DURATION_SECONDS", "10")
        ),
        email_recipient_allowlist_suffix=env.get(
            "ORION_EMAIL_ALLOWLIST_SUFFIX", "@example.test"
        ),
        model_provider=env.get("ORION_MODEL_PROVIDER", "fake").strip().lower(),
        approved_model_id=env.get("ORION_APPROVED_MODEL_ID", "fake-llm-v1"),
        production_token_ttl_seconds=int(
            env.get("ORION_PRODUCTION_TOKEN_TTL_SECONDS", "900")
        ),
        max_request_body_bytes=int(
            env.get("ORION_MAX_REQUEST_BODY_BYTES", str(64 * 1024))
        ),
        oidc_jwks_url=env.get("ORION_OIDC_JWKS_URL", "").strip(),
        oidc_jwks_path=env.get("ORION_OIDC_JWKS_PATH", "").strip(),
        oidc_issuer=env.get("ORION_OIDC_ISSUER", "").strip(),
        oidc_audience=env.get("ORION_OIDC_AUDIENCE", "").strip(),
    )
