"""
Pricing repository - the DB-backed half of the pricing registry
(docs/01-requirements.md section 5, "Pricing must NOT be blindly
hard-coded into the application").

This module talks to PostgreSQL through SQLAlchemy and therefore is
NOT exercised by the automated test suite in this sandbox (no live
Postgres instance is running here - see backend/README.md for how to
set one up). Its logic is intentionally thin and delegates all actual
cost arithmetic to app/services/cost_engine.py, which IS fully unit
tested, to keep the untested surface area as small as possible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.orm import PricingHistory
from app.services.cost_engine import PricingSnapshot


class PricingNotFoundError(AppError):
    status_code = 404
    default_message = "No current pricing found for this model."


def get_current_pricing(db: Session, model_id) -> PricingSnapshot:
    """Fetch the currently-effective price for a model (effective_to
    IS NULL = still current, per docs/03-database.md)."""
    row = db.execute(
        select(PricingHistory)
        .where(PricingHistory.model_id == model_id)
        .where(PricingHistory.effective_to.is_(None))
        .order_by(PricingHistory.effective_from.desc())
    ).scalar_one_or_none()

    if row is None:
        raise PricingNotFoundError(f"No current pricing for model_id={model_id}")

    return PricingSnapshot(
        model_id=str(model_id),
        input_price_per_1k=Decimal(str(row.input_price_per_1k)),
        output_price_per_1k=Decimal(str(row.output_price_per_1k)),
    )


def get_pricing_at(db: Session, model_id, at_time: datetime) -> PricingSnapshot:
    """Fetch whatever price was effective at a specific point in time -
    used to recompute/audit historical costs even after prices have
    since changed (NFR4: transparency/auditability)."""
    row = db.execute(
        select(PricingHistory)
        .where(PricingHistory.model_id == model_id)
        .where(PricingHistory.effective_from <= at_time)
        .where((PricingHistory.effective_to.is_(None)) | (PricingHistory.effective_to > at_time))
        .order_by(PricingHistory.effective_from.desc())
    ).scalar_one_or_none()

    if row is None:
        raise PricingNotFoundError(f"No pricing for model_id={model_id} effective at {at_time}")

    return PricingSnapshot(
        model_id=str(model_id),
        input_price_per_1k=Decimal(str(row.input_price_per_1k)),
        output_price_per_1k=Decimal(str(row.output_price_per_1k)),
    )


def update_pricing(db: Session, model_id, new_input_price_per_1k: Decimal, new_output_price_per_1k: Decimal) -> PricingHistory:
    """Update a model's price without losing history: closes out the
    current row (sets effective_to = now) and inserts a new one. Never
    overwrites a pricing_history row in place - see docs/03-database.md
    design principle: 'pricing_history is append-only'."""
    now = datetime.now(timezone.utc)

    current = db.execute(
        select(PricingHistory)
        .where(PricingHistory.model_id == model_id)
        .where(PricingHistory.effective_to.is_(None))
    ).scalar_one_or_none()

    if current is not None:
        current.effective_to = now

    new_row = PricingHistory(
        model_id=model_id,
        input_price_per_1k=new_input_price_per_1k,
        output_price_per_1k=new_output_price_per_1k,
        effective_from=now,
        effective_to=None,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row
