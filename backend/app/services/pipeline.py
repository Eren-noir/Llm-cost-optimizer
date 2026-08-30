"""
Request pipeline - orchestrates the full flow described in
docs/02-architecture.md §4 "Data Flow (request lifecycle)":

    Task Analyzer -> Model Router -> Provider Adapter -> Cost Engine
    -> Quality Evaluator -> Persistence

This is the one place that wires Phases 5-8 together end to end. The
API layer calls this; it does not re-implement any of this
orchestration itself.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.evaluation.rubric_evaluator import RubricEvaluator
from app.models import orm
from app.providers.base import RequestParams
from app.providers.factory import get_adapter
from app.routing.models import ModelCandidate, RoutingConstraints
from app.routing.router import ModelRouter
from app.services.cost_engine import actual_cost, estimate_cost
from app.services.task_analyzer import DEFAULT_OUTPUT_TOKENS_BY_COMPLEXITY, estimate_complexity


def _load_candidates(db: Session) -> list[ModelCandidate]:
    """Pull active models + their current price from the registry and
    turn them into router-ready ModelCandidate objects."""
    from sqlalchemy import select

    from app.services.pricing_repository import PricingNotFoundError, get_current_pricing

    rows = db.execute(
        select(orm.LLMModel, orm.Provider)
        .join(orm.Provider, orm.LLMModel.provider_id == orm.Provider.id)
        .where(orm.LLMModel.status == "active")
        .where(orm.Provider.status == "active")
    ).all()

    candidates = []
    for model_row, provider_row in rows:
        try:
            pricing = get_current_pricing(db, model_row.id)
        except PricingNotFoundError:
            continue  # skip models with no priced entry rather than failing the whole request
        candidates.append(
            ModelCandidate(
                model_id=str(model_row.id),
                provider_name=provider_row.name,
                model_name=model_row.model_name,
                estimated_quality=model_row.estimated_quality,
                pricing=pricing,
                context_limit=model_row.context_limit,
                status=model_row.status,
            )
        )
    return candidates


def run_request_pipeline(
    db: Session,
    user_id: uuid.UUID,
    prompt: str,
    mode: str = "auto",
    min_quality: int = 0,
    remaining_budget_usd: Decimal | None = None,
    manual_model_id: str | None = None,
) -> orm.RequestLog:
    """Runs one task through the full pipeline and persists every
    stage. Returns the persisted RequestLog (with its relationships
    loaded) so the API layer can serialize it directly.

    mode='manual' requires manual_model_id and skips routing.
    mode='auto' (default) routes automatically under the given
    constraints. mode='comparison' fans out to multiple models and is
    handled separately in the API layer - it doesn't fit this
    single-model-per-call shape.
    """
    complexity = estimate_complexity(prompt)
    expected_output_tokens = DEFAULT_OUTPUT_TOKENS_BY_COMPLEXITY[complexity.complexity]

    candidates = _load_candidates(db)

    if mode == "manual":
        if not manual_model_id:
            raise AppError("manual_model_id is required when mode='manual'")
        chosen_candidate = next((c for c in candidates if c.model_id == manual_model_id), None)
        if chosen_candidate is None:
            raise AppError(f"Model {manual_model_id} not found or not active/priced")
        routing_strategy = "manual"
        routing_reason = f"User manually selected '{chosen_candidate.model_name}'."
        candidates_considered_dicts = [
            {
                "model_id": chosen_candidate.model_id,
                "provider_name": chosen_candidate.provider_name,
                "model_name": chosen_candidate.model_name,
                "estimated_quality": chosen_candidate.estimated_quality,
                "eligible": True,
                "ineligible_reason": None,
            }
        ]
        fallback_triggered = False
    else:
        router = ModelRouter()
        constraints = RoutingConstraints(min_quality=min_quality, remaining_budget_usd=remaining_budget_usd)
        decision = router.route(
            candidates,
            input_tokens=complexity.input_tokens_estimated,
            output_tokens=expected_output_tokens,
            constraints=constraints,
        )
        chosen_candidate = decision.chosen
        routing_strategy = decision.routing_strategy
        routing_reason = decision.chosen_reason
        candidates_considered_dicts = [c.as_dict() for c in decision.candidates_considered]
        fallback_triggered = decision.fallback_triggered

    # Estimated cost, pre-call
    est_breakdown = estimate_cost(complexity.input_tokens_estimated, expected_output_tokens, chosen_candidate.pricing)

    # Send the actual request
    adapter = get_adapter(chosen_candidate.provider_name, chosen_candidate.model_name, chosen_candidate.context_limit)
    params = RequestParams(max_output_tokens=expected_output_tokens)
    request_status = "success"
    try:
        provider_response = adapter.send_request(prompt, params)
    except AppError:
        request_status = "failed"
        raise  # API layer decides whether/how to fall back - see route_with_fallback for that path

    # Actual cost, post-call - always from the provider's own reported usage
    act_breakdown = actual_cost(provider_response.input_tokens, provider_response.output_tokens, chosen_candidate.pricing)

    # Quality (rubric - free, runs on every request; LLM-judge is opt-in
    # and costs an extra call, wired up by callers that want it)
    quality = RubricEvaluator().evaluate(prompt, provider_response, expected_output_tokens)

    # Persist everything
    request_row = orm.RequestLog(
        user_id=user_id,
        mode=mode,
        prompt_text=prompt,
        estimated_complexity=complexity.complexity,
        model_id=uuid.UUID(chosen_candidate.model_id),
        status=request_status,
    )
    db.add(request_row)
    db.flush()  # assign request_row.id without committing yet

    db.add(orm.ResponseLog(
        request_id=request_row.id,
        response_text=provider_response.text,
        finish_reason=provider_response.finish_reason,
        raw_response=provider_response.raw_response,
    ))
    db.add(orm.UsageMetrics(
        request_id=request_row.id,
        input_tokens_estimated=complexity.input_tokens_estimated,
        output_tokens_estimated=expected_output_tokens,
        input_tokens_actual=provider_response.input_tokens,
        output_tokens_actual=provider_response.output_tokens,
        latency_ms=provider_response.latency_ms,
        estimated_cost_usd=est_breakdown.total_cost_usd,
        actual_cost_usd=act_breakdown.total_cost_usd,
    ))
    db.add(orm.QualityEvaluation(
        request_id=request_row.id,
        quality_score=quality.score,
        evaluation_method=quality.method,
        evaluator_notes=quality.notes,
    ))
    db.add(orm.OptimizationResult(
        request_id=request_row.id,
        routing_strategy=routing_strategy,
        candidates_considered=candidates_considered_dicts,
        chosen_model_id=uuid.UUID(chosen_candidate.model_id),
        chosen_reason=routing_reason,
        fallback_triggered=fallback_triggered,
    ))

    db.commit()
    db.refresh(request_row)
    return request_row
