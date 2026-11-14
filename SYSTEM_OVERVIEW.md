# Orion System Overview

Orion supports employees who need a quick answer from internal policies, project notes, and customer account records. The prototype combines a small document index with a deterministic assistant flow so that common retrieval and summarization paths can be exercised without a hosted model.

Employees work with their assigned accounts and project materials. Managers and administrators oversee shared accounts and local operational actions.

## Components

- **Browser interface:** A single-page workspace for choosing a synthetic user, asking questions, and viewing available documents.
- **FastAPI application:** Exposes chat, document, customer, audit, and local message endpoints.
- **Assistant adapter:** `FakeLLM` implements a small deterministic interface. A future model integration can implement the same `LanguageModel` protocol.
- **Local tools:** Search documents, retrieve records, queue simulated messages, and read bundled resource fixtures.
- **SQLite store:** Holds seeded records, audit events, and the local outbox.
- **Bundled data:** Synthetic policies, project materials, customer accounts, and fixture resources.

The service is intended for local evaluation. It has no hosted model dependency, and message delivery is represented by an entry in the local outbox.
