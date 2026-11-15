# Orion Security Fixes — What Changed and Why

This document records the security transformation completed on  
`feature/orion-production-security-hardening` (working tree carried forward onto  
`feature/orion-security-hardening-next`).

- **Before reference:** git tag `baseline/pre-hardening` (untouched inherited app)
- **After reference:** hardened modular monolith in the current working tree
- **Evidence:** local `pytest` (29 passed), `ruff` clean, `pip-audit` clean
- **Scope note:** FakeLLM remains deterministic. Local email is SQLite outbox only. Fixture fetch is local filesystem containment, not SSRF.

---

## Executive summary

| Dimension | Before | After |
| --- | --- | --- |
| Auth tokens | Unsigned base64 JSON | Signed HS256 JWT with `iss`/`aud`/`exp`/`nbf`/`iat`/`jti` |
| Roles / projects | Trusted from client token | Rebound from server `IdentityDirectory` |
| Token issuance | Open `POST /api/token` for known emails | DevIdP only; disabled / fail-closed in production |
| FakeLLM | Executed instructions found in retrieved docs | Treats retrieved text as data only |
| Customer access | Any authenticated user could read any customer | Assignee or manager+ object-level authz |
| File fetch | Contained under `data/`, so `../` escaped fixtures | Allowlisted fixtures under `data/fixtures` only |
| Email | Any user, any recipient, no approval | Manager+, allowlisted recipients, pending approval |
| Audit | Raw chat/email bodies stored | Redacted arguments + structured security logs |
| CI / deps | Soft `pip-audit`, no lockfile | Lockfile + enforced audit/lint/SAST workflow |
| Container | Weak compose hardening | Multi-stage, non-root, read-only root, caps dropped |
| Tests | 4 happy-path API tests | 29 tests including security regressions + eval gate |
| Architecture | Flat modules in `app/*.py` | Modular packages with broker, gateway, authz, prompts |

---

## Finding-by-finding fix log

### 1. Unsigned, forgeable authentication tokens

**Before**  
Tokens were `base64url(JSON UserContext)` with no signature, expiry, issuer, or audience. Anyone who could craft matching JSON could mint a bearer token.

**Why we fixed it**  
Without cryptographic integrity, authentication is theater. An attacker can impersonate any synthetic user, including administrators.

**How we secured it**  
- Introduced `TokenService` (`app/auth/tokens.py`) issuing/verifying HS256 JWTs  
- Required claims: `sub`, `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`  
- Reject unexpected algorithms (including `alg=none`)  
- Signing key from `ORION_TOKEN_SIGNING_KEY` (required in production)

**After**  
Forged unsigned/base64 tokens and expired/wrong-issuer/wrong-audience tokens are rejected (`401`). Covered by `tests/test_security_auth.py`.

---

### 2. Authorization claims trusted from token contents

**Before**  
`current_user` only checked that `email` existed in `SYNTHETIC_USERS`, then returned the token’s `role` and `projects` as-is. A forged/escalated token for `alice@example.test` with `role=administrator` worked.

**Why we fixed it**  
Client-controlled authorization claims enable privilege escalation even when tokens are signed, if roles are taken from the token payload.

**How we secured it**  
- After signature verification, load canonical identity from `IdentityDirectory`  
- Rebind `role` / `projects` / `tenant_id` server-side  
- Central `AuthorizationService` enforces deny-by-default decisions for documents, customers, email, audit, and approvals

**After**  
A correctly signed JWT that embeds admin claims for an employee still cannot access `/api/audit`. Covered by role-escalation regression tests.

---

### 3. Document-content-triggered email in FakeLLM

**Before**  
After retrieval, FakeLLM regex-scanned **document content**. The seeded `doc-service-launch` memo instructed: email the document to `quality-review@example.test`. FakeLLM called `send_email` automatically and wrote to the local outbox.

**Why we fixed it**  
Retrieved content is untrusted data. Treating document text as executable instructions is a deterministic content-to-tool execution flaw (prompt-injection analogue for FakeLLM). This is **not** claimed as proof of real-LLM exploitation.

**How we secured it**  
- Rewrote FakeLLM (`app/gateway/fake.py`) to propose tools from the **user message** only  
- Removed document-body instruction scanning  
- Email side effects must pass the tool broker + approval gate  
- Kept the instructional document as a regression fixture

