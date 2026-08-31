from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    requests_per_month: int = Field(..., ge=1, le=100_000_000)
    input_tokens_per_request: int = Field(..., ge=0, le=10_000_000)
    output_tokens_per_request: int = Field(..., ge=0, le=10_000_000)
    min_quality: int = Field(default=0, ge=0, le=100)


class ModelProjectionOut(BaseModel):
    model_id: str
    provider_name: str
    model_name: str
    monthly_cost_usd: str
    monthly_requests: int
    estimated_quality: int


class SimulationResponse(BaseModel):
    assumptions: dict[str, int]
    projections: list[ModelProjectionOut]
    cheapest_eligible_model_id: str | None
