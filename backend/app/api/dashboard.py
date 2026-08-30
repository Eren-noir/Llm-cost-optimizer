"""
API endpoint for dashboard summary metrics - docs/01-requirements.md
§13 (Total Requests, Total Cost, Average Quality, per-model usage, etc).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import orm
from app.schemas.api import DashboardSummaryOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def dashboard_summary(db: Session = Depends(get_db)):
    total_requests = db.execute(select(func.count(orm.RequestLog.id))).scalar_one()

    if total_requests == 0:
        return DashboardSummaryOut(
            total_requests=0,
            total_cost_usd="0.000000",
            total_tokens=0,
            average_quality=None,
            average_latency_ms=None,
            requests_by_model={},
            cost_by_model={},
        )

    totals = db.execute(
        select(
            func.sum(orm.UsageMetrics.actual_cost_usd),
            func.sum(orm.UsageMetrics.input_tokens_actual + orm.UsageMetrics.output_tokens_actual),
            func.avg(orm.UsageMetrics.latency_ms),
        )
    ).one()
    total_cost, total_tokens, avg_latency = totals

    avg_quality = db.execute(select(func.avg(orm.QualityEvaluation.quality_score))).scalar_one()

    per_model_rows = db.execute(
        select(orm.LLMModel.model_name, func.count(orm.RequestLog.id), func.sum(orm.UsageMetrics.actual_cost_usd))
        .join(orm.RequestLog, orm.RequestLog.model_id == orm.LLMModel.id)
        .join(orm.UsageMetrics, orm.UsageMetrics.request_id == orm.RequestLog.id)
        .group_by(orm.LLMModel.model_name)
    ).all()

    requests_by_model = {name: count for name, count, _ in per_model_rows}
    cost_by_model = {name: str(cost) for name, _, cost in per_model_rows}

    return DashboardSummaryOut(
        total_requests=total_requests,
        total_cost_usd=str(total_cost or 0),
        total_tokens=int(total_tokens or 0),
        average_quality=float(avg_quality) if avg_quality is not None else None,
        average_latency_ms=float(avg_latency) if avg_latency is not None else None,
        requests_by_model=requests_by_model,
        cost_by_model=cost_by_model,
    )
