"""Chat application service."""

from __future__ import annotations

from typing import Any

from app.agent.orchestrator import AgentOrchestrator
from app.models import UserContext
from app.observability.audit import AuditRecorder


class ChatService:
    """Coordinates agent execution and audit recording for chat requests."""

    def __init__(self, orchestrator: AgentOrchestrator, audit: AuditRecorder):
        self.orchestrator = orchestrator
        self.audit = audit

    def handle(self, message: str, user: UserContext) -> dict[str, Any]:
        """Run the agent and record a redacted chat audit event."""
        result = self.orchestrator.run(message, user)
        self.audit.record(
            user_email=user.email,
            endpoint="/api/chat",
            tool_selected="chat",
            arguments={"message": message},
            status="success",
            model_version=result.metadata.get("model"),
            prompt_version=result.metadata.get("prompt_version"),
        )
        payload: dict[str, Any] = {
            "answer": result.answer,
            "tool_calls": result.tool_calls,
            "agent_state": result.state.value,
        }
        if result.document_id:
            payload["document_id"] = result.document_id
        if result.pending_action_id:
            payload["pending_action_id"] = result.pending_action_id
        return payload
