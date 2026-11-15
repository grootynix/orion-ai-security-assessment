# Orion Enterprise Knowledge Assistant

Secure, modular knowledge assistant for internal policies, project documents, and customer records. Orion uses a deterministic FakeLLM by default so local development and security regression testing do not require external model credentials.

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
docker compose up --build
```

For a local Docker demo with the synthetic DevIdP UI flow, set:

```env
ORION_ENV=development
ORION_ENABLE_DEV_IDP=true
ORION_TOKEN_SIGNING_KEY=orion-dev-only-signing-key-not-for-production
```

## Tests and security checks

```sh
make test
make lint
make audit
```

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

## Documentation

- [Architecture](docs/architecture.md)
- [Security architecture](docs/security-architecture.md)
- [Authentication and authorization](docs/authn-authz.md)
- [Agent and tool security](docs/agent-tools.md)
- [Model gateway](docs/model-gateway.md)
- [Prompt versioning](docs/prompts.md)
- [RAG security](docs/rag-security.md)
- [Evaluation framework](docs/evaluation.md)
- [CI/CD security](docs/cicd-security.md)
- [Docker hardening](docs/docker-hardening.md)
- [Threat model](docs/threat-model.md)
- [Security test catalogue](docs/security-test-catalogue.md)
- [Remediation mapping](docs/remediation-mapping.md)
- [Production checklist](docs/production-checklist.md)
- [Residual risks](docs/residual-risks.md)
- [Implementation summary](docs/implementation-summary.md)

## Important limitations

- FakeLLM is deterministic and is not a substitute for real-model security validation.
- Local email delivery is simulated via SQLite outbox only.
- Fixture fetching is constrained local filesystem access, not SSRF.
- Enterprise OIDC requires external identity infrastructure before production use.
