"""
Mock provider adapter.

Simulates a provider without making any network call - used for early
development, unit tests, and CI, so the routing/cost/quality pipeline
can be built and tested before real API credentials are wired in (see
Phase 5 plan in docs/00-master-prompt or the phase sequence in the
project brief: "Start with mock providers if necessary so development
does not depend on API credits").

Configurable per-instance so tests can simulate different model
tiers (cheap/fast vs. slow/expensive) and failure modes.
"""
from __future__ import annotations

import time

from app.core.errors import (
    InvalidProviderCredentialsError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.base import (
    LLMProviderAdapter,
    ModelCapabilities,
    ProviderResponse,
    RequestParams,
    TokenEstimate,
)
from app.providers.token_estimation import estimate_token_count


class MockAdapter(LLMProviderAdapter):
    def __init__(
        self,
        provider_name: str = "mock",
        model_name: str = "mock-model",
        context_limit: int = 8192,
        simulated_latency_ms: int = 50,
        failure_mode: str | None = None,
    ):
        """
        failure_mode: None, "timeout", "rate_limit", "invalid_credentials",
        or "unavailable" - lets tests exercise the router's fallback logic
        without needing a real provider to actually fail.
        """
        self.provider_name = provider_name
        self.model_name = model_name
        self.context_limit = context_limit
        self.simulated_latency_ms = simulated_latency_ms
        self.failure_mode = failure_mode

    def estimate_tokens(self, prompt: str, params: RequestParams) -> TokenEstimate:
        return TokenEstimate(
            input_tokens=estimate_token_count(prompt),
            output_tokens=min(params.max_output_tokens, 256),
        )

    def send_request(self, prompt: str, params: RequestParams) -> ProviderResponse:
        if self.failure_mode == "timeout":
            raise ProviderTimeoutError(f"{self.model_name} (mock) timed out")
        if self.failure_mode == "rate_limit":
            raise ProviderRateLimitError(f"{self.model_name} (mock) rate limited")
        if self.failure_mode == "invalid_credentials":
            raise InvalidProviderCredentialsError(f"{self.model_name} (mock) invalid credentials")
        if self.failure_mode == "unavailable":
            raise ProviderUnavailableError(f"{self.model_name} (mock) unavailable")

        start = time.monotonic()
        # Deterministic-ish "response": echoes a summary of the prompt so
        # tests can assert on content without needing a real model.
        response_text = f"[mock:{self.model_name}] response to: {prompt[:80]}"
        input_tokens = estimate_token_count(prompt)
        output_tokens = estimate_token_count(response_text)
        elapsed_ms = int((time.monotonic() - start) * 1000) + self.simulated_latency_ms

        return ProviderResponse(
            text=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
            finish_reason="stop",
            raw_response={"mock": True, "model": self.model_name},
        )

    def get_model_capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            model_name=self.model_name,
            context_limit=self.context_limit,
            supports_system_prompt=True,
            supports_function_calling=False,
            supports_vision=False,
        )


def make_mock_tier(tier: str) -> MockAdapter:
    """Convenience factory for the three benchmark tiers referenced in
    docs/01-requirements.md, section 9 (benchmark task categories),
    useful for router/cost-engine tests before real pricing is wired in."""
    tiers = {
        "cheap": MockAdapter(provider_name="mock", model_name="mock-cheap", context_limit=16000, simulated_latency_ms=30),
        "mid": MockAdapter(provider_name="mock", model_name="mock-mid", context_limit=32000, simulated_latency_ms=80),
        "premium": MockAdapter(provider_name="mock", model_name="mock-premium", context_limit=128000, simulated_latency_ms=150),
    }
    if tier not in tiers:
        raise ValueError(f"Unknown mock tier: {tier}")
    return tiers[tier]
