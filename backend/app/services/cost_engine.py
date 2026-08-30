"""
Cost Engine - Phase 6.

Pure calculation functions with no database or network dependency, so
they can be unit tested exhaustively and reused identically for both
the pre-call *estimate* and the post-call *actual* cost (see
docs/01-requirements.md FR3 and NFR4: every cost figure must be
traceable to the token counts and price used, and clearly labeled as
estimated or actual).

Money is handled with Decimal throughout, never float, to avoid
floating-point rounding error in financial figures.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


# Cost figures are rounded to 6 decimal places (matches the
# NUMERIC(10,6) columns in usage_metrics / pricing_history - see
# docs/03-database.md) - fine-grained enough for sub-cent per-request
# pricing common with small models, without implying false precision
# beyond what the schema stores.
COST_DECIMAL_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class PricingSnapshot:
    """The price of a model at a single point in time - mirrors one row
    of the `pricing_history` table (docs/03-database.md)."""

    model_id: str
    input_price_per_1k: Decimal
    output_price_per_1k: Decimal

    def __post_init__(self):
        # Accept ints/floats/strings at construction time for convenience,
        # but always store as Decimal internally.
        object.__setattr__(self, "input_price_per_1k", _to_decimal(self.input_price_per_1k))
        object.__setattr__(self, "output_price_per_1k", _to_decimal(self.output_price_per_1k))


@dataclass(frozen=True)
class CostBreakdown:
    """Result of a cost calculation - always shows its work."""

    input_tokens: int
    output_tokens: int
    input_price_per_1k: Decimal
    output_price_per_1k: Decimal
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal
    is_estimate: bool
    model_id: str

    def as_dict(self) -> dict:
        """JSON-serializable form for API responses / persistence."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_price_per_1k": str(self.input_price_per_1k),
            "output_price_per_1k": str(self.output_price_per_1k),
            "input_cost_usd": str(self.input_cost_usd),
            "output_cost_usd": str(self.output_cost_usd),
            "total_cost_usd": str(self.total_cost_usd),
            "is_estimate": self.is_estimate,
            "model_id": self.model_id,
        }


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_cost(value: Decimal) -> Decimal:
    return value.quantize(COST_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    pricing: PricingSnapshot,
    *,
    is_estimate: bool,
) -> CostBreakdown:
    """Core cost formula (docs/01-requirements.md section 6):

        input_cost  = input_tokens  / 1000 * input_price_per_1k
        output_cost = output_tokens / 1000 * output_price_per_1k
        total_cost  = input_cost + output_cost
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative")

    input_cost = _round_cost((Decimal(input_tokens) / Decimal(1000)) * pricing.input_price_per_1k)
    output_cost = _round_cost((Decimal(output_tokens) / Decimal(1000)) * pricing.output_price_per_1k)
    total_cost = _round_cost(input_cost + output_cost)

    return CostBreakdown(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_price_per_1k=pricing.input_price_per_1k,
        output_price_per_1k=pricing.output_price_per_1k,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
        is_estimate=is_estimate,
        model_id=pricing.model_id,
    )


def estimate_cost(input_tokens: int, output_tokens: int, pricing: PricingSnapshot) -> CostBreakdown:
    """Pre-call cost estimate, from the Task Analyzer's token estimate.
    NEVER present this as an actual charge (docs/01-requirements.md
    section 7) - the `is_estimate=True` flag exists precisely so
    callers (API responses, persistence) can't accidentally conflate
    the two."""
    return calculate_cost(input_tokens, output_tokens, pricing, is_estimate=True)


def actual_cost(input_tokens: int, output_tokens: int, pricing: PricingSnapshot) -> CostBreakdown:
    """Post-call cost, computed from the provider's reported actual
    token usage (ProviderResponse.input_tokens / output_tokens)."""
    return calculate_cost(input_tokens, output_tokens, pricing, is_estimate=False)


def estimate_vs_actual_delta(estimate: CostBreakdown, actual: CostBreakdown) -> Decimal:
    """Signed difference (actual - estimate). Positive means the
    estimate undercounted; negative means it overcounted. Useful for
    later analysis of estimation accuracy (RQ3)."""
    if estimate.model_id != actual.model_id:
        raise ValueError("Cannot compare cost breakdowns for different models")
    return actual.total_cost_usd - estimate.total_cost_usd
