"""
Tests for Phase 5: provider adapter interface, mock adapter, and the
adapter factory. Real provider adapters (OpenAI/Anthropic/Gemini) are
exercised for import/construction correctness only here - actual live
API calls are out of scope for unit tests (no API credits budgeted
for CI) and will be covered by a manual integration check once real
keys are available.
"""
import pytest

from app.providers.base import RequestParams
from app.providers.factory import get_adapter
from app.providers.mock_adapter import MockAdapter, make_mock_tier


def test_mock_adapter_estimate_tokens():
    adapter = MockAdapter(model_name="test-model")
    estimate = adapter.estimate_tokens("Hello, how are you today?", RequestParams())
    assert estimate.input_tokens > 0
    assert estimate.output_tokens > 0


def test_mock_adapter_send_request_success():
    adapter = MockAdapter(model_name="test-model")
    response = adapter.send_request("What is the capital of Kenya?", RequestParams())
    assert response.text
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.latency_ms >= 0
    assert response.finish_reason == "stop"


def test_mock_adapter_capabilities():
    adapter = MockAdapter(model_name="test-model", context_limit=32000)
    caps = adapter.get_model_capabilities()
    assert caps.model_name == "test-model"
    assert caps.context_limit == 32000


@pytest.mark.parametrize(
    "failure_mode,expected_exception",
    [
        ("timeout", "ProviderTimeoutError"),
        ("rate_limit", "ProviderRateLimitError"),
        ("invalid_credentials", "InvalidProviderCredentialsError"),
        ("unavailable", "ProviderUnavailableError"),
    ],
)
def test_mock_adapter_failure_modes(failure_mode, expected_exception):
    """Confirms each failure mode raises the correct common exception
    type - this is what the Model Router's fallback logic (Phase 7)
    will depend on."""
    from app.core import errors as app_errors

    adapter = MockAdapter(model_name="test-model", failure_mode=failure_mode)
    exception_cls = getattr(app_errors, expected_exception)
    with pytest.raises(exception_cls):
        adapter.send_request("test prompt", RequestParams())


def test_mock_tier_factory():
    cheap = make_mock_tier("cheap")
    mid = make_mock_tier("mid")
    premium = make_mock_tier("premium")
    assert cheap.context_limit < mid.context_limit < premium.context_limit

    with pytest.raises(ValueError):
        make_mock_tier("nonexistent")


def test_factory_returns_mock_adapter():
    adapter = get_adapter("mock", "any-model-name")
    assert isinstance(adapter, MockAdapter)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_adapter("not-a-real-provider", "some-model")


def test_factory_rejects_missing_api_key():
    """Without .env configured, real provider keys are empty strings -
    the factory should fail clearly rather than construct a client
    that will fail confusingly later."""
    with pytest.raises(ValueError, match="No API key configured"):
        get_adapter("openai", "gpt-4o-mini")


def test_real_adapters_importable():
    """Confirms the OpenAI/Anthropic/Gemini adapter modules import
    cleanly and their SDKs are installed correctly, without making
    any network call."""
    from app.providers.anthropic_adapter import AnthropicAdapter  # noqa: F401
    from app.providers.gemini_adapter import GeminiAdapter  # noqa: F401
    from app.providers.openai_adapter import OpenAIAdapter  # noqa: F401
