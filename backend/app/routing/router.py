"""
Model Router - Stage 1 (filtering) of docs/02-architecture.md §6,
orchestrating candidate evaluation and delegating final selection to
a pluggable RoutingStrategy (Stage 2, app/routing/strategies.py).
"""
from __future__ import annotations

from app.core.errors import NoEligibleModelError
from app.routing.models import CandidateEvaluation, ModelCandidate, RoutingConstraints, RoutingDecision
from app.routing.strategies import STRATEGY_BASELINE, RoutingStrategy, get_strategy
from app.services.cost_engine import estimate_cost


class ModelRouter:
    def __init__(self, strategy: RoutingStrategy | str = STRATEGY_BASELINE):
        self.strategy = strategy if isinstance(strategy, RoutingStrategy) else get_strategy(strategy)

    def _evaluate_candidates(
        self,
        candidates: list[ModelCandidate],
        input_tokens: int,
        output_tokens: int,
        constraints: RoutingConstraints,
    ) -> list[CandidateEvaluation]:
        evaluations: list[CandidateEvaluation] = []

        for candidate in candidates:
            estimated = estimate_cost(input_tokens, output_tokens, candidate.pricing)

            ineligible_reasons = []
            if candidate.status != "active":
                ineligible_reasons.append(f"status is '{candidate.status}', not 'active'")
            if candidate.model_id in constraints.exclude_model_ids:
                ineligible_reasons.append("excluded (e.g. previously failed in this request)")
            if candidate.estimated_quality < constraints.min_quality:
                ineligible_reasons.append(
                    f"estimated_quality {candidate.estimated_quality} < required {constraints.min_quality}"
                )
            if constraints.remaining_budget_usd is not None and estimated.total_cost_usd > constraints.remaining_budget_usd:
                ineligible_reasons.append(
                    f"estimated cost ${estimated.total_cost_usd} exceeds remaining budget "
                    f"${constraints.remaining_budget_usd}"
                )

            evaluations.append(
                CandidateEvaluation(
                    model_id=candidate.model_id,
                    provider_name=candidate.provider_name,
                    model_name=candidate.model_name,
                    estimated_quality=candidate.estimated_quality,
                    estimated_cost=estimated,
                    eligible=len(ineligible_reasons) == 0,
                    ineligible_reason="; ".join(ineligible_reasons) if ineligible_reasons else None,
                )
            )

        return evaluations

    def route(
        self,
        candidates: list[ModelCandidate],
        input_tokens: int,
        output_tokens: int,
        constraints: RoutingConstraints | None = None,
    ) -> RoutingDecision:
        """Select the best model for a task given constraints.

        Raises NoEligibleModelError if no candidate satisfies the
        quality/budget constraints - callers (API layer) should map
        this to a clear error for the user rather than silently
        picking an ineligible model (docs/01-requirements.md §12:
        "no available model satisfies the quality requirement" is an
        explicitly designed-for case, not an afterthought).
        """
        constraints = constraints or RoutingConstraints()

        if not candidates:
            raise NoEligibleModelError("No candidate models were provided to the router.")

        evaluations = self._evaluate_candidates(candidates, input_tokens, output_tokens, constraints)
        eligible = [e for e in evaluations if e.eligible]

        if not eligible:
            raise NoEligibleModelError(
                f"No model meets the constraints (min_quality={constraints.min_quality}, "
                f"remaining_budget={constraints.remaining_budget_usd}) among "
                f"{len(evaluations)} candidate(s) considered."
            )

        chosen_eval, reason = self.strategy.select(eligible)
        chosen_candidate = next(c for c in candidates if c.model_id == chosen_eval.model_id)

        return RoutingDecision(
            chosen=chosen_candidate,
            routing_strategy=self.strategy.name,
            candidates_considered=evaluations,
            chosen_reason=reason,
            fallback_triggered=False,
        )

    def route_with_fallback(
        self,
        candidates: list[ModelCandidate],
        input_tokens: int,
        output_tokens: int,
        constraints: RoutingConstraints | None = None,
        max_attempts: int = 2,
    ) -> list[RoutingDecision]:
        """Returns an ordered list of routing decisions to try, bounded
        by max_attempts (docs/01-requirements.md FR8: fallback without
        an uncontrolled retry loop). The caller (API layer / execution
        pipeline) attempts them in order, calling the provider adapter
        for decisions[0]; on failure it moves to decisions[1], excluding
        the failed model, and so on - it does NOT keep retrying beyond
        what this method returns.
        """
        constraints = constraints or RoutingConstraints()
        decisions: list[RoutingDecision] = []
        excluded: set[str] = set(constraints.exclude_model_ids)

        for attempt in range(max_attempts):
            attempt_constraints = RoutingConstraints(
                min_quality=constraints.min_quality,
                remaining_budget_usd=constraints.remaining_budget_usd,
                exclude_model_ids=frozenset(excluded),
            )
            try:
                decision = self.route(candidates, input_tokens, output_tokens, attempt_constraints)
            except NoEligibleModelError:
                break

            if attempt > 0:
                decision = RoutingDecision(
                    chosen=decision.chosen,
                    routing_strategy=decision.routing_strategy,
                    candidates_considered=decision.candidates_considered,
                    chosen_reason=decision.chosen_reason,
                    fallback_triggered=True,
                )

            decisions.append(decision)
            if decision.chosen:
                excluded.add(decision.chosen.model_id)

        if not decisions:
            raise NoEligibleModelError("No eligible model found for the primary attempt or any fallback.")

        return decisions
