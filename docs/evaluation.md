# Evaluation Framework

Location: `evals/`

- Dataset version: `v1`
- Suite version: `orion-security-evals-1.0.0`
- Runner: `evals/runner.py`
- Gate test: `tests/test_eval_suite.py`

Cases cover normal requests, document-instruction injection, cross-tenant customer access, path traversal, and jailbreak-style email attempts.

Assertions are deterministic. The suite does not use LLM-as-judge.

A release decision of `pass` requires every case to execute and succeed. Unevaluated cases are never reported as passed.
