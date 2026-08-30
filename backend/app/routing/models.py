"""
Data models for the Model Router (docs/02-architecture.md §6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services.cost_engine import CostBreakdown, PricingSnapshot


@dataclass(frozen=True)
class ModelCandidate:
    """A model available for routing, as pulled from the registry
    (docs/03-database.md `models` + `providers` + current `pricing_history`)."""

    model_id: str
    provider_name: str
    model_name: str
    estimated_quality: int  # 0-100
    pricing: PricingSnapshot
    context_limit: int
    status: str = "active"
    expected_latency_ms: int | None = None

    def __post_init__(self):
        if not 0 <= self.estimated_quality <= 100:
            raise ValueError("estimated_quality must be between 0 and 100")


@dataclass(frozen=True)
class RoutingConstraints:
    """Constraints supplied by the caller for a single routing decision
    (docs/01-requirements.md FR6: user-configured quality threshold and budget)."""

    min_quality: int = 0
    remaining_budget_usd: Decimal | None = None  # None = unconstrained
    exclude_model_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if not 0 <= self.min_quality <= 100:
            raise ValueError("min_quality must be between 0 and 100")


@dataclass(frozen=True)
class CandidateEvaluation:
    """One candidate's evaluation outcome - this is what gets stored,
    verbatim, in optimization_results.candidates_considered
    (docs/03-database.md) for auditability (NFR6)."""

    model_id: str
    provider_name: str
    model_name: str
    estimated_quality: int
    estimated_cost: CostBreakdown
    eligible: bool
    ineligible_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "estimated_quality": self.estimated_quality,
            "estimated_cost_usd": str(self.estimated_cost.total_cost_usd),
            "eligible": self.eligible,
            "ineligible_reason": self.ineligible_reason,
        }


@dataclass(frozen=True)
class RoutingDecision:
    """Full output of a routing decision - maps directly onto the
    `optimization_results` table (docs/03-database.md)."""

    chosen: ModelCandidate | None
    routing_strategy: str
    candidates_considered: list[CandidateEvaluation]
    chosen_reason: str
    fallback_triggered: bool = False

    def as_optimization_result_dict(self) -> dict:
        return {
            "routing_strategy": self.routing_strategy,
            "candidates_considered": [c.as_dict() for c in self.candidates_considered],
            "chosen_model_id": self.chosen.model_id if self.chosen else None,
            "chosen_reason": self.chosen_reason,
            "fallback_triggered": self.fallback_triggered,
        }
