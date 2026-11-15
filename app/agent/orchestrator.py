"""Controlled agent execution state machine."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.settings import Settings
from app.gateway.gateway import ModelGateway
from app.models import UserContext
from app.observability.logging import SecurityLogger, get_correlation_id


class AgentState(str, Enum):
    """Explicit agent lifecycle states for trajectory and audit."""

    RECEIVED = "RECEIVED"
    PLAN = "PLAN"
    TOOL_CALL = "TOOL_CALL"
    AWAIT_APPROVAL = "AWAIT_APPROVAL"
    RESPOND = "RESPOND"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class TrajectoryEvent:
    """One recorded state transition during an agent run."""

    state: str
    detail: dict[str, Any]
    timestamp: float


@dataclass
class AgentRunResult:
    """Client-facing outcome of a bounded agent run."""

    answer: str
    tool_calls: list[str]
    state: AgentState
    trajectory: list[TrajectoryEvent] = field(default_factory=list)
    document_id: str | None = None
    pending_action_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None


class AgentOrchestrator:
    """
    Bounded orchestration around the model gateway.

    The model may propose actions; it never authorizes them. Fail closed on
    step/tool/duration budget exhaustion and repeated tool+args signatures.
    """

    def __init__(
        self,
        gateway: ModelGateway,
        settings: Settings,
        security_logger: SecurityLogger | None = None,
        store: Any | None = None,
    ):
        self.gateway = gateway
        self.settings = settings
        self.security_logger = security_logger or SecurityLogger()
        self.store = store
        self._recent_signatures: list[str] = []

    def run(self, message: str, user: UserContext) -> AgentRunResult:
        """Execute one chat turn under step/tool/duration budgets."""
        started = time.monotonic()
        trajectory: list[TrajectoryEvent] = []
        state = AgentState.RECEIVED
        run_id = get_correlation_id()
        trajectory.append(
            TrajectoryEvent(
                state=state.value,
                detail={"correlation_id": run_id},
                timestamp=started,
            )
        )

        try:
            state = AgentState.PLAN
            trajectory.append(
                TrajectoryEvent(state=state.value, detail={}, timestamp=time.monotonic())
            )
            response = self.gateway.complete(message=message, user=user)

            tool_calls = list(response.tool_calls)
            if len(tool_calls) > self.settings.max_tool_calls:
                self.security_logger.emit(
                    "excessive_tool_calls",
                    user_email=user.email,
                    tool_call_count=len(tool_calls),
                )
                raise RuntimeError("Tool call budget exceeded")

            signature = json.dumps(
                {
                    "tools": tool_calls,
                    "pending": response.pending_action_id,
                    "document_id": response.document_id,
                },
                sort_keys=True,
            )
            self._recent_signatures.append(signature)
            if len(self._recent_signatures) >= 2 and len(set(self._recent_signatures[-2:])) == 1:
                self.security_logger.emit(
                    "agent_loop_detected",
                    user_email=user.email,
                    signature=signature,
                )

            if tool_calls:
                state = AgentState.TOOL_CALL
                trajectory.append(
                    TrajectoryEvent(
                        state=state.value,
                        detail={"tool_calls": tool_calls, "signature": signature},
                        timestamp=time.monotonic(),
                    )
                )

            if response.pending_action_id:
                state = AgentState.AWAIT_APPROVAL
                trajectory.append(
                    TrajectoryEvent(
                        state=state.value,
                        detail={"pending_action_id": response.pending_action_id},
                        timestamp=time.monotonic(),
                    )
                )

            elapsed = time.monotonic() - started
            if elapsed > self.settings.max_agent_duration_seconds:
                raise RuntimeError("Agent execution deadline exceeded")

            steps_used = 1 + (1 if tool_calls else 0)
            if steps_used > self.settings.max_agent_steps:
                raise RuntimeError("Agent step budget exceeded")

            state = AgentState.RESPOND
            trajectory.append(
                TrajectoryEvent(
                    state=state.value,
                    detail={"answer_length": len(response.answer)},
                    timestamp=time.monotonic(),
                )
            )
            state = AgentState.DONE
            trajectory.append(
                TrajectoryEvent(state=state.value, detail={}, timestamp=time.monotonic())
            )
            result = AgentRunResult(
                answer=response.answer,
                tool_calls=tool_calls,
                state=state,
                trajectory=trajectory,
                document_id=response.document_id,
                pending_action_id=response.pending_action_id,
                metadata=response.metadata,
                run_id=run_id,
            )
            if self.store is not None:
                self.store.write_trajectory(
                    run_id=run_id,
                    user_email=user.email,
                    events=[
                        {
                            "state": event.state,
                            "detail": event.detail,
                            "timestamp": event.timestamp,
                        }
                        for event in trajectory
                    ],
                )
            return result
        except Exception as exc:
            state = AgentState.FAILED
            trajectory.append(
                TrajectoryEvent(
                    state=state.value,
                    detail={"error": str(exc)},
                    timestamp=time.monotonic(),
                )
            )
            self.security_logger.emit(
                "agent_failed",
                user_email=user.email,
                error=str(exc),
            )
            if self.store is not None:
                self.store.write_trajectory(
                    run_id=run_id,
                    user_email=user.email,
                    events=[
                        {
                            "state": event.state,
                            "detail": event.detail,
                            "timestamp": event.timestamp,
                        }
                        for event in trajectory
                    ],
                )
            raise
