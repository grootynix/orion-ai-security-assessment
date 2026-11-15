# Security Architecture

Final modular-monolith security design after the local hardening assessment.
Production sequencing beyond this baseline: [prod-plan.md](../prod-plan.md).

## Trust boundaries

1. **Browser / untrusted client** → API
2. **Authenticated principal** → authorization policy
3. **Model / FakeLLM proposals** → tool execution broker
4. **Retrieved documents** → model context as data only
5. **Fixture filesystem** → allowlisted paths under `data/fixtures`
6. **Production configuration** → fail closed when secrets/DevIdP are misconfigured

## Final architecture (security design)

```mermaid
flowchart TB
  subgraph untrusted [UntrustedClient]
    Browser[Browser_SPA]
  end

  subgraph edge [EdgeAndAPI]
    MW[SecurityHeaders_Correlation_BodyLimit]
    RL[RateLimiter]
    Routes[API_Routes]
    Deps[BearerAuth_Dependency]
  end

  subgraph identity [IdentityBoundary]
    TokenSvc[TokenService_HS256]
    Directory[IdentityDirectory_Rebind]
    DevIdP[DevIdP_NonProdOnly]
    OIDC[OIDC_Stub_FailClosed]
    Revoke[JTI_Revocation]
  end

  subgraph authz [AuthorizationBoundary]
    Policy[AuthorizationService_DenyByDefault]
  end

  subgraph appServices [ApplicationServices]
    ChatSvc[ChatService]
    DocSvc[DocumentService]
    ApprovalSvc[ApprovalService]
  end

  subgraph aiPlane [AI_ControlPlane]
    Orch[AgentOrchestrator_Budgets_Loops]
    Gateway[ModelGateway_Inventory_Quota]
    Prompts[PromptRegistry_ApprovedOnly]
    FakeLLM[FakeLLM_DataOnly]
    Retrieval[RetrievalService_AuthzFilter]
  end

  subgraph toolPlane [ToolTrustBoundary]
    Broker[ToolExecutionBroker]
    Registry[Allowlist_Registry]
    Impl[ToolImplementations]
    Pending[Approval_Gate_Email]
  end

  subgraph dataPlane [DataAndObservability]
    Store[SQLite_Store]
    Audit[AuditRecorder_Redacted_HashChain]
    SecLog[SecurityLogger_DetectionEvents]
    Fixtures[FixturesRoot_PathContainment]
    Outbox[LocalEmailOutbox]
  end

  Browser --> MW
  MW --> RL
  RL --> Routes
  Routes --> Deps
  Deps --> TokenSvc
  TokenSvc --> Revoke
  TokenSvc --> Directory
  DevIdP -.-> TokenSvc
  OIDC -.-> Directory
  Routes --> ChatSvc
  Routes --> DocSvc
  Routes --> ApprovalSvc
  ChatSvc --> Orch
  Orch --> Gateway
  Gateway --> Prompts
  Gateway --> FakeLLM
  FakeLLM --> Retrieval
  Retrieval --> Policy
  Orch --> Broker
  ApprovalSvc --> Broker
  Broker --> Registry
  Broker --> Policy
  Broker --> Pending
  Broker --> Impl
  Impl --> Policy
  Impl --> Store
  Impl --> Fixtures
  Impl --> Outbox
  Pending --> Store
  Routes --> Policy
  ChatSvc --> Audit
  Broker --> Audit
  Impl --> Audit
  Audit --> Store
  Audit --> SecLog
  Broker --> SecLog
  Deps --> SecLog
  Orch --> SecLog
  Gateway --> SecLog
```

### Trust-boundary callouts on the diagram

| Zone | Trusted for | Never trusted for |
| --- | --- | --- |
| UntrustedClient | Nothing security-critical | Roles, projects, tenant IDs, raw tokens as proof of authz |
| EdgeAndAPI | Transport limits, correlation, route wiring | Business authorization decisions |
| IdentityBoundary | Signature, iss/aud/exp, directory rebind | Client-embedded role claims |
| AuthorizationBoundary | Allow/deny decisions | Model or UI suggestions |
| AI_ControlPlane | Bounded inference and proposals | Executing tools or granting permissions |
| ToolTrustBoundary | Allowlist, schema, approval, execution | Document text as instructions |
| DataAndObservability | Persistence and detection telemetry | Storing raw secrets/chat bodies |

## Request path (security-relevant)

```mermaid
sequenceDiagram
  participant Client
  participant API
  participant Auth
  participant Orch
  participant Gateway
  participant Broker
  participant AuthZ
  participant Audit

  Client->>API: Bearer JWT plus request
  API->>Auth: Verify signature iss aud exp jti
  Auth->>Auth: Rebind role projects from directory
  API->>Orch: Chat or tool route
  Orch->>Gateway: complete with MessageParts
  Gateway->>Gateway: Approved prompt and model only
  Note over Gateway: retrieved_data is data zone not system
  Gateway-->>Orch: Proposed answer or tool calls
  Orch->>Broker: execute allowlisted tool
  Broker->>AuthZ: can_read or can_send decisions
  alt Denied
    Broker-->>Audit: SecurityLogger emit plus redacted audit
    Broker-->>Orch: ToolBrokerError
  else Allowed or pending approval
    Broker-->>Audit: Redacted audit event
    Broker-->>Orch: Result or pending_action_id
  end
  Orch-->>Client: Answer without HTML render
```

## Controls

- Signed HS256 JWTs with `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`
- Server-side identity rebinding (client role claims ignored)
- DevIdP isolated to non-production with explicit enablement
- Central `AuthorizationService` for documents, customers, email, audit, approvals
- Tool allowlist, schema validation, approval for `send_email`
- Rate limiting on token and sensitive API paths
- Security response headers and CSP
- Redacted audit arguments, hash-chained audit rows, structured security logs
- Container non-root, read-only root filesystem, dropped capabilities

## Explicit non-claims

- FakeLLM document-instruction removal is not proof of real LLM robustness.
- Local fixture reads are not SSRF.
- SQLite outbox queuing is not external email delivery or exfiltration.
- This diagram describes the **assessed local architecture**; enterprise OIDC,
  shared rate limits, and real-model guardrails remain in [prod-plan.md](../prod-plan.md).
