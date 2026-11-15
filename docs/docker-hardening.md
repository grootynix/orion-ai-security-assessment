# Docker Hardening

## Image

- Multi-stage build
- Digest-pinned base: `python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`
- Numeric non-root user `10001`
- Hashed dependency install (`pip install --require-hashes`)
- Pinned `pip` / `setuptools` / `wheel` in builder
- No secrets baked into the image
- HEALTHCHECK against `/health`

### Digest refresh process

1. `docker buildx imagetools inspect python:3.12-slim --format '{{.Manifest.Digest}}'`
2. Update `ARG PYTHON_BASE=...@sha256:...` in `Dockerfile`
3. Run `python scripts/assert_dockerfile_digests.py`
4. Rebuild and re-scan with Trivy

## Compose

Profiles:

- `prod`: `docker compose --profile prod up --build` — DevIdP disabled, signing key required
- `dev`: `docker compose --profile dev up --build` — DevIdP enabled for local synthetic users

Hardening:

- Explicit `user: "10001:10001"`
- `init: true`, `stop_grace_period: 20s`
- `read_only: true`
- Scoped writable volume `orion-data:/app/data` (no host bind in prod/dev profiles)
- tmpfs for `/tmp/orion`
- `cap_drop: ALL`
- `no-new-privileges:true`
- Memory/CPU/PID limits and ulimits
- json-file log rotation (`10m` x 3)
- Internal network
- Host publish only on `127.0.0.1:8000`

Secrets: provide `ORION_TOKEN_SIGNING_KEY` via environment or an uncommitted `.env` file. Do not commit production signing keys.
