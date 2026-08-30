"""
SQLAlchemy ORM models - mirror the schema defined in
docs/03-database.md and backend/migrations/001_initial_schema.sql.
Keep these two in sync; the SQL migration is the source of truth for
the actual database, this file is how the app talks to it.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    budget_settings: Mapped["BudgetSettings"] = relationship(back_populates="user", uselist=False)
    requests: Mapped[list["RequestLog"]] = relationship(back_populates="user")


class BudgetSettings(Base):
    __tablename__ = "budget_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    monthly_budget_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    min_quality_threshold: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="budget_settings")

    __table_args__ = (
        CheckConstraint("min_quality_threshold BETWEEN 0 AND 100", name="ck_budget_quality_range"),
    )


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    models: Mapped[list["LLMModel"]] = relationship(back_populates="provider")


class LLMModel(Base):
    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    context_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    estimated_quality: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    provider: Mapped["Provider"] = relationship(back_populates="models")
    pricing_history: Mapped[list["PricingHistory"]] = relationship(back_populates="model")

    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_provider_model"),
        CheckConstraint("estimated_quality BETWEEN 0 AND 100", name="ck_model_quality_range"),
    )


class PricingHistory(Base):
    __tablename__ = "pricing_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    input_price_per_1k: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    output_price_per_1k: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(server_default=func.now())
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)

    model: Mapped["LLMModel"] = relationship(back_populates="pricing_history")


class RequestLog(Base):
    """Named RequestLog (not Request) to avoid clashing with fastapi.Request."""

    __tablename__ = "requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_complexity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="requests")
    response: Mapped["ResponseLog"] = relationship(back_populates="request", uselist=False)
    usage_metrics: Mapped["UsageMetrics"] = relationship(back_populates="request", uselist=False)
    quality_evaluation: Mapped["QualityEvaluation"] = relationship(back_populates="request", uselist=False)
    optimization_result: Mapped["OptimizationResult"] = relationship(back_populates="request", uselist=False)

    __table_args__ = (
        CheckConstraint("mode IN ('manual','comparison','auto')", name="ck_request_mode"),
        CheckConstraint(
            "estimated_complexity IN ('simple','medium','complex') OR estimated_complexity IS NULL",
            name="ck_request_complexity",
        ),
        CheckConstraint("status IN ('success','failed','fallback_used')", name="ck_request_status"),
    )


class ResponseLog(Base):
    __tablename__ = "responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    finish_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    request: Mapped["RequestLog"] = relationship(back_populates="response")


class UsageMetrics(Base):
    __tablename__ = "usage_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False)
    input_tokens_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens_actual: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens_actual: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    actual_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)

    request: Mapped["RequestLog"] = relationship(back_populates="usage_metrics")


class QualityEvaluation(Base):
    __tablename__ = "quality_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False)
    quality_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    evaluation_method: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    request: Mapped["RequestLog"] = relationship(back_populates="quality_evaluation")

    __table_args__ = (
        CheckConstraint("quality_score BETWEEN 0 AND 100", name="ck_quality_score_range"),
        CheckConstraint("evaluation_method IN ('rubric','llm_judge','human')", name="ck_evaluation_method"),
    )


class OptimizationResult(Base):
    __tablename__ = "optimization_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False)
    routing_strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    candidates_considered: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chosen_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False)
    chosen_reason: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    request: Mapped["RequestLog"] = relationship(back_populates="optimization_result")
