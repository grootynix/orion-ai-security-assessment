# Detection Signals

Structured JSON security logs are emitted on stdout via `SecurityLogger`.
Ship them to a SIEM without embedding a SIEM dependency in Orion.

Every event includes `event_type` and `correlation_id`. Never log raw chat/email
bodies, bearer tokens, signing keys, or full retrieved document text.

Full use-case criteria and gap map: [fixes.md](../fixes.md#detection-logging-criteria-use-cases-and-fields).

| Signal | Trigger | Required fields | Suggested severity |
| --- | --- | --- | --- |
| `authentication_failure` | Missing/non-Bearer header or invalid token | `reason`, `path` | medium |
| `token_issuance_denied` | DevIdP disabled / production block | `reason` | medium |
| `token_issuance_anomaly` | Unknown synthetic user mint attempt | `reason`, `email` | medium |
| `rate_limit_exceeded` | Sliding-window API limit hit (429) | `path`, `rate_key`; optional `user_email` | medium |
| `request_size_rejected` | Declared body over ceiling or invalid Content-Length | `path`, `reason`; optional `content_length` | low |
| `cross_tenant_access_attempt` | Unauthorized customer access (API or broker) | `user_email`, `resource_id`, `reason`; optional `tool_id` / `endpoint` | high |
| `unauthorized_tool_attempt` | Non-allowlisted or denied tool (incl. document ACL) | `tool_id`, `user_email`, `reason` | high |
| `unauthorized_resource_access` | Audit / outbox / approval list or decide deny | `user_email`, `resource_type`, `path` or `endpoint`, `reason` | high |
| `unusual_email_recipient` | Recipient outside allowlist | `tool_id`, `user_email`, `recipient_domain` | high |
| `path_policy` | Traversal or non-allowlisted fixture | `user_email`, `reason`; redacted `url` / `fixture_ref` | high |
| `agent_loop_detected` | Repeated tool+args signatures | `user_email`, `signature` | medium |
| `excessive_tool_calls` | Tool budget exceeded | `user_email`, `tool_call_count` | medium |
| `abnormal_model_usage` | Per-user model quota exceeded | `user_email`, `reason` | medium |
| `agent_failed` | Orchestrator failure | `user_email`, `error` | medium |
| `tool_timeout` | Tool execution exceeded timeout | `tool_id`, `user_email`, `elapsed_seconds` | medium |
| `model_inference` | Normal inference telemetry | `user_email`, `provider`, `model`, `prompt_version`, `elapsed_seconds` | info |
| `audit_event` | Persisted redacted audit row | redacted audit fields | info |

Unexpected prompt/model version changes should be correlated by comparing
`prompt_version` / `model` fields on `model_inference` events against the
approved inventory and prompt registry hashes.
