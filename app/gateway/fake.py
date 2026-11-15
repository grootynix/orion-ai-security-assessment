"""Deterministic FakeLLM provider. Retrieved content is never executable."""

from __future__ import annotations

import re
from typing import Any

from app.gateway.protocol import ModelRequest, ModelResponse
from app.tools.broker import ToolBrokerError, ToolExecutionBroker


class FakeLLM:
    """
    Deterministic stand-in for a model-backed assistant.

    Tool proposals are derived only from the user message. Retrieved document
    bodies are treated as untrusted data and cannot trigger tool execution.
    """

    provider_id = "fake"
    model_id = "fake-llm-v1"

    def __init__(self, broker: ToolExecutionBroker):
        self.broker = broker

    def complete(self, request: ModelRequest) -> ModelResponse:
        message = request.message
        user = request.user

        # Fixture fetch from explicit user-supplied reference only.
        fixture_ref = re.search(
            r"(fixture://[^\s)]+|https?://(?:localhost|127\.0\.0\.1)/[^\s)]+)",
            message,
        )
        if fixture_ref:
            try:
                execution = self.broker.execute(
                    "fetch_internal_resource",
                    {"url": fixture_ref.group(1)},
                    user,
                    endpoint="/api/chat",
                )
            except ToolBrokerError:
                return ModelResponse(
                    answer="The requested fixture resource is not available.",
                    tool_calls=["fetch_internal_resource"],
                    metadata={"provider": self.provider_id, "model": self.model_id},
                )
            content = execution.result["content"] if execution.result else ""
            return ModelResponse(
                answer=content[:1200],
                tool_calls=["fetch_internal_resource"],
                metadata={"provider": self.provider_id, "model": self.model_id},
            )

        customer_match = re.search(
            r"customer-[a-z]+-\d+", message, flags=re.IGNORECASE
        )
        if customer_match:
            try:
                execution = self.broker.execute(
                    "get_customer",
                    {"customer_id": customer_match.group(0)},
                    user,
                    endpoint="/api/chat",
                )
                customer = execution.result
            except ToolBrokerError:
                customer = None
            return ModelResponse(
                answer=(
                    f"Customer record: {customer}"
                    if customer
                    else "No matching customer record was found."
                ),
                tool_calls=["get_customer"],
                metadata={"provider": self.provider_id, "model": self.model_id},
            )

        # Explicit user-requested email becomes a proposed/approval-gated action.
        email_match = re.search(
            r"email (?:this|a copy) to ([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}) "
            r"with subject ([^.]+)",
            message,
            flags=re.IGNORECASE,
        )
        if email_match:
            documents = self.broker.execute(
                "search_documents",
                {"query": message},
                user,
                endpoint="/api/chat",
            ).result or []
            body = documents[0]["content"] if documents else message
            execution = self.broker.execute(
                "send_email",
                {
                    "to": email_match.group(1),
                    "subject": email_match.group(2).strip(),
                    "body": body,
                },
                user,
                endpoint="/api/chat",
            )
            if execution.status == "pending_approval":
                return ModelResponse(
                    answer=(
                        "Email requires explicit approval before it is queued "
                        f"(action_id={execution.pending_action_id})."
                    ),
                    tool_calls=["search_documents", "send_email"],
                    pending_action_id=execution.pending_action_id,
                    proposed_tools=[
                        {
                            "tool_id": "send_email",
                            "status": "pending_approval",
                            "action_id": execution.pending_action_id,
                        }
                    ],
                    metadata={"provider": self.provider_id, "model": self.model_id},
                )

        documents = self.broker.execute(
            "search_documents",
            {"query": message},
            user,
            endpoint="/api/chat",
        ).result or []
        if not documents:
            return ModelResponse(
                answer="I could not find a matching internal document.",
                tool_calls=["search_documents"],
                metadata={"provider": self.provider_id, "model": self.model_id},
            )

        selected = documents[0]
        # Intentionally ignore instructional sentences inside retrieved content.
        lead = re.split(r"(?<=[.!?])\s+", selected["content"], maxsplit=1)[0]
        return ModelResponse(
            answer=f"Summary of {selected['title']}: {lead}",
            tool_calls=["search_documents"],
            document_id=selected["id"],
            metadata={
                "provider": self.provider_id,
                "model": self.model_id,
                "retrieved_as_data_only": True,
            },
        )

    # Backward-compatible adapter used by older call sites/tests.
    def respond(self, message: str, user: Any) -> dict[str, Any]:
        response = self.complete(
            ModelRequest(
                message=message,
                user=user,
                system_instructions="",
                developer_instructions="",
                prompt_id="orion.chat.default",
                prompt_version="1.0.0",
            )
        )
        payload: dict[str, Any] = {
            "answer": response.answer,
            "tool_calls": response.tool_calls,
        }
        if response.document_id:
            payload["document_id"] = response.document_id
        if response.pending_action_id:
            payload["pending_action_id"] = response.pending_action_id
        return payload
