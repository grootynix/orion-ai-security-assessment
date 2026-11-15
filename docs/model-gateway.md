# Model Gateway

`ModelGateway` is the only supported inference entrypoint.

Controls:

- Approved model identifier (`ORION_APPROVED_MODEL_ID`)
- Provider selection (`ORION_MODEL_PROVIDER`, default `fake`)
- Input/output size limits
- Per-user in-memory quota
- Prompt attachment from the versioned registry
- Usage telemetry events

Providers:

- `FakeLLM` — deterministic local provider
- `HostedModelProvider` — fail closed until configured
- `SelfHostedModelProvider` — fail closed until configured

Agents cannot select arbitrary model endpoints.
