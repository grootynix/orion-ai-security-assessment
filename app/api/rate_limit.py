"""In-process sliding-window rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request


class RateLimiter:
    """Sliding-window limiter for API abuse controls.

    Trust boundary: client identity for keys may be IP- or user-derived; limits
    are enforced server-side. Logging is additive and does not alter 429 outcomes.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(
        self,
        key: str,
        limit: int,
        window_seconds: float = 60.0,
        *,
        security_logger: Any | None = None,
        path: str | None = None,
        user_email: str | None = None,
    ) -> None:
        """Raise 429 when the key exceeds `limit` events in the window."""
        now = time.monotonic()
        bucket = self._events[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            if security_logger is not None:
                fields: dict[str, Any] = {
                    "rate_key": key,
                    "path": path or "",
                }
                if user_email:
                    fields["user_email"] = user_email
                security_logger.emit("rate_limit_exceeded", **fields)
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)


def client_key(request: Request, suffix: str) -> str:
    """Build a rate-limit bucket key from client host and a route suffix."""
    client = request.client.host if request.client else "unknown"
    return f"{client}:{suffix}"
