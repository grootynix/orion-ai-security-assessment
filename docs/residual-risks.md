# Residual Risks

1. **Live enterprise OIDC/JWKS hosting** is not wired to a real IdP. Fixture/OIDC stub exists and fails closed without JWKS; production federation still requires external infrastructure.
2. **Shared rate limiting** across replicas is not implemented (in-process only). Multi-instance deployments need Redis or equivalent.
3. **FakeLLM is not a real model.** Prompt-injection resistance against foundation models is unvalidated.
4. **SQLite single-node persistence** is suitable for local/staging, not highly available multi-writer production.
5. **Email remains simulated.** Integrating real SMTP would require additional DLP, recipient policy, and transport controls.
6. **Remote GitHub Actions runner evidence** (Gitleaks/Trivy/Checkov/Syft/Hadolint on hosted runners) is configured with SHA-pinned actions but was not executed against GitHub-hosted runners in this session.
7. **Docker image rebuild smoke** after digest pinning was not fully executed as a runtime container test in this session; compose config validation passed locally.
8. **Frontend SSO UX** is not implemented; DevIdP synthetic user picker remains for local/dev only.
