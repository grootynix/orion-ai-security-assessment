# CI/CD Security

Workflow: `.github/workflows/ci.yml`

Enforced steps:

1. Install from `requirements.txt` lockfile plus editable package
2. Pytest (functional, security regressions, evaluation gate)
3. Ruff
4. Bandit
5. pip-audit (fails the job on known vulnerabilities)
6. Gitleaks
7. Trivy filesystem scan
8. Checkov on Dockerfile/compose
9. Syft SBOM artifact upload

`continue-on-error` is not used for security gates.

Accepted risks, if any, must be recorded in `docs/accepted-risks.md` with owner and expiry.
