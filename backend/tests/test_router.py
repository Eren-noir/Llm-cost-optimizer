"""
Tests for Phase 7: Task Analyzer and Model Router.
"""
from decimal import Decimal

import pytest

from app.core.errors import NoEligibleModelError
from app.routing.models import ModelCandidate, RoutingConstraints
from app.routing.router import ModelRouter
from app.routing.strategies import (
    STRATEGY_BASELINE,
    STRATEGY_WEIGHTED_SCORING,
    BaselineStrategy,
    WeightedScoringStrategy,
    get_strategy,
)
from app.services.cost_engine import PricingSnapshot
from app.services.task_analyzer import (
    COMPLEXITY_COMPLEX,
    COMPLEXITY_MEDIUM,
    COMPLEXITY_SIMPLE,
    estimate_complexity,
)


# --- Task Analyzer tests -----------------------------------------------

def test_task_analyzer_simple_prompt():
    result = estimate_complexity("What is the capital of Kenya?")
    assert result.complexity == COMPLEXITY_SIMPLE


def test_task_analyzer_complex_keyword():
    result = estimate_complexity("Prove that this recursive algorithm terminates.")
    assert result.complexity == COMPLEXITY_COMPLEX
    assert "keyword" in result.reasoning


def test_task_analyzer_medium_keyword():
    result = estimate_complexity("Summarize this article for me in a few sentences.")
    assert result.complexity == COMPLEXITY_MEDIUM


def test_task_analyzer_long_prompt_escalates():
    long_prompt = "word " * 400  # ~500 tokens at ~4 chars/token heuristic
    result = estimate_complexity(long_prompt)
    assert result.complexity in (COMPLEXITY_MEDIUM, COMPLEXITY_COMPLEX)


def test_task_analyzer_empty_prompt():
    result = estimate_complexity("")
    assert result.complexity == COMPLEXITY_SIMPLE
    assert result.input_tokens_estimated == 0


# --- Fixtures: the worked example from docs/01-requirements.md §4 ------

def _make_candidate(model_id, quality, input_price, output_price, status="active"):
    return ModelCandidate(
        model_id=model_id,
        provider_name="mock",
        model_name=model_id,
        estimated_quality=quality,
        pricing=PricingSnapshot(model_id=model_id, input_price_per_1k=input_price, output_price_per_1k=output_price),
        context_limit=32000,
        status=status,
    )


@pytest.fixture
def worked_example_candidates():
    """Mirrors docs/01-requirements.md's worked example:
    Model A: cost=$0.01, quality=65
    Model B: cost=$0.05, quality=84
    Model C: cost=$0.20, quality=93
    Priced so that ~1000 input/500 output tokens roughly produce those
    total costs, for a readable test fixture."""
    return [
        _make_candidate("model-a", 65, Decimal("0.0067"), Decimal("0.0067")),
        _make_candidate("model-b", 84, Decimal("0.0333"), Decimal("0.0333")),
        _make_candidate("model-c", 93, Decimal("0.1333"), Decimal("0.1333")),
    ]


# --- Router: filtering / eligibility -------------------------------------

def test_router_picks_cheapest_when_quality_threshold_is_low(worked_example_candidates):
    router = ModelRouter(strategy=STRATEGY_BASELINE)
    decision = router.route(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=0),
    )
    assert decision.chosen.model_id == "model-a"


def test_router_picks_model_b_when_quality_80_required(worked_example_candidates):
    """Matches the requirements doc's example: quality >= 80 -> Model B."""
    router = ModelRouter(strategy=STRATEGY_BASELINE)
    decision = router.route(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=80),
    )
    assert decision.chosen.model_id == "model-b"


def test_router_picks_model_c_when_quality_90_required(worked_example_candidates):
    """Matches the requirements doc's example: quality >= 90 -> Model C."""
    router = ModelRouter(strategy=STRATEGY_BASELINE)
    decision = router.route(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=90),
    )
    assert decision.chosen.model_id == "model-c"


def test_router_raises_when_no_model_meets_quality(worked_example_candidates):
    router = ModelRouter()
    with pytest.raises(NoEligibleModelError):
        router.route(
            worked_example_candidates, input_tokens=1000, output_tokens=500,
            constraints=RoutingConstraints(min_quality=99),
        )


def test_router_respects_budget_constraint(worked_example_candidates):
    router = ModelRouter()
    # Quality floor would pick model-c, but budget rules it out.
    decision = router.route(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=0, remaining_budget_usd=Decimal("0.05")),
    )
    assert decision.chosen.model_id in ("model-a", "model-b")
    assert decision.chosen.model_id != "model-c"


