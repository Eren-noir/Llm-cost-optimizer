"""Deterministic what-if LLM cost simulation.

This module deliberately contains no database or provider calls. It makes the
simulation easy to test and keeps projected cost separate from actual spend.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class ModelProjection:
    model_id: str
    model_name: str
    provider_name: str
    monthly_cost_usd: Decimal
    monthly_requests: int


def project_model_cost(
    model_id: str,
    model_name: str,
    provider_name: str,
    requests_per_month: int,
    input_tokens_per_request: int,
    output_tokens_per_request: int,
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
) -> ModelProjection:
    input_cost = (Decimal(input_tokens_per_request) / Decimal(1000)) * input_price_per_1k
    output_cost = (Decimal(output_tokens_per_request) / Decimal(1000)) * output_price_per_1k
    monthly = (input_cost + output_cost) * Decimal(requests_per_month)
    return ModelProjection(
        model_id=model_id,
        model_name=model_name,
        provider_name=provider_name,
        monthly_cost_usd=monthly.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        monthly_requests=requests_per_month,
    )


def percentage_savings(baseline: Decimal, optimized: Decimal) -> Decimal:
    if baseline <= 0:
        return Decimal("0")
    return ((baseline - optimized) / baseline * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
