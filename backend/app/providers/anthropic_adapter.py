"""
Anthropic provider adapter.

Uses the official `anthropic` Python SDK's Messages API. Model name
comes from the registry, same rationale as app/providers/openai_adapter.py.
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


class AnthropicAdapter(LLMProviderAdapter):
    provider_name = "anthropic"

    def __init__(self, api_key: str, model_name: str, context_limit: int = 200000):
        from anthropic import Anthropic

        self.model_name = model_name
        self.context_limit = context_limit
        self._client = Anthropic(api_key=api_key)

    def estimate_tokens(self, prompt: str, params: RequestParams) -> TokenEstimate:
        return TokenEstimate(
            input_tokens=estimate_token_count(prompt),
            output_tokens=params.max_output_tokens,
        )

    def send_request(self, prompt: str, params: RequestParams) -> ProviderResponse:
        from anthropic import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            InternalServerError,
            RateLimitError,
        )

        # NOTE: `temperature` is intentionally NOT sent as a top-level
        # parameter here. As of the current Anthropic SDK, newer models
        # (Opus 4.7+ and later) reject non-default temperature/top_p/top_k
        # with a 400 error - Anthropic has moved to adaptive sampling
        # controlled via `output_config`/`thinking` instead. Since this
        # adapter must work across whichever Claude model the registry
        # points it at, we rely on the model's default sampling behavior
        # rather than risk a hard failure on newer models. Verified
        # against the installed SDK's actual method signature, which no
        # longer lists `temperature` as a typed parameter at all.
        kwargs = dict(
            model=self.model_name,
            max_tokens=params.max_output_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if params.system_prompt:
            kwargs["system"] = params.system_prompt

        start = time.monotonic()
        try:
            message = self._client.messages.create(**kwargs)
        except AuthenticationError as exc:
            raise InvalidProviderCredentialsError(f"Anthropic: {exc}") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError(f"Anthropic: {exc}") from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError(f"Anthropic: {exc}") from exc
        except (APIConnectionError, InternalServerError) as exc:
            raise ProviderUnavailableError(f"Anthropic: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        text = "".join(block.text for block in message.content if block.type == "text")

        return ProviderResponse(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
            finish_reason=message.stop_reason or "unknown",
            raw_response=message.model_dump(),
        )

    def get_model_capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            model_name=self.model_name,
            context_limit=self.context_limit,
            supports_system_prompt=True,
            supports_function_calling=True,
            supports_vision=True,
        )
