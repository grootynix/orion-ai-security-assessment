# Model and Data Supply Chain

Approved model inventory (current):

| Model ID | Provider | Status | Notes |
| --- | --- | --- | --- |
| `fake-llm-v1` | fake | approved | Deterministic local provider for tests and local runs |
| `hosted-unconfigured` | hosted | blocked | Fail-closed stub |
| `self-hosted-unconfigured` | self_hosted | blocked | Fail-closed stub |

Governance notes:

- No automatic download or execution of remote model code.
- Prompt versions and hashes are recorded in the prompt registry.
- Retrieval/embedding configuration versions are tracked in `RetrievalService`.
- Application dependency SBOM is generated in CI via Syft.
- Real model provenance, license, tokenizer, and artifact digest recording become mandatory when a non-fake provider is enabled.
