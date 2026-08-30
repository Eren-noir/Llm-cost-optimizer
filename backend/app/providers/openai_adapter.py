"""
OpenAI provider adapter.

Uses the official `openai` Python SDK's Chat Completions API. Model
name is NOT hard-coded - it's passed in at construction time from the
model registry (see docs/03-database.md, `models` table), so pricing
and model choice stay data-driven rather than baked into this file
(see project Rule 3 in the master brief: "Use current official
pricing when calculating real-world costs").
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


class OpenAIAdapter(LLMProviderAdapter):
    provider_name = "openai"

    def __init__(self, api_key: str, model_name: str, context_limit: int = 128000):
        # Import here, not at module level, so the rest of the app can be
        # imported/tested without the `openai` package installed if this
        # adapter isn't in use.
        from openai import OpenAI

        self.model_name = model_name
        self.context_limit = context_limit
        self._client = OpenAI(api_key=api_key)

    def estimate_tokens(self, prompt: str, params: RequestParams) -> TokenEstimate:
        return TokenEstimate(
            input_tokens=estimate_token_count(prompt),
            output_tokens=params.max_output_tokens,
        )

    def send_request(self, prompt: str, params: RequestParams) -> ProviderResponse:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            InternalServerError,
            RateLimitError,
        )

        messages = []
        if params.system_prompt:
            messages.append({"role": "system", "content": params.system_prompt})
        messages.append({"role": "user", "content": prompt})

        start = time.monotonic()
        try:
            completion = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=params.max_output_tokens,
                temperature=params.temperature,
            )
        except AuthenticationError as exc:
            raise InvalidProviderCredentialsError(f"OpenAI: {exc}") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError(f"OpenAI: {exc}") from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError(f"OpenAI: {exc}") from exc
        except (APIConnectionError, InternalServerError) as exc:
            raise ProviderUnavailableError(f"OpenAI: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        choice = completion.choices[0]

        return ProviderResponse(
            text=choice.message.content or "",
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "unknown",
            raw_response=completion.model_dump(),
        )

    def get_model_capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            model_name=self.model_name,
            context_limit=self.context_limit,
            supports_system_prompt=True,
            supports_function_calling=True,
            supports_vision=True,
        )
