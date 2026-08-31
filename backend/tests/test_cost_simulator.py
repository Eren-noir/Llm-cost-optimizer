from decimal import Decimal

from app.services.cost_simulator import percentage_savings, project_model_cost


def test_monthly_projection_uses_input_and_output_prices():
    result = project_model_cost(
        "m1", "Test", "Provider", 10_000, 500, 300,
        Decimal("0.01"), Decimal("0.02"),
    )
    # Per request = .005 + .006 = .011; 10,000 requests = $110.
    assert result.monthly_cost_usd == Decimal("110.000000")


def test_zero_baseline_has_zero_savings():
    assert percentage_savings(Decimal("0"), Decimal("1")) == Decimal("0")


def test_savings_are_positive_when_optimized_is_cheaper():
    assert percentage_savings(Decimal("100"), Decimal("60")) == Decimal("40.00")
