"""Structured security logging with correlation IDs."""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any

_correlation_id: ContextVar[str] = ContextVar("orion_correlation_id", default="")


def set_correlation_id(value: str | None = None) -> str:
    """Bind a request correlation ID (client-supplied or generated)."""
    correlation_id = value or str(uuid.uuid4())
    _correlation_id.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str:
    """Return the current correlation ID, creating one if absent."""
    current = _correlation_id.get()
    if current:
        return current
    return set_correlation_id()


class SecurityLogger:
    """Emits structured JSON security events to the application logger.

    Trust boundary: field values may include user identifiers and reason codes
    but must never include secrets, bearer tokens, or raw message bodies.
    """

    def __init__(self, name: str = "orion.security"):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)
            self._logger.propagate = False

    def emit(self, event_type: str, **fields: Any) -> None:
        """Write one detection-oriented JSON event with correlation_id."""
        payload = {
            "event_type": event_type,
            "correlation_id": get_correlation_id(),
            **fields,
        }
        self._logger.info(json.dumps(payload, sort_keys=True, default=str))
