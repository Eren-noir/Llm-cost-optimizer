"""
Google Gemini provider adapter.

Uses the official `google-genai` Python SDK. Model name comes from the
registry, same rationale as the OpenAI/Anthropic adapters.
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


class GeminiAdapter(LLMProviderAdapter):
    provider_name = "gemini"

    def __init__(self, api_key: str, model_name: str, context_limit: int = 1000000):
        from google import genai

        self.model_name = model_name
        self.context_limit = context_limit
        self._client = genai.Client(api_key=api_key)

    def estimate_tokens(self, prompt: str, params: RequestParams) -> TokenEstimate:
        return TokenEstimate(
            input_tokens=estimate_token_count(prompt),
            output_tokens=params.max_output_tokens,
        )

    def send_request(self, prompt: str, params: RequestParams) -> ProviderResponse:
        from google.genai import errors as genai_errors
        from google.genai.types import GenerateContentConfig

        config = GenerateContentConfig(
            max_output_tokens=params.max_output_tokens,
            temperature=params.temperature,
            system_instruction=params.system_prompt,
        )

        start = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
        except genai_errors.ClientError as exc:
            # google-genai surfaces auth/rate-limit/invalid-request as
            # ClientError with an http status code attached.
            status = getattr(exc, "code", None)
            if status == 401 or status == 403:
                raise InvalidProviderCredentialsError(f"Gemini: {exc}") from exc
            if status == 429:
                raise ProviderRateLimitError(f"Gemini: {exc}") from exc
            raise ProviderUnavailableError(f"Gemini: {exc}") from exc
        except genai_errors.ServerError as exc:
            raise ProviderUnavailableError(f"Gemini: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError(f"Gemini: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage_metadata

        return ProviderResponse(
            text=response.text or "",
            input_tokens=usage.prompt_token_count if usage else estimate_token_count(prompt),
            output_tokens=usage.candidates_token_count if usage else estimate_token_count(response.text or ""),
            latency_ms=latency_ms,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "unknown",
            raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
        )

    def get_model_capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            model_name=self.model_name,
            context_limit=self.context_limit,
            supports_system_prompt=True,
            supports_function_calling=True,
            supports_vision=True,
        )
