# Orion System Overview

Orion supports employees who need a quick answer from internal policies, project notes, and customer account records. The application combines a local document index with a deterministic assistant flow so retrieval, authorization, and tool-policy paths can be exercised without a hosted model.

Employees work with their assigned accounts and project materials. Managers and administrators oversee shared accounts and consequential local actions that require approval.

## Components

- **Browser interface:** Single-page workspace for selecting a synthetic DevIdP user, asking questions, and viewing authorized documents. Layout and branding are unchanged from the inherited prototype.
- **FastAPI application:** Chat, document, customer, approval, audit, and local outbox endpoints with authentication, authorization, rate limits, and security headers.
- **Model gateway:** Controlled inference boundary. FakeLLM is the default approved provider. Hosted and self-hosted providers exist as fail-closed stubs.
- **Agent orchestrator:** Bounded state machine with step, tool-call, and duration limits plus trajectory recording.
- **Tool broker:** Allowlisted tools with schema validation, authorization, approval gates, timeouts, and audit events.
- **Retrieval:** Keyword search over authorized documents with classification and project checks.
- **SQLite store:** Seeded records, redacted audit events, pending approvals, and the local outbox.
- **Evaluation framework:** Versioned deterministic security and quality cases used as a release gate.

The service is intended for local evaluation and secure staging. It has no hosted model dependency by default, and message delivery is represented by an entry in the local outbox after explicit approval.
