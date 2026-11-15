# Agent and Tool Security

## Tool registry

Every tool declares identifier, schemas, permission, resource scope, risk, timeout, side-effect class, and approval requirement.

Allowlisted tools:

- `search_documents`
- `get_document`
- `get_customer`
- `send_email` (approval required)
- `fetch_internal_resource`

## Execution broker

Order of enforcement:

1. Allowlist check
2. Argument schema validation
3. Authorization and recipient policy
4. Approval gate for consequential actions
5. Timed execution
6. Audit event

Idempotency keys prevent duplicate side effects for approved actions.

## FakeLLM behavior

FakeLLM proposes tools from the **user message** only. Retrieved document bodies are never scanned for executable instructions. This removes the deterministic document-content-triggered email vulnerability while preserving useful regression coverage via the seeded instructional document.

## Agent bounds

`AgentOrchestrator` states: `RECEIVED → PLAN → TOOL_CALL → AWAIT_APPROVAL → RESPOND → DONE|FAILED`

Limits: max steps, max tool calls, max duration, loop detection signals, trajectory recording.