**After**  
Queries that retrieve the launch playbook summarize it and do **not** queue email. Covered by `test_document_content_cannot_trigger_email` and eval case `prompt-injection-document-email`.

---

### 4. Missing object-level authorization on customer records

**Before**  
`get_customer` returned any customer by ID for any authenticated user. `assigned_to` existed in seed data but was unused for ACL. Documents had ACL; customers did not.

**Why we fixed it**  
Without object-level authorization, employees can read peer/manager customer records by changing an identifier (IDOR).

**How we secured it**  
- `AuthorizationService.can_read_customer` allows assignee or manager+ only  
- Enforced in tool implementations and again in the broker  
- API returns `404` on deny to avoid existence leakage for unauthorized readers

**After**  
Alice can read `customer-cinder-104` but not `customer-orbit-219`. Covered by authz tests and eval case `cross-tenant-customer-denied`.

---

### 5. Path traversal from fixtures into broader `data/`

**Before**  
`fetch_internal_resource` resolved under `data/fixtures/...` but containment checked against `data/`. Paths like `../test_credentials.json` stayed inside `data/` and were readable. This was **local file read**, not SSRF.

**Why we fixed it**  
A constrained local reader that escapes the intended fixture root exposes credential-shaped fixtures and other data files.

**How we secured it**  
- Explicit fixture ID allowlist (`fixture://quarterly-brief`, etc.)  
- Canonical path containment under `data/fixtures` only  
- Reject traversal, symlink escape, and unexpected file types  
- Prefer `fixture://` identifiers over arbitrary URL-to-filesystem mapping

**After**  
`http://localhost/../test_credentials.json` does not return secrets. Covered by path-traversal tests and eval case `path-traversal-rejected`.

---

### 6. Unrestricted email recipients and insufficient approval

**Before**  
Any authenticated user could `POST /api/tools/send-email` to any recipient. No allowlist, no role gate in the tool path, no human approval. Delivery was local SQLite outbox only (not external SMTP).

**Why we fixed it**  
Consequential side effects must not execute solely because a model/API caller asked. Unrestricted recipients enable simulated data exfil paths even with a local outbox.

**How we secured it**  
- Tool broker marks `send_email` as approval-required  
- Manager+ role required  
- Recipient must end with configured allowlist suffix (`@example.test`)  
- Pending actions stored; approve/deny via `/api/approvals/{action_id}`  
- Outbox write occurs only after approval

**After**  
Employees are denied; managers create pending actions; external domains are rejected; approved messages appear in outbox. Covered by API + security tests.

---

### 7. Sensitive test credential-like fixtures in the repo

**Before**  
`data/test_credentials.json` and `data/fixtures/legacy_sample.env` contained password/token-shaped strings (marked synthetic, but still risky and fetchable via finding 5).

**Why we fixed it**  
Credential-shaped material trains bad habits, trips secret scanners, and becomes useful to attackers when combined with path escape.

**How we secured it**  
- Replaced values with explicit `NOT-A-SECRET-PLACEHOLDER` strings  
- Kept fixtures only for local regression realism  
- Combined with fixture allowlist so `test_credentials.json` is not tool-fetchable

**After**  
Repo fixtures are clearly non-secrets; path escape no longer exposes them through the tool.

---

### 8. Sensitive conversation data in audit logs

**Before**  
Chat audits stored raw `message` text. Email audits stored full `body`. Admins could dump sensitive content via `/api/audit`.

**Why we fixed it**  
Audit systems should reconstruct security-relevant events without becoming a second copy of sensitive conversations by default.

**How we secured it**  
- `redact_arguments()` stores `{redacted, sha256_16, length}` for sensitive keys  
- Extended audit schema with correlation IDs, authz decision, approval status, model/prompt versions  
- Structured `SecurityLogger` emits JSON security events without raw bodies

**After**  
Audit rows for chat no longer contain raw user messages. Covered by `test_audit_arguments_are_redacted`.

---

### 9. Dependency auditing not enforced in CI

**Before**  
`.github/workflows/ci.yml` ran `pip-audit` with `continue-on-error: true`, so failures did not fail the job.

**Why we fixed it**  
A scanner that cannot fail the build is monitoring theater, not a control.

**How we secured it**  
- Removed soft-fail behavior  
- CI runs pytest, ruff, bandit, pip-audit, gitleaks, trivy, checkov, syft  
- Local `make audit` uses the lockfile

**After**  
Known vulnerable dependencies fail the gate. Local pip-audit was clean after upgrading pytest. Remote Actions evidence still pending (see residual risks).

