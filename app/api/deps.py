"""FastAPI authentication dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.auth.tokens import TokenError
from app.models import UserContext
from app.observability.logging import SecurityLogger


def get_app_state(request: Request):
    """Return the FastAPI app.state container for dependency injection."""
    return request.app.state


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> UserContext:
    """Resolve the caller from a Bearer token; identity is rebound server-side.

    Trust boundary: client Authorization header is untrusted. Missing or
    malformed schemes are logged as authentication_failure before 401.
    """
    logger: SecurityLogger = request.app.state.security_logger
    if not authorization or not authorization.startswith("Bearer "):
        # Detection: probe or missing credential (additive log; still 401).
        logger.emit(
            "authentication_failure",
            reason="missing_bearer",
            path=str(request.url.path),
        )
        raise HTTPException(
            status_code=401,
            detail="A bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    provider = request.app.state.identity_provider
    try:
        return provider.authenticate_bearer(token)
    except TokenError as exc:
        logger.emit(
            "authentication_failure",
            reason=str(exc),
            path=str(request.url.path),
        )
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc


UserDependency = Annotated[UserContext, Depends(current_user)]
