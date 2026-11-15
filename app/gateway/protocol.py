"""Common model provider interface with explicit message-part separation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models import UserContext


@dataclass(frozen=True)
class MessageParts:
    """
    Strict separation of trust zones for model input.

    Retrieved context is data-tagged and must never be promoted to system or
    developer instructions.
    """

    system: str
    developer: str
    user: str
    retrieved_data: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "developer": self.developer,
            "user": self.user,
            "retrieved_data": list(self.retrieved_data),
        }


@dataclass
class ModelRequest:
    message: str
    user: UserContext
    system_instructions: str
    developer_instructions: str
    prompt_id: str
    prompt_version: str
    correlation_id: str = ""
    parts: MessageParts | None = None


@dataclass
class ModelResponse:
    answer: str
    tool_calls: list[str] = field(default_factory=list)
    proposed_tools: list[dict[str, Any]] = field(default_factory=list)
    document_id: str | None = None
    pending_action_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieved_as_data_only: bool = True


class LanguageModel(Protocol):
    provider_id: str
    model_id: str

    def complete(self, request: ModelRequest) -> ModelResponse: ...
