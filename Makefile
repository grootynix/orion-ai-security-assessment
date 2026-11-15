.PHONY: setup run test reset-data audit lint lock

setup:
	python3.12 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"
	$(MAKE) lock

lock:
	uv pip compile pyproject.toml -o requirements.txt --generate-hashes --python-version 3.12

run:
	ORION_ENV=development ORION_ENABLE_DEV_IDP=true ORION_ALLOW_DATA_RESET=true \
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	ORION_ENV=test ORION_ENABLE_DEV_IDP=true \
	ORION_TOKEN_SIGNING_KEY=orion-test-signing-key-not-for-production \
	.venv/bin/pytest

lint:
	.venv/bin/ruff check app tests evals scripts
	.venv/bin/bandit -r app -ll -q

audit:
	.venv/bin/pip-audit -r requirements.txt

reset-data:
	ORION_ENV=development ORION_ALLOW_DATA_RESET=true \
	.venv/bin/python scripts/reset_data.py
