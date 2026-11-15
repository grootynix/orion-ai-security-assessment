"""Security headers, correlation IDs, and request body size limits."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.observability.logging import get_correlation_id, set_correlation_id


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers, correlation IDs, and body-size rejection.

    Trust boundary: Content-Length and X-Correlation-ID are client-supplied;
    size rejection fails closed. Detection emits are additive only.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID")
        set_correlation_id(correlation_id)

        settings = getattr(request.app.state, "settings", None)
        max_body = getattr(settings, "max_request_body_bytes", 64 * 1024)
        content_length = request.headers.get("content-length")
        security_logger = getattr(request.app.state, "security_logger", None)
        if content_length is not None:
            try:
                length = int(content_length)
                if length > max_body:
                    if security_logger is not None:
                        security_logger.emit(
                            "request_size_rejected",
                            path=str(request.url.path),
                            reason="body_too_large",
                            content_length=length,
                        )
                    return JSONResponse(
                        {"detail": "Request body too large"}, status_code=413
                    )
            except ValueError:
                if security_logger is not None:
                    security_logger.emit(
                        "request_size_rejected",
                        path=str(request.url.path),
                        reason="invalid_content_length",
                        content_length=content_length,
                    )
                return JSONResponse(
                    {"detail": "Invalid content length"}, status_code=400
                )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["X-Correlation-ID"] = get_correlation_id()
        return response
