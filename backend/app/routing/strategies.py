"""Pluggable routing strategies used after constraint filtering."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.routing.models import CandidateEvaluation

STRATEGY_BASELINE = "baseline"
STRATEGY_WEIGHTED_SCORING = "weighted_scoring"


class RoutingStrategy(ABC):
    name: str

    @abstractmethod
    def select(self, eligible: list[CandidateEvaluation]) -> tuple[CandidateEvaluation, str]:
        raise NotImplementedError


class BaselineStrategy(RoutingStrategy):
    """Transparent baseline: choose the lowest-cost eligible model."""

    name = STRATEGY_BASELINE

    def select(self, eligible: list[CandidateEvaluation]) -> tuple[CandidateEvaluation, str]:
        cheapest = min(eligible, key=lambda c: c.estimated_cost.total_cost_usd)
        return cheapest, (
            f"Baseline strategy: '{cheapest.model_name}' is the lowest-cost eligible model "
            f"(${cheapest.estimated_cost.total_cost_usd}) among {len(eligible)} candidate(s)."
        )


class WeightedScoringStrategy(RoutingStrategy):
    """Balance normalized cost, estimated quality and historical latency.

    Missing latency is neutral rather than punitive. This means new models
    can still be selected while models with measured latency receive the
    latency component of the score.
    """

    name = STRATEGY_WEIGHTED_SCORING

    def __init__(self, weight_cost: float = 0.5, weight_quality: float = 0.4, weight_latency: float = 0.1):
        if min(weight_cost, weight_quality, weight_latency) < 0:
            raise ValueError("Weights cannot be negative")
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

        latencies = [c.expected_latency_ms for c in eligible if c.expected_latency_ms is not None]
        min_latency = min(latencies) if latencies else None
        max_latency = max(latencies) if latencies else None
        latency_range = (max_latency - min_latency) if min_latency is not None and max_latency is not None else 0

        def cost_score(cost: float) -> float:
            return 1.0 if cost_range == 0 else (max_cost - cost) / cost_range

        def latency_score(latency: int | None) -> float:
            if latency is None or min_latency is None or max_latency is None:
                return 0.5
            return 1.0 if latency_range == 0 else (max_latency - latency) / latency_range

        def score(candidate: CandidateEvaluation) -> float:
            return (
                self.weight_cost * cost_score(float(candidate.estimated_cost.total_cost_usd))
                + self.weight_quality * (candidate.estimated_quality / 100.0)
                + self.weight_latency * latency_score(candidate.expected_latency_ms)
            )

        best, best_score = max(((c, score(c)) for c in eligible), key=lambda pair: pair[1])
        return best, (
            f"Weighted-scoring strategy: '{best.model_name}' scored {best_score:.4f} using "
            f"cost={self.weight_cost:.2f}, quality={self.weight_quality:.2f}, "
            f"latency={self.weight_latency:.2f}."
        )


def get_strategy(name: str) -> RoutingStrategy:
    if name == STRATEGY_BASELINE:
        return BaselineStrategy()
    if name == STRATEGY_WEIGHTED_SCORING:
        return WeightedScoringStrategy()
    raise ValueError(f"Unknown routing strategy: {name}")
