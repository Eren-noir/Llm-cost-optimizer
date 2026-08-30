"""
Tests for Phase 6: cost engine.

All tests here exercise pure functions with no database - see
app/services/pricing_repository.py's module docstring for why the
DB-backed pricing registry itself isn't covered by automated tests in
this sandbox (no live Postgres instance available here).
"""
from decimal import Decimal

import pytest

from app.providers.base import ProviderResponse, TokenEstimate
from app.services.cost_engine import (
    PricingSnapshot,
    actual_cost,
    estimate_cost,
    estimate_vs_actual_delta,
)
from app.services.token_tracking import cost_from_estimate, cost_from_response


@pytest.fixture
def cheap_pricing():
    # e.g. a "mini" tier model: $0.15 / 1M input, $0.60 / 1M output
    # expressed here per-1k as the schema stores it.
    return PricingSnapshot(
        model_id="model-cheap",
        input_price_per_1k=Decimal("0.00015"),
        output_price_per_1k=Decimal("0.0006"),
    )


@pytest.fixture
def premium_pricing():
    # e.g. a frontier model: $5 / 1M input, $25 / 1M output
    return PricingSnapshot(
        model_id="model-premium",
        input_price_per_1k=Decimal("0.005"),
        output_price_per_1k=Decimal("0.025"),
    )


def test_calculate_cost_basic_arithmetic(cheap_pricing):
    result = estimate_cost(input_tokens=1000, output_tokens=1000, pricing=cheap_pricing)
    assert result.input_cost_usd == Decimal("0.000150")
    assert result.output_cost_usd == Decimal("0.000600")
    assert result.total_cost_usd == Decimal("0.000750")


def test_calculate_cost_scales_linearly(cheap_pricing):
    small = estimate_cost(500, 500, cheap_pricing)
    large = estimate_cost(5000, 5000, cheap_pricing)
    # 10x the tokens should be ~10x the cost
    assert large.total_cost_usd == small.total_cost_usd * 10


def test_calculate_cost_zero_tokens(cheap_pricing):
    result = estimate_cost(0, 0, cheap_pricing)
    assert result.total_cost_usd == Decimal("0.000000")


def test_calculate_cost_rejects_negative_tokens(cheap_pricing):
    with pytest.raises(ValueError):
        estimate_cost(-10, 100, cheap_pricing)


def test_estimate_is_flagged_correctly(cheap_pricing):
    result = estimate_cost(100, 100, cheap_pricing)
    assert result.is_estimate is True


def test_actual_is_flagged_correctly(cheap_pricing):
    result = actual_cost(100, 100, cheap_pricing)
    assert result.is_estimate is False


def test_premium_model_costs_more_than_cheap_model_for_same_tokens(cheap_pricing, premium_pricing):
    cheap_result = estimate_cost(1000, 500, cheap_pricing)
    premium_result = estimate_cost(1000, 500, premium_pricing)
    assert premium_result.total_cost_usd > cheap_result.total_cost_usd


def test_cost_breakdown_shows_its_work(cheap_pricing):
    """NFR4: every cost figure must be traceable to token counts + price used."""
    result = estimate_cost(2000, 1000, cheap_pricing)
    d = result.as_dict()
    assert d["input_tokens"] == 2000
    assert d["output_tokens"] == 1000
    assert d["input_price_per_1k"] == "0.00015"
    assert d["output_price_per_1k"] == "0.0006"
    # total should be reconstructable from the parts shown
    reconstructed = Decimal(d["input_cost_usd"]) + Decimal(d["output_cost_usd"])
    assert reconstructed == Decimal(d["total_cost_usd"])


def test_estimate_vs_actual_delta_positive_when_underestimated(cheap_pricing):
    estimate = estimate_cost(1000, 500, cheap_pricing)
    actual = actual_cost(1000, 800, cheap_pricing)  # more output tokens than estimated
    delta = estimate_vs_actual_delta(estimate, actual)
    assert delta > 0  # actual cost higher than estimated


def test_estimate_vs_actual_delta_rejects_mismatched_models(cheap_pricing, premium_pricing):
    estimate = estimate_cost(1000, 500, cheap_pricing)
    actual = actual_cost(1000, 500, premium_pricing)
    with pytest.raises(ValueError):
        estimate_vs_actual_delta(estimate, actual)


def test_token_tracking_from_estimate(cheap_pricing):
    token_estimate = TokenEstimate(input_tokens=300, output_tokens=150)
    result = cost_from_estimate(token_estimate, cheap_pricing)
    assert result.is_estimate is True
    assert result.input_tokens == 300
    assert result.output_tokens == 150


def test_token_tracking_from_provider_response(cheap_pricing):
    response = ProviderResponse(
        text="hello world",
        input_tokens=42,
        output_tokens=17,
        latency_ms=120,
        finish_reason="stop",
    )
    result = cost_from_response(response, cheap_pricing)
    assert result.is_estimate is False
    assert result.input_tokens == 42
    assert result.output_tokens == 17


def test_pricing_snapshot_accepts_various_numeric_types():
    # float, int, string should all coerce cleanly to Decimal
    p1 = PricingSnapshot(model_id="a", input_price_per_1k=0.001, output_price_per_1k=0.002)
    p2 = PricingSnapshot(model_id="a", input_price_per_1k="0.001", output_price_per_1k="0.002")
    assert p1.input_price_per_1k == p2.input_price_per_1k
