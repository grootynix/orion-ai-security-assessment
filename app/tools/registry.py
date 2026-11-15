"""Explicit tool allowlist registry."""

from __future__ import annotations

from app.tools.definitions import RiskLevel, SideEffect, ToolDefinition
from app.tools.implementations import ToolImplementations


class ToolRegistry:
    """Explicit allowlist of tool definitions; unknown IDs are denied."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        """Add or replace a tool definition on the allowlist."""
        self._tools[definition.tool_id] = definition

    def get(self, tool_id: str) -> ToolDefinition | None:
        """Return a definition or None when the tool is not allowlisted."""
        return self._tools.get(tool_id)

    def allowed_ids(self) -> set[str]:
        """Set of registered tool IDs."""
        return set(self._tools)

    def all(self) -> list[ToolDefinition]:
        """All registered definitions (order not significant)."""
        return list(self._tools.values())


def build_default_registry(implementations: ToolImplementations) -> ToolRegistry:
    """Wire the production allowlist to concrete ToolImplementations handlers."""
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            tool_id="search_documents",
            description="Search authorized documents",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 300}},
                "required": ["query"],
            },
            output_schema={"type": "array"},
            required_permission="documents:search",
            resource_scope="document",
            risk_level=RiskLevel.LOW,
            timeout_seconds=2.0,
            side_effect=SideEffect.READ,
            requires_approval=False,
            handler=implementations.search_documents,
        )
    )
    registry.register(
        ToolDefinition(
            tool_id="get_document",
            description="Retrieve one authorized document",
            input_schema={
                "type": "object",
                "properties": {"document_id": {"type": "string"}},
                "required": ["document_id"],
            },
            output_schema={"type": "object"},
            required_permission="documents:read",
            resource_scope="document",
            risk_level=RiskLevel.LOW,
            timeout_seconds=2.0,
            side_effect=SideEffect.READ,
            requires_approval=False,
            handler=implementations.get_document,
        )
    )
    registry.register(
        ToolDefinition(
            tool_id="get_customer",
            description="Retrieve an authorized customer record",
            input_schema={
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
            output_schema={"type": "object"},
            required_permission="customers:read",
            resource_scope="customer",
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=2.0,
            side_effect=SideEffect.READ,
            requires_approval=False,
            handler=implementations.get_customer,
        )
    )
    registry.register(
        ToolDefinition(
            tool_id="send_email",
            description="Queue a simulated outbound email to the local outbox",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "maxLength": 254},
                    "subject": {"type": "string", "maxLength": 200},
                    "body": {"type": "string", "maxLength": 10000},
                },
                "required": ["to", "subject", "body"],
            },
            output_schema={"type": "object"},
            required_permission="email:send",
            resource_scope="email",
            risk_level=RiskLevel.HIGH,
            timeout_seconds=2.0,
            side_effect=SideEffect.EXTERNAL_SIMULATED,
            requires_approval=True,
            handler=implementations.queue_email,
        )
    )
    registry.register(
        ToolDefinition(
            tool_id="fetch_internal_resource",
            description="Read an allowlisted local fixture resource",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string", "maxLength": 500}},
                "required": ["url"],
            },
            output_schema={"type": "object"},
            required_permission="fixtures:read",
            resource_scope="fixture",
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=2.0,
            side_effect=SideEffect.READ,
            requires_approval=False,
            handler=implementations.fetch_internal_resource,
        )
    )
    return registry
