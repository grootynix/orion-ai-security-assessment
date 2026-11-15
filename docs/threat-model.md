# Threat Model

## Assets

- Customer records
- Project and management documents
- Audit trail integrity
- Local outbox contents
- Signing keys and runtime configuration

## Adversaries

- Unauthenticated callers
- Authenticated low-privilege employees
- Malicious document authors
- Compromised or over-permissive automation

## Key threats and mitigations

| Threat | Mitigation |
| --- | --- |
| Token forgery | Signed JWT, algorithm allowlist |
| Privilege escalation via claims | Server-side identity rebinding |
| Document-triggered tool abuse | FakeLLM ignores document instructions; broker approval |
| Cross-user customer reads | Object-level authorization |
| Fixture path escape | Allowlist + fixtures-root containment |
| Email abuse | Role gate, recipient allowlist, approval |
| Audit leakage | Argument redaction |
| Dependency/supply-chain issues | Lockfile + enforced pip-audit/Trivy/Syft |
| Container breakout / over-privilege | Non-root, read-only root, dropped caps |

## Out of scope for current evidence

- Real foundation-model prompt injection campaigns
- External SMTP delivery
- Network SSRF to non-local hosts
