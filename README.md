# Orion Enterprise Knowledge Assistant

## Purpose

Orion is a small internal assistant prototype for answering employee questions using company policies, project documents, and customer records.

## Architecture overview

The application uses FastAPI for its HTTP API, Pydantic for request validation, and SQLite for the document index, audit events, and message outbox. A deterministic `FakeLLM` selects local tools and produces summaries. The browser interface is served by the application.

## Prerequisites

- Python 3.12
- `make` for the convenience commands
- Docker Compose v2 (optional)

## Setup

Create a virtual environment and install the application and test dependencies:

```sh
make setup
```

The application uses the bundled data and does not need an external service configuration.

## Run locally

Start the API and browser interface on `127.0.0.1:8000`:

```sh
make run
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Use `make reset-data` to restore the local SQLite state to its initial contents.

## Docker

```sh
cp .env.example .env
docker compose up --build
```

The service is published on the local machine at `127.0.0.1:8000`. Stop it with `docker compose down`.

## Tests

```sh
make test
```

## Synthetic users and tokens

The local token endpoint issues bearer tokens for these synthetic accounts:

| Email | Role |
| --- | --- |
| `alice@example.test` | employee |
| `bob@example.test` | employee |
| `manager@example.test` | manager |
| `admin@example.test` | administrator |

For example, acquire a token for Alice:

```sh
TOKEN=$(curl --silent -X POST http://127.0.0.1:8000/api/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.test"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

## API examples

Search the documents available to the signed-in user:

```sh
curl --silent 'http://127.0.0.1:8000/api/documents?q=travel' \
  -H "Authorization: Bearer $TOKEN"
```

Ask Orion a question:

```sh
curl --silent -X POST http://127.0.0.1:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"What does the travel policy say?"}'
```

Retrieve a customer record:

```sh
curl --silent http://127.0.0.1:8000/api/customers/customer-cinder-104 \
  -H "Authorization: Bearer $TOKEN"
```

Queue a simulated email in the local outbox:

```sh
MANAGER_TOKEN=$(curl --silent -X POST http://127.0.0.1:8000/api/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"manager@example.test"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl --silent -X POST http://127.0.0.1:8000/api/tools/send-email \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"to":"recipient@example.test","subject":"Local update","body":"Synthetic message"}'
```

The API also provides `GET /health`, `GET /api/documents/{document_id}`, and `GET /api/audit`.

## Repository structure

```text
app/                  FastAPI application, agent, tools, and browser interface
data/                 Synthetic documents, customer records, and local fixtures
tests/                Normal API behavior tests
scripts/              Local development helpers
.github/workflows/    Continuous integration workflow
```

## Simulation

All users, documents, customer records, credentials, tool results, and email actions are simulated. The application is designed to run locally and does not use an external model or email service.
