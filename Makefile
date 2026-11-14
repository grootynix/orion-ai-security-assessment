.PHONY: setup run test reset-data

setup:
	python3.12 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

run:
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	.venv/bin/pytest

reset-data:
	.venv/bin/python scripts/reset_data.py
