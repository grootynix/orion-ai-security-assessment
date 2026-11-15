# RAG Security

Orion uses keyword retrieval over SQLite-seeded documents. No external vector database is required for the current workload.

Controls:

- Classification-aware authorization before content enters model context
- Project membership checks for project-scoped documents
- Retrieval config version tracking (`keyword-v1`)
- Embedding model version recorded as `none-local-keyword`
- Retrieved text treated as untrusted data

## Fixture access

`fetch_internal_resource` accepts:

- `fixture://{allowlisted-id}`
- `http://localhost/...` / `http://127.0.0.1/...` only when mapped to an allowlisted fixture file

Canonical path resolution is constrained to `data/fixtures`. Traversal, symlink escape, and unknown file types are rejected. This is local filesystem containment, not SSRF.
