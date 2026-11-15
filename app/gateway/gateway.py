"""Controlled inference boundary for approved model providers."""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.gateway.protocol import LanguageModel, MessageParts, ModelRequest, ModelResponse
from app.observability.logging import SecurityLogger, get_correlation_id
from app.prompts.registry import PromptRegistry

INVENTORY_PATH = Path(__file__).resolve().parent / "model_inventory.json"


class ModelGatewayError(Exception):
    """Fail-closed gateway error with safe client status mapping."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class CircuitBreaker:
    """Simple consecutive-failure circuit breaker."""

    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def before_call(self) -> None:
        """Raise if the breaker is open and the reset window has not elapsed."""
        if self._opened_at is None:
            return
        if time.monotonic() - self._opened_at >= self.reset_seconds:
            self._opened_at = None
            self._failures = 0
            return
        raise ModelGatewayError("Model circuit breaker is open", status_code=503)

    def record_success(self) -> None:
        """Reset consecutive-failure state after a successful provider call."""
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        """Count a provider failure and open the breaker at threshold."""
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()


class ModelGateway:
    """
    Approved-model-only gateway with quotas, limits, and telemetry.

    Fail-closed behaviors:
    - Reject unknown/unapproved model IDs
    - Reject non-approved prompts
    - Enforce input/output size and per-user quotas
    - Open circuit after repeated provider failures
    """

    def __init__(
        self,
        settings: Settings,
        provider: LanguageModel,
        prompts: PromptRegistry,
        security_logger: SecurityLogger | None = None,
        inventory_path: Path | None = None,
    ):
        self.settings = settings
        self.provider = provider
        self.prompts = prompts
        self.security_logger = security_logger or SecurityLogger()
        self._usage: dict[str, deque[float]] = defaultdict(deque)
        self._max_input_chars = 4000
        self._max_output_chars = 4000
        self._per_user_per_minute = 60
        self._max_retries = 1
        self._breaker = CircuitBreaker()
        self._inventory = self._load_inventory(inventory_path or INVENTORY_PATH)

    @staticmethod
    def _load_inventory(path: Path) -> dict[str, dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["model_id"]: item for item in payload.get("models", [])}

    def _enforce_quota(self, user_email: str) -> None:
        now = time.monotonic()
        bucket = self._usage[user_email]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= self._per_user_per_minute:
            self.security_logger.emit(
                "abnormal_model_usage",
                user_email=user_email,
                reason="quota_exceeded",
            )
            raise ModelGatewayError("Model usage quota exceeded", status_code=429)
        bucket.append(now)

    def complete(
        self,
        *,
        message: str,
        user: Any,
        prompt_id: str = "orion.chat.default",
        retrieved_data: tuple[str, ...] = (),
    ) -> ModelResponse:
        """Run approved-prompt inference; retrieved_data stays in the data zone."""
        inventory_entry = self._inventory.get(self.provider.model_id)
        if inventory_entry is None or inventory_entry.get("status") != "approved":
            raise ModelGatewayError("Model is not on the approved inventory")
        if self.provider.model_id != self.settings.approved_model_id:
            raise ModelGatewayError("Model is not on the approved inventory")
        if len(message) > self._max_input_chars:
            raise ModelGatewayError("Input exceeds gateway limit")

        self._enforce_quota(user.email)
        prompt = self.prompts.get(prompt_id, require_approved=True)
        # Explicit trust-zone separation: retrieved_data never enters system/developer.
        parts = MessageParts(
            system=prompt.system_instructions,
            developer=prompt.developer_instructions,
            user=message,
            retrieved_data=retrieved_data,
        )
        request = ModelRequest(
            message=message,
            user=user,
            system_instructions=prompt.system_instructions,
            developer_instructions=prompt.developer_instructions,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            correlation_id=get_correlation_id(),
            parts=parts,
        )

        last_error: Exception | None = None
        response: ModelResponse | None = None
        for attempt in range(self._max_retries + 1):
            self._breaker.before_call()
            started = time.monotonic()
            try:
                response = self.provider.complete(request)
                self._breaker.record_success()
                elapsed = time.monotonic() - started
                break
            except Exception as exc:
                last_error = exc
                self._breaker.record_failure()
                if attempt >= self._max_retries:
                    raise ModelGatewayError(
                        "Model provider failed", status_code=503
                    ) from exc
                time.sleep(0.05 * (attempt + 1))
        assert response is not None
        elapsed = locals().get("elapsed", 0.0)

        if len(response.answer) > self._max_output_chars:
            response.answer = response.answer[: self._max_output_chars]
        response.metadata = {
            **response.metadata,
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "elapsed_seconds": elapsed,
            "provider": self.provider.provider_id,
            "model": self.provider.model_id,
            "message_parts": parts.as_dict()["retrieved_data"][:0],  # never log bodies
            "retrieved_parts_count": len(retrieved_data),
            "system_unchanged_by_retrieval": True,
        }
        if last_error is not None and response is None:
            raise ModelGatewayError("Model provider failed", status_code=503)
        self.security_logger.emit(
            "model_inference",
            user_email=user.email,
            provider=self.provider.provider_id,
            model=self.provider.model_id,
            prompt_version=prompt.version,
            elapsed_seconds=elapsed,
        )
        return response


class HostedModelProvider:
    """Future hosted API provider. Fails closed without explicit configuration."""

    provider_id = "hosted"
    model_id = "hosted-unconfigured"

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise ModelGatewayError(
            "Hosted model provider is not configured", status_code=503
        )


class SelfHostedModelProvider:
    """Future self-hosted provider. Fails closed without explicit configuration."""

    provider_id = "self_hosted"
    model_id = "self-hosted-unconfigured"

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise ModelGatewayError(
            "Self-hosted model provider is not configured", status_code=503
        )
