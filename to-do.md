# Orion Hardening Backlog — Next Wave

Branch: `feature/orion-security-hardening-next`  
Owner posture: Principal Application Security / AI Security / DevSecOps  
Status: **wave executed locally** (checkboxes updated to match reality)  
Baseline completed on: `feature/orion-production-security-hardening` (unsigned work still in tree)

---

## Priority 0 — Supply-chain integrity

### P0.1 Pin container base images by digest
- [x] Replace `FROM python:3.12-slim` with digest-pinned refs
- [x] Pin both builder and runtime stages via `ARG PYTHON_BASE=...@sha256:...`
- [x] Document digest refresh process in `docs/docker-hardening.md`
- [x] Add CI/script check `scripts/assert_dockerfile_digests.py`

### P0.2 Hash-pin GitHub Actions
- [x] Replace mutable tags with full commit SHAs + version comments
- [x] Cover checkout, setup-python, upload-artifact, gitleaks, trivy, checkov, sbom, hadolint
- [x] Add Dependabot for `github-actions` and `pip`

### P0.3 Reproducible Python installs
- [x] Hashed `requirements.txt` via `uv pip compile --generate-hashes`
- [x] Install with `--require-hashes` in CI and Docker
- [x] Pin `pip`/`setuptools`/`wheel` in builder
- [ ] Fail CI if lockfile is stale vs `pyproject.toml` — **deferred** (manual regenerate via `uv pip compile`; add automated drift check later)

### P0.4 Further Docker Compose / runtime hardening
- [x] Explicit `user: "10001:10001"`
- [x] `security_opt: [no-new-privileges:true]` verified via `docker compose config`
- [x] `cap_drop: [ALL]`
- [x] Logging driver rotation limits
- [x] ulimits (nofile, nproc)
- [x] Named volume only (no host bind)
- [x] Split compose profiles: `dev` vs `prod`
- [x] `init: true` and `stop_grace_period`
- [x] Internal network retained (egress deny for sidecar-less local demos)
- [x] Secrets via required env var / uncommitted `.env` guidance

---

## Priority 1 — Identity, session, and API abuse controls

### P1.1 Real OIDC / enterprise IdP boundary
- [x] OIDC provider with JWKS URL client + fixture path support (fail closed without keys)
- [ ] Live key rotation against hosted IdP — **deferred** (requires external IdP)
- [x] Server-side identity rebinding retained (never trust token roles)
- [x] DevIdP impossible in production (already gated + regressions)

### P1.2 Token revocation / session controls
- [x] JTI denylist + `/api/logout`
- [x] Shorter production default TTL (900s) + `ORION_PRODUCTION_TOKEN_TTL_SECONDS`
- [x] Auth failure / issuance anomaly security logs

### P1.3 Stronger API abuse protection
- [ ] Shared Redis rate limiter — **deferred** (multi-instance residual risk)
- [x] Tighter per-route budgets for token/chat/approvals/email
- [x] Request body size middleware (`ORION_MAX_REQUEST_BODY_BYTES`)
- [ ] Optional IP allowlists for admin endpoints — **deferred**

---

## Priority 2 — Prompt, model, and agent security depth

### P2.1 Prompt versioning maturity
- [x] Move prompts to `app/prompts/templates/...`
- [x] Keep prompt_id/version/hash/owner/status/history
- [x] Require `approved` status in ModelGateway
- [x] Prompt hash/load covered by tests (eval suite remains CI gate)

### P2.2 System / developer / user / retrieved separation
- [x] `MessageParts` structure in gateway protocol
- [x] FakeLLM/retrieval remain data-only (existing injection regressions)
- [x] Documented unsafe patterns in prompt developer text + docs

### P2.3 Model gateway production controls
- [x] Circuit breaker + bounded retries
- [x] Output length truncation / size limits
- [x] In-memory per-user quotas
- [x] Approved-model inventory JSON
- [x] No claim of real-model security validation

### P2.4 Agent execution hardening
- [x] Persist trajectories to SQLite
- [x] Stronger loop detection via tool signature window
- [ ] Cancellation API — **deferred**
- [x] Idempotency keys for side-effect tools
- [x] Propose vs execute for HIGH risk email (approval gate)

---

## Priority 3 — Code quality, modularity, and documentation debt

### P3.1 Modularization cleanup
- [x] Deprecate `app/store.py` shim
- [x] Services for chat/documents/approvals; thinner routes
- [x] Authz remains centralized
- [x] Keep API handlers thin

### P3.2 Docstrings and typing completeness
- [x] Security-boundary docstrings on key modules/services
- [ ] Enforce pydocstyle in CI for all `app/` — **partial** (manual docstrings added; formal pydocstyle rule not enabled)

### P3.3 Structured exceptions
- [x] Domain errors (`AuthError`, `AuthzDenied`, `ToolPolicyError`, etc.) + HTTP mapping helper

### P3.4 Docs accuracy pass
- [x] Residual risks / docker hardening / detection / frontend notes updated
- [ ] Full ops runbooks (key rotation, IR) — **partial** (covered lightly in docs; dedicated runbooks still thin)

---

## Priority 4 — Data, audit, and detection engineering

### P4.1 Audit integrity
- [x] Hash-chained audit events (`prev_hash` / `event_hash`)
- [ ] Separate audit DB permissions — **deferred** (single SQLite process)
- [x] Redaction regressions retained

### P4.2 Detection signals
- [x] `docs/detection-signals.md` catalogue
- [x] JSON stdout security logger retained

### P4.3 Database hardening
- [x] Directory `0700` / DB file `0600` at init
- [ ] Full migration framework — **deferred**
- [ ] Backup/restore drill doc — **deferred**

---

## Priority 5 — Frontend and browser security polish

- [x] Confirmed `textContent` only; documented in `docs/frontend-security.md`
- [x] Trusted Types readiness note
- [x] Token not in `localStorage`
- [x] Cookie/CSRF guidance if cookies are introduced later
- [x] UI design unchanged

---

## Priority 6 — Validation evidence

- [ ] Remote GitHub Actions artifacts — **deferred** (workflow updated; not run on hosted runners here)
- [ ] Full container runtime smoke after rebuild — **deferred** (compose config validated locally)
- [x] Hadolint step added to CI
- [x] Compose config validation in CI + local
- [x] Dockerfile digest assertion in CI + local tests
- [x] Local pytest/ruff/pip-audit evidence recorded in `fixes.md`

---

## Deferred intentionally this wave

- Redis shared rate limiter
- Live hosted OIDC/JWKS rotation
- Cancellation API for in-flight agents
- Formal pydocstyle CI enforcement
- Separate audit database / migration framework
- Remote Actions scanner artifact capture

## Local evidence (this session)

```text
pytest: 34 passed
ruff: All checks passed
pip-audit -r requirements.txt: No known vulnerabilities found
scripts/assert_dockerfile_digests.py: passed
docker compose --profile prod|dev config: passed (with ORION_TOKEN_SIGNING_KEY set)
```
