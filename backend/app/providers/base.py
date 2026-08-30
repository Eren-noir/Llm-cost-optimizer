"""
Common provider adapter interface - see docs/02-architecture.md, section 5
"Provider Abstraction".

Every concrete adapter (mock, OpenAI, Anthropic, Gemini) implements
LLMProviderAdapter and returns the same normalized dataclasses, so
nothing outside this package ever imports a provider SDK directly or
branches on "which provider is this".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RequestParams:
    """Parameters for a single generation request, provider-agnostic."""

    max_output_tokens: int = 1024
    temperature: float = 0.7
    system_prompt: str | None = None


@dataclass
class TokenEstimate:
    """Pre-call estimate of token usage, used by the Cost Engine to
    compute an *estimated* cost before any request is sent."""

    input_tokens: int
    output_tokens: int


@dataclass
class ProviderResponse:
    """Normalized response shape, regardless of which provider produced it."""

    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    finish_reason: str
    raw_response: dict = field(default_factory=dict)


@dataclass
class ModelCapabilities:
    model_name: str
    context_limit: int
    supports_system_prompt: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False


class LLMProviderAdapter(ABC):
    """Abstract interface every provider adapter must implement.

    Implementations MUST translate provider-specific errors (timeouts,
    rate limits, invalid credentials, etc.) into the common exception
    types defined in app.core.errors, so the Model Router (Phase 7)
    never needs to know which provider raised what.
    """

    provider_name: str
    model_name: str

    @abstractmethod
    def estimate_tokens(self, prompt: str, params: RequestParams) -> TokenEstimate:
        """Cheap, local estimate of token usage - no network call."""
        raise NotImplementedError

    @abstractmethod
    def send_request(self, prompt: str, params: RequestParams) -> ProviderResponse:
        """Send the prompt to the provider and return a normalized response.

        Must raise one of the app.core.errors.AppError subclasses on
        failure (ProviderTimeoutError, ProviderRateLimitError,
        InvalidProviderCredentialsError, ProviderUnavailableError) -
        never a raw provider SDK exception.
        """
        raise NotImplementedError

    @abstractmethod
    def get_model_capabilities(self) -> ModelCapabilities:
        raise NotImplementedError
