"""
Routing strategies - Stage 2 of the router (docs/02-architecture.md §6).

Each strategy implements the same interface and picks one candidate
from an already-filtered, already-eligible list. This is what makes
routing_strategy swappable via config without touching the filtering
logic in router.py (docs/01-requirements.md §4: "Start with a
transparent baseline algorithm before implementing more advanced
approaches").
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.routing.models import CandidateEvaluation

STRATEGY_BASELINE = "baseline"
STRATEGY_WEIGHTED_SCORING = "weighted_scoring"


class RoutingStrategy(ABC):
    name: str

    @abstractmethod
    def select(self, eligible: list[CandidateEvaluation]) -> tuple[CandidateEvaluation, str]:
        """Given a non-empty list of eligible candidates, return the
        chosen one plus a short human-readable reason. Callers are
        responsible for ensuring `eligible` is non-empty before calling."""
        raise NotImplementedError


class BaselineStrategy(RoutingStrategy):
    """MVP default: pick the lowest estimated-cost eligible candidate.
    Simple, transparent, and easy to justify in the write-up
    (docs/01-requirements.md §4) - the goal is NOT to always pick the
    cheapest model overall, but among models that already satisfy the
    quality floor, cheapest is the value-maximizing choice."""

    name = STRATEGY_BASELINE

    def select(self, eligible: list[CandidateEvaluation]) -> tuple[CandidateEvaluation, str]:
        cheapest = min(eligible, key=lambda c: c.estimated_cost.total_cost_usd)
        reason = (
            f"Baseline strategy: '{cheapest.model_name}' is the lowest-cost "
            f"eligible model (${cheapest.estimated_cost.total_cost_usd}) among "
            f"{len(eligible)} candidate(s) meeting the quality/budget constraints."
        )
        return cheapest, reason


class WeightedScoringStrategy(RoutingStrategy):
    """Post-baseline strategy: normalizes cost and quality to a common
    0-1 scale within the eligible candidate set, then takes a weighted
    sum. Weights are configurable so the tradeoff can be tuned/
    experimented with (docs/01-requirements.md §4, listed as one of
    the routing approaches to consider).

    Normalization matters here: an earlier version scored raw
    `1/cost`, which is unbounded and swamped the quality term
    regardless of how the weights were set (a cheap model's 1/cost can
    be orders of magnitude larger than a 0-1 quality score) - caught
    by test_weighted_scoring_prefers_quality_when_weighted_heavily
    during Phase 7 testing. Min-max normalizing cost within the
    candidate set (cheapest -> 1.0, most expensive -> 0.0) keeps both
    terms on the same 0-1 scale, so the weights actually control the
    tradeoff as intended.
    """

    name = STRATEGY_WEIGHTED_SCORING

    def __init__(self, weight_cost: float = 0.5, weight_quality: float = 0.4, weight_latency: float = 0.1):
        total = weight_cost + weight_quality + weight_latency
        if total <= 0:
            raise ValueError("Weights must sum to a positive number")
        self.weight_cost = weight_cost / total
        self.weight_quality = weight_quality / total
        self.weight_latency = weight_latency / total

    def select(self, eligible: list[CandidateEvaluation]) -> tuple[CandidateEvaluation, str]:
        costs = [float(c.estimated_cost.total_cost_usd) for c in eligible]
        min_cost, max_cost = min(costs), max(costs)
        cost_range = max_cost - min_cost

        def normalized_cost_score(cost: float) -> float:
            if cost_range == 0:
                return 1.0  # all candidates cost the same - cost doesn't differentiate them
            return (max_cost - cost) / cost_range  # cheapest -> 1.0, most expensive -> 0.0

        def score(candidate: CandidateEvaluation) -> float:
            cost_term = self.weight_cost * normalized_cost_score(float(candidate.estimated_cost.total_cost_usd))
            quality_term = self.weight_quality * (candidate.estimated_quality / 100.0)
            # Latency isn't available pre-call in this candidate shape yet
            # (no expected_latency_ms plumbed through CandidateEvaluation) -
            # contributes 0 for now; wiring it through is a natural next
            # step once historical latency data exists (post-MVP,
            # docs/01-requirements.md "historical-performance routing").
            latency_term = 0.0
            return cost_term + quality_term + latency_term

        scored = [(c, score(c)) for c in eligible]
        best, best_score = max(scored, key=lambda pair: pair[1])
        reason = (
            f"Weighted-scoring strategy: '{best.model_name}' scored highest "
            f"({best_score:.4f}) among {len(eligible)} candidate(s) using "
            f"weights cost={self.weight_cost:.2f}, quality={self.weight_quality:.2f}, "
            f"latency={self.weight_latency:.2f} (cost normalized within candidate set)."
        )
        return best, reason


def get_strategy(name: str) -> RoutingStrategy:
    if name == STRATEGY_BASELINE:
        return BaselineStrategy()
    if name == STRATEGY_WEIGHTED_SCORING:
        return WeightedScoringStrategy()
    raise ValueError(f"Unknown routing strategy: {name}")
