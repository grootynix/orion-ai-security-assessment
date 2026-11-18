# Orion Enterprise Knowledge Assistant

Secure, modular knowledge assistant for internal policies, project documents, and customer records. Orion uses a deterministic FakeLLM by default so local development and security regression testing do not require external model credentials.

This repository is the hardened submission for the Orion AI security assessment.

---

## Assessor quick start

Read these three files first:

| Order | Document | What it answers |
| --- | --- | --- |
| 1 | [fixes.md](fixes.md) | **What we fixed** — finding-by-finding before/after, why each control was added, and evidence of the hardening work |
| 2 | [prod-plan.md](prod-plan.md) | **How to take it to production** — phased program plan (identity, platform, AI guardrails, detection, release) beyond this local assessment |
| 3 | [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | **What Orion is** — product scope, components, and intended operating posture |

Suggested review path after that:

1. Threats and residual risk → [docs/threat-model.md](docs/threat-model.md), [docs/residual-risks.md](docs/residual-risks.md), [docs/accepted-risks.md](docs/accepted-risks.md)
2. Security design → [docs/security-architecture.md](docs/security-architecture.md), [docs/authn-authz.md](docs/authn-authz.md), [docs/agent-tools.md](docs/agent-tools.md)
3. Proof / verification → [docs/security-test-catalogue.md](docs/security-test-catalogue.md), [docs/remediation-mapping.md](docs/remediation-mapping.md), `make test`
4. Deploy-day gates → [docs/production-checklist.md](docs/production-checklist.md) (companion to [prod-plan.md](prod-plan.md))

---

## Repository map

```text
.
├── fixes.md                 # Security fixes log (primary assessor evidence)
├── prod-plan.md             # Phased production readiness plan
├── SYSTEM_OVERVIEW.md       # Product / system overview
├── README.md                # This file
├── app/                     # Hardened FastAPI application
├── tests/                   # Security + API regression tests
├── evals/                   # Deterministic security evaluation suite
├── docs/                    # Architecture, threat model, checklists
├── data/                    # Synthetic seed data + fixtures (not real secrets)
├── scripts/                 # Local helpers (reset, digest asserts)
├── Dockerfile               # Multi-stage hardened runtime
├── docker-compose.yml       # Dev/prod compose profiles
└── .github/workflows/       # CI: tests, lint, audit, SAST
```

---

## Architecture overview

Orion is a modular monolith:

- FastAPI route layer with authentication, rate limiting, and security headers
- Signed JWT authentication with server-side identity rebinding
- Centralized deny-by-default authorization
- Tool registry and execution broker with approval for consequential actions
- Model gateway wrapping FakeLLM (optional future hosted/self-hosted providers)
- Versioned prompts and deterministic evaluation gates
- SQLite persistence for documents, customers, redacted audit events, approvals, and local email outbox

See [docs/architecture.md](docs/architecture.md) and [docs/security-architecture.md](docs/security-architecture.md).

---

## Prerequisites

- Python 3.12
- `make`
- Docker Compose v2 (optional)

## Setup

```sh
make setup
```

Copy environment defaults:

```sh
cp .env.example .env
```

## Run locally

```sh
make run
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Reset the local SQLite database (non-production only, explicit allow required):

```sh
make reset-data
```

## Docker

Production-oriented compose requires a signing key:

```sh
cp .env.example .env
# Set ORION_ENV=production, ORION_ENABLE_DEV_IDP=false,
# and a strong ORION_TOKEN_SIGNING_KEY in .env
docker compose --profile prod up --build
```

For a local Docker demo with the synthetic DevIdP UI flow:

```sh
docker compose --profile dev up --build
```

Dev profile defaults use the labeled non-production signing key from `.env.example`.

## Tests and security checks

```sh
make test
make lint
make audit
```

---

## Synthetic users (DevIdP only)

`POST /api/token` is available only when `ORION_ENV` is `development` or `test` and `ORION_ENABLE_DEV_IDP=true`.

| Email | Role |
| --- | --- |
| `alice@example.test` | employee |
| `bob@example.test` | employee |
| `manager@example.test` | manager |
| `admin@example.test` | administrator |

## API examples

```sh
TOKEN=$(curl --silent -X POST http://127.0.0.1:8000/api/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.test"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl --silent 'http://127.0.0.1:8000/api/documents?q=travel' \
  -H "Authorization: Bearer $TOKEN"
```

Email send creates a pending approval. Managers approve via:

```sh
curl --silent -X POST "http://127.0.0.1:8000/api/approvals/$ACTION_ID" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approve"}'
```

---

## Documentation index

### Submission evidence (start here)

| Document | Purpose |
| --- | --- |
| [fixes.md](fixes.md) | What changed, why, and how each finding was closed |
| [prod-plan.md](prod-plan.md) | Phased plan to operate Orion beyond local assessment |
| [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | System purpose and component map |
| [docs/implementation-summary.md](docs/implementation-summary.md) | Compact implementation wrap-up |
| [docs/remediation-mapping.md](docs/remediation-mapping.md) | Finding → control mapping |

### Security design

| Document | Purpose |
| --- | --- |
| [docs/security-architecture.md](docs/security-architecture.md) | End-to-end security design |
| [docs/threat-model.md](docs/threat-model.md) | Threats and mitigations |
| [docs/authn-authz.md](docs/authn-authz.md) | Authentication and authorization |
| [docs/agent-tools.md](docs/agent-tools.md) | Tool broker, approvals, agent bounds |
| [docs/rag-security.md](docs/rag-security.md) | Retrieval and document trust boundaries |
| [docs/model-gateway.md](docs/model-gateway.md) | Model gateway and FakeLLM boundary |
| [docs/model-supply-chain.md](docs/model-supply-chain.md) | Model / dependency supply-chain controls |
| [docs/prompts.md](docs/prompts.md) | Versioned prompts |
| [docs/frontend-security.md](docs/frontend-security.md) | Browser UI security notes |
| [docs/detection-signals.md](docs/detection-signals.md) | Audit and detection signals |

### Verification and operations

| Document | Purpose |
| --- | --- |
| [docs/security-test-catalogue.md](docs/security-test-catalogue.md) | Security test catalogue |
| [docs/evaluation.md](docs/evaluation.md) | Deterministic eval framework |
| [docs/cicd-security.md](docs/cicd-security.md) | CI/CD controls |
| [docs/docker-hardening.md](docs/docker-hardening.md) | Container hardening |
| [docs/architecture.md](docs/architecture.md) | Application architecture |
| [docs/production-checklist.md](docs/production-checklist.md) | Deploy-day go / no-go switches |
| [docs/residual-risks.md](docs/residual-risks.md) | Known remaining risks |
| [docs/accepted-risks.md](docs/accepted-risks.md) | Explicitly accepted risks for this assessment |

---

## Important limitations

- FakeLLM is deterministic and is not a substitute for real-model security validation.
- Local email delivery is simulated via SQLite outbox only.
- Fixture fetching is constrained local filesystem access, not SSRF.
- Enterprise OIDC requires external identity infrastructure before production use.

For the path from this local posture to a production release, see [prod-plan.md](prod-plan.md).
