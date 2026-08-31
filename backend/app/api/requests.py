"""API endpoints for task submission and controlled model comparison."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.models import orm
from app.schemas.api import CandidateConsideredOut, SubmitTaskRequest, TaskResultOut
from app.services.pipeline import run_request_pipeline

router = APIRouter(prefix="/api/requests", tags=["requests"])


def _get_or_create_demo_user(db: Session) -> uuid.UUID:
    existing = db.execute(
        select(orm.User).where(orm.User.email == "demo@local")
    ).scalar_one_or_none()
    if existing:
        return existing.id
    user = orm.User(email="demo@local", password_hash="not-used-in-demo-mode")
    db.add(user)
    db.commit()
    return user.id


def _to_result_out(request_row: orm.RequestLog, db: Session) -> TaskResultOut:
    response = db.query(orm.ResponseLog).filter_by(request_id=request_row.id).one()
    usage = db.query(orm.UsageMetrics).filter_by(request_id=request_row.id).one()
    quality = db.query(orm.QualityEvaluation).filter_by(request_id=request_row.id).one()
    opt_result = db.query(orm.OptimizationResult).filter_by(request_id=request_row.id).one()
    model = db.query(orm.LLMModel).filter_by(id=request_row.model_id).one()
    provider = db.query(orm.Provider).filter_by(id=model.provider_id).one()

    return TaskResultOut(
        request_id=str(request_row.id),
        mode=request_row.mode,
        status=request_row.status,
        estimated_complexity=request_row.estimated_complexity,
        model_id=str(model.id),
        provider_name=provider.name,
        model_name=model.model_name,
        response_text=response.response_text,
        finish_reason=response.finish_reason,
        input_tokens_actual=usage.input_tokens_actual,
        output_tokens_actual=usage.output_tokens_actual,
        latency_ms=usage.latency_ms,
        estimated_cost_usd=str(usage.estimated_cost_usd),
        actual_cost_usd=str(usage.actual_cost_usd),
        quality_score=quality.quality_score,
        quality_method=quality.evaluation_method,
        quality_notes=quality.evaluator_notes or "",
        routing_strategy=opt_result.routing_strategy,
        routing_reason=opt_result.chosen_reason,
        fallback_triggered=opt_result.fallback_triggered,
        candidates_considered=[CandidateConsideredOut(**c) for c in opt_result.candidates_considered],
    )


@router.post("", response_model=TaskResultOut)
def submit_task(payload: SubmitTaskRequest, db: Session = Depends(get_db)):
    if payload.mode == "comparison":
        raise AppError("Use POST /api/requests/compare for comparison mode.")

    user_id = _get_or_create_demo_user(db)
    request_row = run_request_pipeline(
        db,
        user_id=user_id,
        prompt=payload.prompt,
        mode=payload.mode,
        min_quality=payload.min_quality,
        remaining_budget_usd=payload.remaining_budget_usd,
        manual_model_id=payload.manual_model_id,
        routing_strategy=payload.routing_strategy,
    )
    return _to_result_out(request_row, db)


@router.post("/compare", response_model=list[TaskResultOut])
def compare_models(payload: SubmitTaskRequest, db: Session = Depends(get_db)):
    """Send the same prompt to selected models for side-by-side evaluation.

    The comparison mode is deliberately manual: it measures each model
    independently so benchmark analysis can replay routing strategies without
    making additional model calls.
    """
    if not payload.model_ids or len(payload.model_ids) < 2:
        raise AppError("model_ids must contain at least two model IDs for comparison mode.")

    user_id = _get_or_create_demo_user(db)
    results = []
    for model_id in payload.model_ids:
        request_row = run_request_pipeline(
            db,
            user_id=user_id,
            prompt=payload.prompt,
            mode="comparison",
            min_quality=payload.min_quality,
            manual_model_id=model_id,
        )
        results.append(_to_result_out(request_row, db))
    return results
