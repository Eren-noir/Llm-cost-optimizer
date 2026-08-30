"""
Pydantic schemas for API requests/responses.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class SubmitTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    mode: Literal["manual", "comparison", "auto"] = "auto"
    min_quality: int = Field(default=0, ge=0, le=100)
    remaining_budget_usd: Decimal | None = None
    manual_model_id: str | None = None
    model_ids: list[str] | None = None  # used by comparison mode


class CandidateConsideredOut(BaseModel):
    model_id: str
    provider_name: str
    model_name: str
    estimated_quality: int
    estimated_cost_usd: str | None = None
    eligible: bool
    ineligible_reason: str | None = None


class TaskResultOut(BaseModel):
    request_id: str
    mode: str
    status: str
    estimated_complexity: str | None
    model_id: str
    provider_name: str
    model_name: str
    response_text: str
    finish_reason: str | None
    input_tokens_actual: int
    output_tokens_actual: int
    latency_ms: int
    estimated_cost_usd: str
    actual_cost_usd: str
    quality_score: int
    quality_method: str
    quality_notes: str
    routing_strategy: str
    routing_reason: str
    fallback_triggered: bool
    candidates_considered: list[CandidateConsideredOut]


class ModelOut(BaseModel):
    model_id: str
    provider_name: str
    model_name: str
    estimated_quality: int
    context_limit: int
    status: str
    input_price_per_1k: str | None
    output_price_per_1k: str | None


class DashboardSummaryOut(BaseModel):
    total_requests: int
    total_cost_usd: str
    total_tokens: int
    average_quality: float | None
    average_latency_ms: float | None
    requests_by_model: dict[str, int]
    cost_by_model: dict[str, str]
