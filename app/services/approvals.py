"""Approval application service for consequential tools."""

from __future__ import annotations

from typing import Any

from app.models import UserContext
from app.tools.broker import ToolBrokerError, ToolExecutionBroker


class ApprovalService:
    """List and decide pending consequential tool actions.

    Trust boundary: callers must already be authenticated; approval capability
    is decided by AuthorizationService, never by client role claims.
    """

    def __init__(self, broker: ToolExecutionBroker, store: Any, authorization: Any):
        self.broker = broker
        self.store = store
        self.authorization = authorization

    def list_pending(self, user: UserContext) -> list[dict[str, Any]]:
        """Return pending actions when the user may approve; else deny."""
        decision = self.authorization.can_approve_action(user, user.email)
        if not decision.allowed:
            # Detection: unauthorized approval-queue probe.
            self.broker.security_logger.emit(
                "unauthorized_resource_access",
                user_email=user.email,
                resource_type="approvals",
                endpoint="/api/approvals/pending",
                reason=decision.reason,
            )
            raise ToolBrokerError("Approval not authorized")
        return self.store.list_pending_actions()

    def decide(
        self, action_id: str, decision: str, user: UserContext
    ) -> dict[str, Any]:
        """Approve or deny a pending action via the tool broker."""
        result = self.broker.resolve_pending_action(
            action_id,
            decision,
            user,
            endpoint=f"/api/approvals/{action_id}",
        )
        payload = {
            "status": result.status,
            "tool_id": result.tool_id,
            "pending_action_id": result.pending_action_id,
        }
        if result.result is not None:
            payload["result"] = result.result
        return payload