---

### 10. Missing structured application security logging

**Before**  
Observability was mostly SQLite audit rows with over-retained payloads. No correlation IDs, no structured authz/tool/path signals for detection engineering.

**Why we fixed it**  
Security operations need reconstructable, correlated events across API → agent → tool → authz outcomes.

**How we secured it**  
- `SecurityLogger` + correlation ID middleware  
- Detection-oriented event types (auth failures, unauthorized tool attempts, unusual recipients, agent failures, etc.)  
- Enriched audit recorder fields

**After**  
Security-relevant actions emit structured logs and redacted audit records with correlation IDs. Gap closures later added additive emits for missing-bearer, rate-limit, request-size, admin-surface probes, broker document deny, API customer IDOR, and first-class `path_policy` / `tool_timeout` catalogue coverage (see [Detection logging criteria](#detection-logging-criteria-use-cases-and-fields) below). Business allow/deny outcomes were not changed.

---

### 11. Unsafe path handling in data reset utility

**Before**  
`scripts/reset_data.py` deleted `ORION_DATABASE_PATH` (+ WAL/SHM) with no containment and no explicit enablement. A mis-set env var could delete arbitrary writable paths.

**Why we fixed it**  
Destructive utilities must be safe by default and impossible to trigger accidentally in production.

**How we secured it**  
- Require `ORION_ALLOW_DATA_RESET=true`  
- Refuse `ORION_ENV=production`  
- Constrain deletion under repository/data paths  
- Final containment check before unlink

**After**  
Reset without allow flag or in production fails closed. Covered by `tests/test_reset_and_config.py`.

---

### 12. Missing API rate limiting

**Before**  
No request-rate controls on token, chat, or tool endpoints.

**Why we fixed it**  
Open endpoints enable brute force, token minting abuse (while DevIdP is on), and resource exhaustion.

**How we secured it**  
- In-process sliding-window `RateLimiter`  
- Applied to `/api/token`, `/api/chat`, and email endpoints  
- Configurable via env (`ORION_RATE_LIMIT_*`)

**After**  
Bursting beyond the window returns `429`. Multi-instance shared limiting remains a residual backlog item.

---

### 13. Unauthenticated token issuance

**Before**  
`POST /api/token` issued a bearer token for any known synthetic email with no password/secret/challenge.

**Why we fixed it**  
Open issuance is acceptable only as an explicit local DevIdP, never as production identity.

**How we secured it**  
- DevIdP requires non-production env **and** `ORION_ENABLE_DEV_IDP=true`  
- Production configuration fails closed if DevIdP is enabled or signing key is missing  
- OIDC provider stub exists but fails closed until JWKS is configured

**After**  
Production token issuance is disabled; missing production signing key raises `ConfigurationError`.

---

### 14. Dependency reproducibility / lockfile gaps

**Before**  
Only version ranges in `pyproject.toml`. CI/Docker installed floating versions over time.

**Why we fixed it**  
Unpinned installs make builds non-reproducible and undermine vulnerability triage.

**How we secured it**  
- Generated `requirements.txt` via `pip freeze`  
- CI installs from the lockfile  
- Documented `make lock` workflow  

**After**  
Installs are reproducible at the freeze snapshot level. Hash-pinned/`uv.lock` installs remain in `to-do.md` as next-wave hardening.

---

### 15. Container hardening gaps

**Before**  
Single-stage image; writable `./data` bind mount; limited compose security options; no healthcheck in image.

**Why we fixed it**  
Containers should run least privilege, with minimal writable surface and clear health semantics.

**How we secured it**  
- Multi-stage Dockerfile, UID `10001`, HEALTHCHECK  
- Compose: `read_only`, scoped data volume, tmpfs, `cap_drop: ALL`, `no-new-privileges`, resource limits, internal network  
- Production env defaults disable DevIdP and require signing key

**After**  
Hardening is present in source. Digest-pinned base images and live compose verification remain next-wave items (`to-do.md` P0).

---

### 16. Inadequate security regression coverage

**Before**  
Only four happy-path API tests. None of the original attack paths had automated regressions.

**Why we fixed it**  
Without negative tests, remediations regress silently.

**How we secured it**  
- Added auth, tools/path/email, reset/config, and evaluation suite tests  
- Deterministic eval dataset under `evals/datasets/v1/`  
- CI runs the full pytest suite as a release gate

**After**  
`29 passed` locally, including regressions for the original confirmed findings.

---

## Architectural security changes (how the system is structured now)

**Before:** Flat `main.py` / `agent.py` / `tools.py` / `store.py` with business logic and weak controls mixed together.

**After (modular monolith):**

| Area | Module |
| --- | --- |
| Config fail-closed | `app/config` |
| AuthN / DevIdP / tokens | `app/auth` |
| AuthZ policy | `app/authorization` |
| API / rate limit / headers | `app/api` |
| Tool registry + broker | `app/tools` |
| Agent state machine | `app/agent` |
| Model gateway + FakeLLM | `app/gateway` |
| Prompt versions | `app/prompts` |
| Persistence | `app/persistence` |
| Audit / telemetry | `app/observability` |
| Evals | `evals/` |

Security decisions are enforced at the broker and authorization service, not only by hiding UI controls.

**Final architecture diagram (security design):** see
[docs/security-architecture.md](docs/security-architecture.md) for the modular
monolith control-plane diagram (trust zones, request sequence) and
[docs/architecture.md](docs/architecture.md) for module topology. Production
phased recommendations: [prod-plan.md](prod-plan.md).

---

## What we explicitly did **not** claim

- Real foundation-model prompt-injection resistance (FakeLLM only)
- External email delivery or external data exfiltration
- SSRF to remote networks (fixture fetch is local filesystem)
- Full production readiness (live OIDC hosting, shared rate limits, remote CI artifacts still open)

See also:

- [docs/security-architecture.md](docs/security-architecture.md) — final architecture + security design diagrams
- [docs/remediation-mapping.md](docs/remediation-mapping.md)
- [docs/residual-risks.md](docs/residual-risks.md)
- [docs/implementation-summary.md](docs/implementation-summary.md)
- [prod-plan.md](prod-plan.md) — phased production recommendations
- [to-do.md](to-do.md) for backlog status

---

## Next-wave fixes (`feature/orion-security-hardening-next`)

This section records the hardening wave that executed [to-do.md](to-do.md).

### P0.1 Digest-pinned container base image

**Before:** `FROM python:3.12-slim` floated with the tag.  
**Why:** Tag mutation can silently change the runtime trust root.  
**How:** Pinned `python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b` via `ARG PYTHON_BASE`; added `scripts/assert_dockerfile_digests.py` and CI step.  
**After:** Unpinned Dockerfiles fail the assertion script/tests.

### P0.2 SHA-pinned GitHub Actions + Dependabot

**Before:** Workflow used mutable tags (`@v4`, `@v5`, `@v2`, …).  
**Why:** Action tags can move; supply-chain integrity requires immutable refs.  
**How:** Replaced with 40-char commit SHAs and version comments; added `.github/dependabot.yml`.  
**After:** CI references immutable action commits; Dependabot can open update PRs.

### P0.3 Hashed Python lockfile

**Before:** Unhashed `pip freeze` snapshot / floating installs.  
**Why:** Without hashes, dependency substitution is possible.  
**How:** Regenerated `requirements.txt` with `uv pip compile --generate-hashes`; CI/Docker install with `--require-hashes`; pinned pip/setuptools/wheel in builder.  
**After:** Local `pip-audit` clean against hashed lockfile. Automated lock drift CI check remains deferred.

### P0.4 Compose prod/dev hardening

**Before:** Single compose service without explicit user/ulimits/logging/profile split.  
**Why:** Production and local DevIdP flows must not share fail-open defaults.  
**How:** Profiles `prod`/`dev`, explicit UID, init, stop grace, ulimits, log rotation, named volume only, internal network.  
**After:** `docker compose --profile prod|dev config` validates locally.

### P2 Prompt files + message-part separation + gateway depth

**Before:** Prompts embedded as strings in Python; limited gateway resilience controls.  
**Why:** Prompt changes must be reviewable artifacts; retrieved data must never become system policy.  
**How:** On-disk templates under `app/prompts/templates/`; `MessageParts`; approved-only prompt loading; circuit breaker/retries; model inventory JSON; side-effect idempotency; trajectory persistence + loop signature detection.  
**After:** Prompt hash/load tests pass; injection regressions still green.

### P1 Local identity / API abuse controls

**Before:** No logout/revocation; no request body ceiling beyond pydantic field sizes; OIDC stub only.  
**Why:** Compromised bearer tokens and oversized bodies are practical abuse paths.  
**How:** JTI denylist + `/api/logout`; production TTL default 900s; body-size middleware; tighter route budgets; fixture/URL JWKS OIDC provider that fails closed without keys.  
**After:** Revoked tokens return `401`; oversized declared bodies return `413`. Live hosted IdP and Redis limiter remain residual.

### P3 Modularity / docstrings / domain errors

**Before:** Route handlers carried more orchestration; shim not marked deprecated.  
**Why:** Security boundaries should be explicit and reusable outside HTTP.  
**How:** `ChatService` / `DocumentService` / `ApprovalService`; deprecated `app/store.py`; domain errors; security-boundary docstrings on core modules; public-method docstrings and trust-boundary comments on auth, authz, API, tools, observability, agent, gateway, retrieval, and services.  
**After:** Routes are thinner; method-level docs cover security-critical callables. Formal pydocstyle CI enforcement still partial/deferred.

### P4/P5/P6 Evidence and polish

**Before:** Audit rows lacked integrity chaining; DB file modes unset; detection catalogue missing; Actions lacked hadolint/compose/digest checks.  
**Why:** Audit tamper-evidence, least filesystem privilege, and CI guardrails reduce operational blind spots.  
**How:** Hash-chained audit events; chmod `0700`/`0600`; `docs/detection-signals.md` + `docs/frontend-security.md`; CI hadolint + compose config + digest assertion; additive detection emits for previously silent deny/abuse paths.  
**After:** Local pytest **41 passed**, ruff clean, pip-audit clean. Operational signal catalogue includes `rate_limit_exceeded`, `request_size_rejected`, `unauthorized_resource_access`, `path_policy`, and `tool_timeout`. Remote Actions artifacts and full container runtime smoke remain deferred.

### Explicitly still open

See [docs/residual-risks.md](docs/residual-risks.md) and unchecked deferred items in [to-do.md](to-do.md). Production release sequencing (OIDC, shared abuse controls, AI guardrails, data/embedding protection, SIEM, release gates) is recommended phase-by-phase in [prod-plan.md](prod-plan.md) — recommendations only; not implemented by that document alone.

---

### Production recommendation program (`prod-plan.md`)

**Before:** Local hardening evidence lived in finding logs and a short deploy checklist. Teams lacked a phased path from assessment posture to enterprise release covering identity, AI guardrails, data/embedding protection, and ops.

**Why we documented it**  
A local FakeLLM assessment must not be mistaken for production readiness. Release owners need ordered secure practices with acceptance criteria.

**How we captured it**  
- Added root [prod-plan.md](prod-plan.md): Phases 0–6 (baseline → identity/edge → platform HA → AI guardrails → data/embeddings → detect/respond → release/ops)  
- Explicit non-claims (FakeLLM ≠ real-model safety; outbox ≠ SMTP; fixture fetch ≠ SSRF)  
- MVP vs enterprise matrices, recommendation→current-status map, 30/60/90-day sketch  
- Cross-links from [docs/production-checklist.md](docs/production-checklist.md) and [docs/implementation-summary.md](docs/implementation-summary.md)

**After**  
Deploy-day switches remain in the checklist; the phased program lives in `prod-plan.md`. Implementing those phases is separate engineering/infra work.

---

## Maintainability — docstrings and comments

Security-critical modules already had module-level boundary headers. This pass adds short public-method/class docstrings that state **purpose** and **trust boundary** (what is trusted vs untrusted), plus sparse inline comments only at non-obvious policy or emit sites.

Annotated surfaces:

- `app/auth/*` — token issue/verify, identity rebind, revocation, providers
- `app/authorization/policy.py` — deny-by-default decisions
- `app/api/{deps,middleware,rate_limit,routes}.py` — auth gate, abuse controls, thin routes
- `app/tools/{broker,definitions,registry,implementations}.py` — allowlist broker and handlers
- `app/observability/{logging,audit}.py` — structured security events and redaction
- `app/agent/orchestrator.py`, `app/gateway/gateway.py`, `app/retrieval/service.py`, `app/services/*`

Rules:

- Docstrings explain intent and trust; they do not restate signatures.
- Comments mark *why* a deny path emits a detection signal, not *what* the next line does.
- No business-logic changes accompany documentation edits.
- Formal `pydocstyle` CI remains deferred (see P3.2 in [to-do.md](to-do.md)).

---

## Detection logging criteria (use cases and fields)

Operational catalogue: [docs/detection-signals.md](docs/detection-signals.md).  
Emitter: `SecurityLogger` in `app/observability/logging.py` (JSON on stdout).

### Common envelope

Every event includes:

| Field | Meaning |
| --- | --- |
| `event_type` | Detection signal name |
| `correlation_id` | Request-scoped ID from middleware / `X-Correlation-ID` |

### Privacy rules (never log)

- Raw chat or email bodies
- Bearer tokens, signing keys, JWKS material
- Full retrieved document text
- Unredacted tool argument payloads that contain message content (audit path already redacts)

### Use cases and required fields

| Use case | `event_type` | When | Required fields | Severity |
| --- | --- | --- | --- | --- |
| Missing/invalid auth | `authentication_failure` | Missing/non-Bearer header or `TokenError` | `reason`, `path` | medium |
| DevIdP blocked | `token_issuance_denied` | Production / disabled IdP | `reason` | medium |
| Unknown mint | `token_issuance_anomaly` | Unknown synthetic email | `reason`, `email` | medium |
| API/tool abuse volume | `rate_limit_exceeded` | 429 before handler | `path`, `rate_key`; optional `user_email` | medium |
| Oversized/invalid body | `request_size_rejected` | 413 or invalid Content-Length | `path`, `reason`; optional `content_length` | low |
| Customer IDOR | `cross_tenant_access_attempt` | Customer deny (API and broker) | `user_email`, `resource_id`, `reason`; optional `tool_id` / `endpoint` | high |
| Document/tool ACL deny | `unauthorized_tool_attempt` | Non-allowlisted tool, email role deny, broker document deny | `tool_id`, `user_email`, `reason` | high |
| Admin surface probe | `unauthorized_resource_access` | Audit / outbox / approval list or decide deny | `user_email`, `resource_type`, `path` or `endpoint`, `reason` | high |
| Email allowlist | `unusual_email_recipient` | Recipient suffix fail | `tool_id`, `user_email`, `recipient_domain` | high |
| Fixture escape | `path_policy` | Fixture resolve / fetch deny | `user_email`, `reason`; redacted `url` / `fixture_ref` | high |
| Agent budget | `excessive_tool_calls` | Tool call budget exceeded | `user_email`, `tool_call_count` | medium |
| Agent loop | `agent_loop_detected` | Repeated tool+args signature | `user_email`, `signature` | medium |
| Agent failure | `agent_failed` | Orchestrator exception | `user_email`, `error` | medium |
| Model quota | `abnormal_model_usage` | Per-user model quota exceeded | `user_email`, `reason` | medium |
| Model telemetry | `model_inference` | Successful gateway completion | `user_email`, `provider`, `model`, `prompt_version`, `elapsed_seconds` | info |
| Tool hang | `tool_timeout` | Tool execution over timeout | `tool_id`, `user_email`, `elapsed_seconds` | medium |
| Redacted audit mirror | `audit_event` | Every `AuditRecorder.record` | redacted audit fields | info |

Correlate unexpected prompt/model drift by comparing `prompt_version` / `model` on `model_inference` against the approved inventory and prompt registry hashes.

### Logging gap closures (additive only)

Emits were added immediately before existing raise/return paths. Allow/deny decisions, HTTP status codes, FakeLLM behavior, and tool outputs are unchanged.

| Gap | Site | `event_type` |
| --- | --- | --- |
| Missing / non-Bearer Authorization | `app/api/deps.py` `current_user` | `authentication_failure` (`reason=missing_bearer`) |
| Rate limit 429 | `app/api/rate_limit.py` `RateLimiter.check` (+ route call sites) | `rate_limit_exceeded` |
| Body too large / invalid Content-Length | `app/api/middleware.py` | `request_size_rejected` |
| Audit / outbox 403 | `app/api/routes.py` | `unauthorized_resource_access` |
| Approval list unauthorized | `app/services/approvals.py` | `unauthorized_resource_access` |
| Approval decide unauthorized | `app/tools/broker.py` `resolve_pending_action` | `unauthorized_resource_access` |
| Broker document ACL deny | `app/tools/broker.py` `_authorize_tool` | `unauthorized_tool_attempt` |
| API customer ACL deny | `app/tools/implementations.py` `get_customer` | `cross_tenant_access_attempt` |
| Fixture path deny | `app/tools/implementations.py` `fetch_internal_resource` | `path_policy` (alongside existing `audit_event`) |
