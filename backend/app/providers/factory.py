"""
Factory for constructing the right adapter instance given a provider
name and model name. This is the one place that knows how to turn
"provider = openai, model = gpt-4o-mini" into a live adapter object -
the Model Router (Phase 7) only ever calls get_adapter(), it never
imports a concrete adapter class directly.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.providers.anthropic_adapter import AnthropicAdapter
from app.providers.base import LLMProviderAdapter
from app.providers.gemini_adapter import GeminiAdapter
from app.providers.mock_adapter import MockAdapter
from app.providers.openai_adapter import OpenAIAdapter

_ADAPTER_CLASSES = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
}


def get_adapter(provider_name: str, model_name: str, context_limit: int = 128000) -> LLMProviderAdapter:
    """Construct a live provider adapter.

    provider_name == "mock" returns a MockAdapter regardless of
    model_name, which is what lets the rest of the system (router,
    cost engine, quality evaluator) be developed and tested before
    real API keys are available.
    """
    if provider_name == "mock":
        return MockAdapter(model_name=model_name, context_limit=context_limit)

    if provider_name not in _ADAPTER_CLASSES:
        raise ValueError(f"Unknown provider: {provider_name}")

    settings = get_settings()
    api_keys = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
    }
    api_key = api_keys[provider_name]
    if not api_key:
        raise ValueError(
            f"No API key configured for provider '{provider_name}' "
            f"(set it in .env - see .env.example)"
        )

    adapter_cls = _ADAPTER_CLASSES[provider_name]
    return adapter_cls(api_key=api_key, model_name=model_name, context_limit=context_limit)
