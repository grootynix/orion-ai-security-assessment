# Remediation Mapping

| # | Finding | Remediation | Status |
|---|---------|-------------|--------|
| 1 | Unsigned forgeable tokens | HS256 JWT with claim validation | Implemented and tested |
| 2 | Trusted client role claims | Identity directory rebinding | Implemented and tested |
| 3 | Document-triggered FakeLLM email | Removed content-to-tool execution | Implemented and tested |
| 4 | Missing customer OLAC | Assignee/manager policy in authz + tools | Implemented and tested |
| 5 | Fixture path escape into `data/` | Allowlist + fixtures-root containment | Implemented and tested |
| 6 | Unrestricted email / no approval | Allowlist, manager role, pending approval | Implemented and tested |
| 7 | Credential-like fixtures | Replaced with non-secret placeholders | Implemented and tested |
| 8 | Sensitive chat bodies in audit | Redacted argument storage | Implemented and tested |
| 9 | Soft pip-audit in CI | Enforced pip-audit without continue-on-error | Implemented but not fully validated in remote CI run |
| 10 | Missing structured security logging | SecurityLogger + enriched audit schema | Implemented and tested |
| 11 | Unsafe reset utility | Env gate + path containment | Implemented and tested |
| 12 | Missing rate limiting | In-process sliding window | Implemented and tested |
| 13 | Unauthenticated token issuance | DevIdP gated; production disabled | Implemented and tested |
| 14 | No dependency lockfile | `requirements.txt` generated from freeze | Implemented and tested |
| 15 | Container hardening gaps | Multi-stage, non-root, read-only, caps, limits | Implemented but not fully validated (image build not executed in this session) |
| 16 | Inadequate security regressions | Expanded pytest + eval suite | Implemented and tested |
