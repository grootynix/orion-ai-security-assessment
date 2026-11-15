# Security Test Catalogue

| Test | File | Finding covered |
| --- | --- | --- |
| Unsigned token rejected | `tests/test_security_auth.py` | 1 |
| Forged base64 token rejected | `tests/test_security_auth.py` | 1 |
| Role escalation via claims rejected | `tests/test_security_auth.py` | 2 |
| Expired / bad issuer / bad audience | `tests/test_security_auth.py` | 1 |
| Production disables DevIdP | `tests/test_security_auth.py` | 13 |
| Missing production signing key fails closed | `tests/test_security_auth.py` | 13 |
| Cross-user customer denied | `tests/test_security_auth.py` | 4 |
| Assignee can read own customer | `tests/test_security_auth.py` | 4 |
| Unauthorized audit denied | `tests/test_security_auth.py` | 2 |
| Document content cannot trigger email | `tests/test_security_tools.py` | 3 |
| Path traversal rejected | `tests/test_security_tools.py` | 5 |
| Allowlisted fixture readable | `tests/test_security_tools.py` | 5 |
| Employee cannot send email | `tests/test_security_tools.py` | 6 |
| Recipient outside allowlist rejected | `tests/test_security_tools.py` | 6 |
| Non-allowlisted tool rejected | `tests/test_security_tools.py` | 6 |
| Audit arguments redacted | `tests/test_security_tools.py` | 8, 10 |
| Security headers present | `tests/test_security_tools.py` | API hardening |
| Rate limiter burst rejected | `tests/test_security_tools.py` | 12 |
| Reset requires allow + refuses production | `tests/test_reset_and_config.py` | 11 |
| Evaluation suite gate | `tests/test_eval_suite.py` | 3, 4, 5, 16 |
| Functional API compatibility | `tests/test_api.py` | Compatibility |

CI additionally enforces dependency audit (9, 14), container/IaC scanning (15), and secret scanning (7).
