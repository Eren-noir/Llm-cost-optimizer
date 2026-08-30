"""
Token tracking - thin glue between the provider adapter layer
(Phase 5's TokenEstimate / ProviderResponse) and the cost engine
(Phase 6's estimate_cost / actual_cost), so callers don't have to
know the field names on both sides.
"""
from __future__ import annotations

from app.providers.base import ProviderResponse, TokenEstimate
from app.services.cost_engine import CostBreakdown, PricingSnapshot, actual_cost, estimate_cost


def cost_from_estimate(token_estimate: TokenEstimate, pricing: PricingSnapshot) -> CostBreakdown:
    """Pre-call: turn a Task Analyzer / adapter token estimate into an
    estimated CostBreakdown."""
    return estimate_cost(token_estimate.input_tokens, token_estimate.output_tokens, pricing)


def cost_from_response(provider_response: ProviderResponse, pricing: PricingSnapshot) -> CostBreakdown:
    """Post-call: turn a provider's actual reported usage into an
    actual CostBreakdown. Always use the token counts the provider
    itself reports (ProviderResponse.input_tokens/output_tokens) -
    never re-estimate after the fact."""
    return actual_cost(provider_response.input_tokens, provider_response.output_tokens, pricing)
