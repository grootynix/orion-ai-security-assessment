"""Central tool execution broker with authorization and approval gates."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from app.authorization.policy import AuthorizationService
from app.config.settings import Settings
from app.models import UserContext
from app.observability.audit import AuditRecorder
from app.observability.logging import SecurityLogger
from app.persistence.store import Store
from app.tools.definitions import SideEffect
from app.tools.registry import ToolRegistry


class ToolBrokerError(Exception):
    """
    Raised when a tool invocation is rejected or fails policy checks.

    Trust boundary: models may propose tool calls; this broker alone authorizes
    and executes them. Fail closed on unknown tools, bad args, or authz denial.
    """

    def __init__(self, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ToolExecutionResult:
    """Outcome of broker.execute / resolve_pending_action."""

    tool_id: str
    status: str
    result: Any = None
    pending_action_id: str | None = None
    error: str | None = None


class ToolExecutionBroker:
    """
    Sole execution boundary for tools.

    Flow: allowlist → argument validation → authorization → approval → execute.
    Side-effect tools always use an idempotency key to prevent duplicate writes.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        authorization: AuthorizationService,
        store: Store,
        settings: Settings,
        audit: AuditRecorder,
        security_logger: SecurityLogger | None = None,
    ):
        self.registry = registry
        self.authorization = authorization
        self.store = store
        self.settings = settings
        self.audit = audit
        self.security_logger = security_logger or SecurityLogger()
        self._idempotency: dict[str, ToolExecutionResult] = {}

    @staticmethod
    def _derive_idempotency_key(
        tool_id: str, arguments: dict[str, Any], user_email: str
    ) -> str:
        canonical = json.dumps(
            {"tool": tool_id, "args": arguments, "user": user_email},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"auto:{tool_id}:{digest}"

    def _validate_arguments(
        self, tool_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        definition = self.registry.get(tool_id)
        assert definition is not None
        schema = definition.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        for key in required:
            if key not in arguments:
                raise ToolBrokerError(f"Missing required argument: {key}", status_code=400)
        cleaned: dict[str, Any] = {}
        for key, value in arguments.items():
            if key not in properties:
                raise ToolBrokerError(f"Unexpected argument: {key}", status_code=400)
            prop = properties[key]
            if prop.get("type") == "string":
                if not isinstance(value, str):
                    raise ToolBrokerError(f"Argument {key} must be a string", status_code=400)
                max_length = prop.get("maxLength")
                if max_length is not None and len(value) > max_length:
                    raise ToolBrokerError(
                        f"Argument {key} exceeds max length", status_code=400
                    )
            cleaned[key] = value
        return cleaned

    def _authorize_tool(
        self, tool_id: str, user: UserContext, arguments: dict[str, Any]
    ) -> None:
        if tool_id == "send_email":
            decision = self.authorization.can_send_email(user)
            if not decision.allowed:
                self.security_logger.emit(
                    "unauthorized_tool_attempt",
                    tool_id=tool_id,
                    user_email=user.email,
                    reason=decision.reason,
                )
                raise ToolBrokerError("Email send not authorized")
            recipient = str(arguments.get("to", "")).lower()
            suffix = self.settings.email_recipient_allowlist_suffix.lower()
            if not recipient.endswith(suffix):
                self.security_logger.emit(
                    "unusual_email_recipient",
                    tool_id=tool_id,
                    user_email=user.email,
                    recipient_domain=recipient.split("@")[-1]
                    if "@" in recipient
                    else "invalid",
                )
                raise ToolBrokerError(
                    "Recipient is outside the approved allowlist", status_code=400
                )
            return

        if tool_id == "get_customer":
            customer = self.store.customer(str(arguments["customer_id"]))
            if customer is None:
                return
            decision = self.authorization.can_read_customer(user, customer)
            if not decision.allowed:
                self.security_logger.emit(
                    "cross_tenant_access_attempt",
                    tool_id=tool_id,
                    user_email=user.email,
                    resource_id=arguments.get("customer_id"),
                    reason=decision.reason,
                )
                raise ToolBrokerError("Customer access denied")
            return

        if tool_id == "get_document":
            document = self.store.document(str(arguments["document_id"]))
            if document is None:
                return
            decision = self.authorization.can_read_document(user, document)
            if not decision.allowed:
                # Detection: tool-path document ACL deny (additive).
                self.security_logger.emit(
                    "unauthorized_tool_attempt",
                    tool_id=tool_id,
                    user_email=user.email,
                    reason=decision.reason,
                )
                raise ToolBrokerError("Document access denied")
            return

        # Remaining allowlisted tools are permitted for authenticated users.
        return

    def execute(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        user: UserContext,
        *,
        endpoint: str,
        auto_approve: bool = False,
        idempotency_key: str | None = None,
    ) -> ToolExecutionResult:
        """Authorize and run an allowlisted tool; may return pending_approval."""
        definition = self.registry.get(tool_id)
        if definition is None:
            self.security_logger.emit(
                "unauthorized_tool_attempt",
                tool_id=tool_id,
                user_email=user.email,
                reason="not_allowlisted",
            )
            raise ToolBrokerError("Tool is not allowlisted")

        cleaned = self._validate_arguments(tool_id, arguments)
        self._authorize_tool(tool_id, user, cleaned)

        if definition.side_effect in {SideEffect.WRITE, SideEffect.EXTERNAL_SIMULATED}:
            idempotency_key = idempotency_key or self._derive_idempotency_key(
                tool_id, cleaned, user.email
            )
        if idempotency_key and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]

        if definition.requires_approval and not auto_approve:
            action_id = self.store.create_pending_action(tool_id, cleaned, user.email)
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected=tool_id,
                arguments=cleaned,
                status="pending_approval",
                authorization_decision="awaiting_approval",
                resource_type=definition.resource_scope,
                approval_status="pending",
            )
            result = ToolExecutionResult(
                tool_id=tool_id,
                status="pending_approval",
                pending_action_id=action_id,
            )
            if idempotency_key:
                self._idempotency[idempotency_key] = result
            return result

        if definition.handler is None:
            raise ToolBrokerError("Tool handler is not configured")

        started = time.monotonic()
        try:
            # Handlers accept named user/endpoint kwargs for audited tools.
            if tool_id == "search_documents":
                output = definition.handler(
                    cleaned["query"], user, endpoint=endpoint
                )
            elif tool_id == "get_document":
                output = definition.handler(
                    cleaned["document_id"], user, endpoint=endpoint
                )
            elif tool_id == "get_customer":
                output = definition.handler(
                    cleaned["customer_id"], user, endpoint=endpoint
                )
            elif tool_id == "send_email":
                output = definition.handler(
                    cleaned["to"],
                    cleaned["subject"],
                    cleaned["body"],
                    user,
                    endpoint=endpoint,
                )
            elif tool_id == "fetch_internal_resource":
                output = definition.handler(
                    cleaned["url"], user, endpoint=endpoint
                )
            else:
                raise ToolBrokerError("Unsupported tool handler binding")
        except ToolBrokerError:
            raise
        except Exception as exc:
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected=tool_id,
                arguments=cleaned,
                status="failure",
                authorization_decision="execution_error",
                resource_type=definition.resource_scope,
            )
            raise ToolBrokerError(str(exc), status_code=400) from exc

        elapsed = time.monotonic() - started
        if elapsed > definition.timeout_seconds:
            self.security_logger.emit(
                "tool_timeout",
                tool_id=tool_id,
                user_email=user.email,
                elapsed_seconds=elapsed,
            )

        result = ToolExecutionResult(
            tool_id=tool_id, status="executed", result=output
        )
        if idempotency_key:
            self._idempotency[idempotency_key] = result
        return result

    def resolve_pending_action(
        self,
        action_id: str,
        decision: str,
        actor: UserContext,
        *,
        endpoint: str,
    ) -> ToolExecutionResult:
        """Approve or deny a pending consequential action after authz check."""
        pending = self.store.get_pending_action(action_id)
        if pending is None:
            raise ToolBrokerError("Pending action not found", status_code=404)
        if pending["status"] != "pending":
            raise ToolBrokerError("Pending action already decided", status_code=409)

        authz = self.authorization.can_approve_action(actor, pending["requested_by"])
        if not authz.allowed:
            self.security_logger.emit(
                "unauthorized_resource_access",
                user_email=actor.email,
                resource_type="pending_action",
                endpoint=endpoint,
                reason=authz.reason,
            )
            raise ToolBrokerError("Approval not authorized")

        if decision == "deny":
            self.store.decide_pending_action(action_id, "denied", actor.email)
            self.audit.record(
                user_email=actor.email,
                endpoint=endpoint,
                tool_selected=pending["tool_name"],
                arguments=pending["arguments"],
                status="denied",
                authorization_decision=authz.reason,
                approval_status="denied",
                resource_type="pending_action",
                resource_id=action_id,
            )
            return ToolExecutionResult(
                tool_id=pending["tool_name"],
                status="denied",
                pending_action_id=action_id,
            )

        self.store.decide_pending_action(action_id, "approved", actor.email)
        return self.execute(
            pending["tool_name"],
            pending["arguments"],
            actor,
            endpoint=endpoint,
            auto_approve=True,
            idempotency_key=f"approved:{action_id}",
        )
