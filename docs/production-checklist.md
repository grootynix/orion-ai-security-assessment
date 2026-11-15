# Production Deployment Checklist

Day-of deploy switches only. For phased production recommendations (OIDC, guardrails, data/embedding protection, SIEM, release gates), see [prod-plan.md](../prod-plan.md).

- [ ] Set `ORION_ENV=production`
- [ ] Set strong unique `ORION_TOKEN_SIGNING_KEY` from a secret manager
- [ ] Confirm `ORION_ENABLE_DEV_IDP=false`
- [ ] Confirm `ORION_ALLOW_DATA_RESET` is unset/false
- [ ] Configure enterprise OIDC/JWKS (current stub is fail-closed)
- [ ] Restrict network exposure; keep compose publish on localhost or place behind TLS reverse proxy
- [ ] Mount only the SQLite data volume as writable
- [ ] Verify container runs as UID 10001
- [ ] Enable external log shipping for structured security events
- [ ] Review SBOM and vulnerability scan artifacts
- [ ] Confirm evaluation suite and security regressions pass in CI
- [ ] Document on-call ownership for approvals and audit review
- [ ] Rotate signing keys and define revocation/short-TTL strategy
- [ ] Validate backup/restore for the data volume
