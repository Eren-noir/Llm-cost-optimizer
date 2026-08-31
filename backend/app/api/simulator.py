from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import orm
from app.schemas.simulator import ModelProjectionOut, SimulationRequest, SimulationResponse
from app.services.cost_simulator import project_model_cost
from app.services.pricing_repository import PricingNotFoundError, get_current_pricing

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


@router.post("/monthly", response_model=SimulationResponse)
def simulate_monthly(payload: SimulationRequest, db: Session = Depends(get_db)):
    rows = db.execute(
        select(orm.LLMModel, orm.Provider)
        .join(orm.Provider, orm.LLMModel.provider_id == orm.Provider.id)
        .where(orm.LLMModel.status == "active")
        .where(orm.Provider.status == "active")
    ).all()

    projections = []
    for model, provider in rows:
        try:
            pricing = get_current_pricing(db, model.id)
        except PricingNotFoundError:
            continue
        projection = project_model_cost(
            str(model.id), model.model_name, provider.name,
            payload.requests_per_month,
            payload.input_tokens_per_request,
            payload.output_tokens_per_request,
            pricing.input_price_per_1k,
            pricing.output_price_per_1k,
        )
        projections.append(ModelProjectionOut(
            model_id=projection.model_id,
            provider_name=projection.provider_name,
            model_name=projection.model_name,
            monthly_cost_usd=str(projection.monthly_cost_usd),
            monthly_requests=projection.monthly_requests,
            estimated_quality=model.estimated_quality,
        ))

    eligible = [p for p in projections if p.estimated_quality >= payload.min_quality]
    cheapest = min(eligible, key=lambda p: p.monthly_cost_usd).model_id if eligible else None

    return SimulationResponse(
        assumptions={
            "requests_per_month": payload.requests_per_month,
            "input_tokens_per_request": payload.input_tokens_per_request,
            "output_tokens_per_request": payload.output_tokens_per_request,
            "min_quality": payload.min_quality,
        },
        projections=projections,
        cheapest_eligible_model_id=cheapest,
    )
