"""
Request pipeline - orchestrates the full request lifecycle:

    Task Analyzer -> Model Router -> Provider Adapter -> Cost Engine
    -> Quality Evaluator -> Persistence

The API layer calls this function; it does not duplicate orchestration.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
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
    """Load active, priced models and attach historical average latency.

    Latency is advisory only: a model with no history gets ``None`` and
    remains eligible. This avoids making a new model unusable merely because
    it has not served a request yet.
    """
    from app.services.pricing_repository import PricingNotFoundError, get_current_pricing

    rows = db.execute(
        select(orm.LLMModel, orm.Provider)
        .join(orm.Provider, orm.LLMModel.provider_id == orm.Provider.id)
        .where(orm.LLMModel.status == "active")
        .where(orm.Provider.status == "active")
    ).all()

    latency_rows = db.execute(
        select(orm.RequestLog.model_id, func.avg(orm.UsageMetrics.latency_ms))
        .join(orm.UsageMetrics, orm.UsageMetrics.request_id == orm.RequestLog.id)
        .where(orm.RequestLog.status.in_(["success", "fallback_used"]))
        .group_by(orm.RequestLog.model_id)
    ).all()
    avg_latency_by_model = {
        str(model_id): int(round(float(avg_latency)))
        for model_id, avg_latency in latency_rows
        if avg_latency is not None
    }

    candidates: list[ModelCandidate] = []
    for model_row, provider_row in rows:
        try:
            pricing = get_current_pricing(db, model_row.id)
        except PricingNotFoundError:
            continue
        candidates.append(
            ModelCandidate(
                model_id=str(model_row.id),
                provider_name=provider_row.name,
                model_name=model_row.model_name,
                estimated_quality=model_row.estimated_quality,
                pricing=pricing,
                context_limit=model_row.context_limit,
                status=model_row.status,
                expected_latency_ms=avg_latency_by_model.get(str(model_row.id)),
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
    routing_strategy: str = "baseline",
) -> orm.RequestLog:
    """Run one task through analysis, routing, provider, cost, evaluation and persistence."""
    complexity = estimate_complexity(prompt)
    expected_output_tokens = DEFAULT_OUTPUT_TOKENS_BY_COMPLEXITY[complexity.complexity]
    candidates = _load_candidates(db)

    if mode in {"manual", "comparison"}:
        if not manual_model_id:
            raise AppError(f"manual_model_id is required when mode='{mode}'")
        chosen_candidate = next((c for c in candidates if c.model_id == manual_model_id), None)
        if chosen_candidate is None:
            raise AppError(f"Model {manual_model_id} not found or not active/priced")
        routing_strategy_used = "manual"
        routing_reason = f"User manually selected '{chosen_candidate.model_name}'."
        candidates_considered_dicts = [{
            "model_id": chosen_candidate.model_id,
            "provider_name": chosen_candidate.provider_name,
            "model_name": chosen_candidate.model_name,
            "estimated_quality": chosen_candidate.estimated_quality,
            "estimated_cost_usd": str(estimate_cost(
                complexity.input_tokens_estimated,
                expected_output_tokens,
                chosen_candidate.pricing,
            ).total_cost_usd),
            "eligible": True,
            "ineligible_reason": None,
        }]
        fallback_triggered = False
    else:
        router = ModelRouter(strategy=routing_strategy)
        constraints = RoutingConstraints(
            min_quality=min_quality,
            remaining_budget_usd=remaining_budget_usd,
        )
        decision = router.route(
            candidates,
            input_tokens=complexity.input_tokens_estimated,
            output_tokens=expected_output_tokens,
            constraints=constraints,
        )
        chosen_candidate = decision.chosen
        routing_strategy_used = decision.routing_strategy
        routing_reason = decision.chosen_reason
        candidates_considered_dicts = [c.as_dict() for c in decision.candidates_considered]
        fallback_triggered = decision.fallback_triggered

    if chosen_candidate is None:
        raise AppError("Routing did not return a model")

    est_breakdown = estimate_cost(
        complexity.input_tokens_estimated,
        expected_output_tokens,
        chosen_candidate.pricing,
    )

    adapter = get_adapter(
        chosen_candidate.provider_name,
        chosen_candidate.model_name,
        chosen_candidate.context_limit,
    )
    provider_response = adapter.send_request(
        prompt,
        RequestParams(max_output_tokens=expected_output_tokens),
    )

    act_breakdown = actual_cost(
        provider_response.input_tokens,
        provider_response.output_tokens,
        chosen_candidate.pricing,
    )
    quality = RubricEvaluator().evaluate(prompt, provider_response, expected_output_tokens)

    request_row = orm.RequestLog(
        user_id=user_id,
        mode=mode,
        prompt_text=prompt,
        estimated_complexity=complexity.complexity,
        model_id=uuid.UUID(chosen_candidate.model_id),
        status="success",
    )
    db.add(request_row)
    db.flush()

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
        routing_strategy=routing_strategy_used,
        candidates_considered=candidates_considered_dicts,
        chosen_model_id=uuid.UUID(chosen_candidate.model_id),
        chosen_reason=routing_reason,
        fallback_triggered=fallback_triggered,
    ))

    db.commit()
    db.refresh(request_row)
    return request_row
