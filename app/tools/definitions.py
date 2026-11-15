"""Tool metadata contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """Qualitative tool risk used for approval and monitoring policy."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SideEffect(str, Enum):
    """Declared side-effect class; WRITE/EXTERNAL require idempotency keys."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXTERNAL_SIMULATED = "external_simulated"


@dataclass(frozen=True)
class ToolDefinition:
    """Allowlisted tool contract: schema, permissions, risk, and handler."""

    tool_id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permission: str
    resource_scope: str
    risk_level: RiskLevel
    timeout_seconds: float
    side_effect: SideEffect
    requires_approval: bool
    audit_required: bool = True
    handler: Callable[..., Any] | None = field(default=None, compare=False, hash=False)