def test_router_raises_when_budget_too_low_for_any_model(worked_example_candidates):
    router = ModelRouter()
    with pytest.raises(NoEligibleModelError):
        router.route(
            worked_example_candidates, input_tokens=1000, output_tokens=500,
            constraints=RoutingConstraints(min_quality=0, remaining_budget_usd=Decimal("0.0001")),
        )


def test_router_excludes_inactive_models(worked_example_candidates):
    candidates = worked_example_candidates + [
        _make_candidate("model-cheap-disabled", 99, Decimal("0.0001"), Decimal("0.0001"), status="disabled")
    ]
    router = ModelRouter()
    decision = router.route(candidates, input_tokens=1000, output_tokens=500, constraints=RoutingConstraints(min_quality=90))
    assert decision.chosen.model_id == "model-c"  # the disabled cheap model is never chosen


def test_router_raises_on_empty_candidate_list():
    router = ModelRouter()
    with pytest.raises(NoEligibleModelError):
        router.route([], input_tokens=100, output_tokens=100)


def test_candidates_considered_includes_ineligible_with_reason(worked_example_candidates):
    router = ModelRouter()
    decision = router.route(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=90),
    )
    ineligible = [c for c in decision.candidates_considered if not c.eligible]
    assert len(ineligible) == 2  # model-a and model-b both fail the quality bar
    for c in ineligible:
        assert c.ineligible_reason is not None


# --- Router: strategies --------------------------------------------------

def test_get_strategy_returns_correct_type():
    assert isinstance(get_strategy(STRATEGY_BASELINE), BaselineStrategy)
    assert isinstance(get_strategy(STRATEGY_WEIGHTED_SCORING), WeightedScoringStrategy)
    with pytest.raises(ValueError):
        get_strategy("not-a-real-strategy")


def test_weighted_scoring_prefers_quality_when_weighted_heavily(worked_example_candidates):
    strategy = WeightedScoringStrategy(weight_cost=0.1, weight_quality=0.9, weight_latency=0.0)
    router = ModelRouter(strategy=strategy)
    decision = router.route(worked_example_candidates, input_tokens=1000, output_tokens=500)
    assert decision.chosen.model_id == "model-c"  # highest quality wins when quality dominates


def test_weighted_scoring_prefers_cost_when_weighted_heavily(worked_example_candidates):
    strategy = WeightedScoringStrategy(weight_cost=0.99, weight_quality=0.01, weight_latency=0.0)
    router = ModelRouter(strategy=strategy)
    decision = router.route(worked_example_candidates, input_tokens=1000, output_tokens=500)
    assert decision.chosen.model_id == "model-a"  # cheapest wins when cost dominates


# --- Router: fallback ------------------------------------------------------

def test_route_with_fallback_returns_ordered_decisions(worked_example_candidates):
    router = ModelRouter()
    decisions = router.route_with_fallback(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=0), max_attempts=2,
    )
    assert len(decisions) == 2
    assert decisions[0].chosen.model_id == "model-a"  # cheapest first
    assert decisions[0].fallback_triggered is False
    assert decisions[1].fallback_triggered is True
    assert decisions[1].chosen.model_id != decisions[0].chosen.model_id


def test_route_with_fallback_stops_when_no_more_eligible(worked_example_candidates):
    router = ModelRouter()
    # Only one model meets this quality bar, so fallback has nothing to offer.
    decisions = router.route_with_fallback(
        worked_example_candidates, input_tokens=1000, output_tokens=500,
        constraints=RoutingConstraints(min_quality=90), max_attempts=3,
    )
    assert len(decisions) == 1
    assert decisions[0].chosen.model_id == "model-c"


def test_route_with_fallback_raises_when_nothing_eligible_at_all(worked_example_candidates):
    router = ModelRouter()
    with pytest.raises(NoEligibleModelError):
        router.route_with_fallback(
            worked_example_candidates, input_tokens=1000, output_tokens=500,
            constraints=RoutingConstraints(min_quality=99), max_attempts=2,
        )


def test_optimization_result_dict_shape(worked_example_candidates):
    """Confirms the decision serializes into the shape optimization_results expects."""
    router = ModelRouter()
    decision = router.route(worked_example_candidates, input_tokens=1000, output_tokens=500)
    d = decision.as_optimization_result_dict()
    assert d["routing_strategy"] == STRATEGY_BASELINE
    assert d["chosen_model_id"] == decision.chosen.model_id
    assert isinstance(d["candidates_considered"], list)
    assert len(d["candidates_considered"]) == 3
