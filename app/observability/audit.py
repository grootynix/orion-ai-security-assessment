"""Audit recording with argument redaction."""

from __future__ import annotations

import hashlib
from typing import Any

from app.observability.logging import SecurityLogger, get_correlation_id

SENSITIVE_KEYS = {
    "message",
    "body",
    "content",
    "password",
    "access_token",
    "token",
    "authorization",
}


def redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Minimize sensitive payloads while retaining forensic metadata."""

    redacted: dict[str, Any] = {}
    for key, value in arguments.items():
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS or "secret" in lowered or "password" in lowered:
            text = value if isinstance(value, str) else str(value)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            redacted[key] = {
                "redacted": True,
                "sha256_16": digest,
                "length": len(text),
            }
        elif isinstance(value, dict):
            redacted[key] = redact_arguments(value)
        else:
            redacted[key] = value
    return redacted


class AuditRecorder:
    """
    Persists redacted audit events and emits structured security logs.

    Fail-closed preference: sensitive fields are redacted by default. Raw prompts,
    secrets, and document bodies must not be stored unless an explicit future
    policy change is approved and tested.
    """

    def __init__(self, store: Any, security_logger: SecurityLogger | None = None):
        self.store = store
        self.security_logger = security_logger or SecurityLogger()

    def record(
        self,
        *,
        user_email: str,
        endpoint: str,
        tool_selected: str,
        arguments: dict[str, Any],
        status: str,
        authorization_decision: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        approval_status: str | None = None,
        model_version: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        """Persist a redacted audit row and mirror an `audit_event` log."""
        safe_arguments = redact_arguments(arguments)
        correlation_id = get_correlation_id()
        self.store.write_audit(
            user_email=user_email,
            endpoint=endpoint,
            tool_selected=tool_selected,
            arguments=safe_arguments,
            status=status,
            correlation_id=correlation_id,
            authorization_decision=authorization_decision,
            resource_type=resource_type,
            resource_id=resource_id,
            approval_status=approval_status,
            model_version=model_version,
            prompt_version=prompt_version,
        )
        self.security_logger.emit(
            "audit_event",
            user_email=user_email,
            endpoint=endpoint,
            tool_selected=tool_selected,
            status=status,
            authorization_decision=authorization_decision,
            resource_type=resource_type,
            resource_id=resource_id,
            approval_status=approval_status,
        )
