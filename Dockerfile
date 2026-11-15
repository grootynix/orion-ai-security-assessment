# Multi-stage hardened runtime for Orion.
# Base image digest pinned for supply-chain integrity.
# Refresh: docker buildx imagetools inspect python:3.12-slim --format '{{.Manifest.Digest}}'
ARG PYTHON_BASE=python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

FROM ${PYTHON_BASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY requirements.txt ./
COPY app ./app
COPY evals ./evals
COPY data ./data
RUN python -m pip install --upgrade --no-cache-dir \
      "pip==26.3" "setuptools==80.9.0" "wheel==0.45.1" \
    && pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip install --no-cache-dir --prefix=/install --no-deps .

FROM ${PYTHON_BASE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORION_ENV=production \
    ORION_ENABLE_DEV_IDP=false \
    ORION_DATA_DIR=/app/data \
    ORION_DATABASE_PATH=/app/data/orion.sqlite3

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app ./app
COPY data ./data
COPY pyproject.toml ./

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin orion \
    && mkdir -p /app/data /tmp/orion \
    && chown -R 10001:10001 /app /tmp/orion

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
