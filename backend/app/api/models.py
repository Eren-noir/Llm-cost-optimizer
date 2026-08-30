"""
API endpoint exposing the model registry - used by the frontend to
populate model-selection dropdowns for manual/comparison modes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import orm
from app.schemas.api import ModelOut
from app.services.pricing_repository import PricingNotFoundError, get_current_pricing

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
def list_models(db: Session = Depends(get_db)):
    rows = db.execute(
        select(orm.LLMModel, orm.Provider).join(orm.Provider, orm.LLMModel.provider_id == orm.Provider.id)
    ).all()

    result = []
    for model, provider in rows:
        try:
            pricing = get_current_pricing(db, model.id)
            input_price = str(pricing.input_price_per_1k)
            output_price = str(pricing.output_price_per_1k)
        except PricingNotFoundError:
            input_price = None
            output_price = None

        result.append(ModelOut(
            model_id=str(model.id),
            provider_name=provider.name,
            model_name=model.model_name,
            estimated_quality=model.estimated_quality,
            context_limit=model.context_limit,
            status=model.status,
            input_price_per_1k=input_price,
            output_price_per_1k=output_price,
        ))
    return result
