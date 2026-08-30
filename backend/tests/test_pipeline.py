"""
Tests for the request pipeline - the first tests in this suite that
exercise a REAL database (in-memory SQLite, see tests/conftest.py)
rather than pure in-memory objects. This proves the full
Analyzer -> Router -> Adapter -> Cost Engine -> Quality Evaluator ->
Persistence chain actually works end to end, not just its individual
pieces in isolation.
"""
import uuid

import pytest

from app.core.errors import NoEligibleModelError
from app.models import orm
from app.services.pipeline import run_request_pipeline


def _seed_registry(db_session, models: list[dict]):
    """models: list of dicts with keys provider, model_name, quality,
    input_price, output_price, context_limit."""
    providers = {}
    for m in models:
        if m["provider"] not in providers:
            p = orm.Provider(name=m["provider"], status="active")
            db_session.add(p)
            db_session.flush()
            providers[m["provider"]] = p

        model_row = orm.LLMModel(
            provider_id=providers[m["provider"]].id,
            model_name=m["model_name"],
            context_limit=m.get("context_limit", 32000),
            capabilities={},
            estimated_quality=m["quality"],
            status="active",
        )
        db_session.add(model_row)
        db_session.flush()

        pricing = orm.PricingHistory(
            model_id=model_row.id,
            input_price_per_1k=m["input_price"],
            output_price_per_1k=m["output_price"],
        )
        db_session.add(pricing)

    db_session.commit()


def _seed_user(db_session) -> uuid.UUID:
    user = orm.User(email="student@example.com", password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture
def seeded_db(db_session):
    """A real SQLite-backed DB seeded with a mock-provider model
    registry mirroring the worked example in docs/01-requirements.md §4."""
    _seed_registry(db_session, [
        {"provider": "mock", "model_name": "mock-cheap", "quality": 65, "input_price": "0.0067", "output_price": "0.0067"},
        {"provider": "mock", "model_name": "mock-mid", "quality": 84, "input_price": "0.0333", "output_price": "0.0333"},
        {"provider": "mock", "model_name": "mock-premium", "quality": 93, "input_price": "0.1333", "output_price": "0.1333"},
    ])
    user_id = _seed_user(db_session)
    return db_session, user_id


def test_pipeline_auto_mode_picks_cheapest_when_no_quality_floor(seeded_db):
    db, user_id = seeded_db
    request_row = run_request_pipeline(db, user_id, "What is the capital of Kenya?", mode="auto", min_quality=0)

    assert request_row.status == "success"
    assert request_row.mode == "auto"

    # Fetch and confirm every related row was actually persisted
    response = db.query(orm.ResponseLog).filter_by(request_id=request_row.id).one()
    usage = db.query(orm.UsageMetrics).filter_by(request_id=request_row.id).one()
    quality = db.query(orm.QualityEvaluation).filter_by(request_id=request_row.id).one()
    opt_result = db.query(orm.OptimizationResult).filter_by(request_id=request_row.id).one()

    assert response.response_text  # mock adapter always returns non-empty text
    assert usage.actual_cost_usd >= 0
    assert 0 <= quality.quality_score <= 100
    assert opt_result.routing_strategy == "baseline"

    chosen_model = db.query(orm.LLMModel).filter_by(id=request_row.model_id).one()
    assert chosen_model.model_name == "mock-cheap"  # cheapest, no quality floor


def test_pipeline_auto_mode_respects_quality_floor(seeded_db):
    db, user_id = seeded_db
    request_row = run_request_pipeline(db, user_id, "Explain quantum entanglement.", mode="auto", min_quality=90)
    chosen_model = db.query(orm.LLMModel).filter_by(id=request_row.model_id).one()
    assert chosen_model.model_name == "mock-premium"  # only one clears quality=90


def test_pipeline_raises_when_no_model_meets_quality(seeded_db):
    db, user_id = seeded_db
    with pytest.raises(NoEligibleModelError):
        run_request_pipeline(db, user_id, "Impossible task.", mode="auto", min_quality=99)


def test_pipeline_manual_mode_uses_specified_model(seeded_db):
    db, user_id = seeded_db
    mid_model = db.query(orm.LLMModel).filter_by(model_name="mock-mid").one()

    request_row = run_request_pipeline(
        db, user_id, "Translate this to French.", mode="manual", manual_model_id=str(mid_model.id),
    )
    assert request_row.model_id == mid_model.id

    opt_result = db.query(orm.OptimizationResult).filter_by(request_id=request_row.id).one()
    assert opt_result.routing_strategy == "manual"


def test_pipeline_stores_estimated_and_actual_cost_separately(seeded_db):
    db, user_id = seeded_db
    request_row = run_request_pipeline(db, user_id, "Short question?", mode="auto")
    usage = db.query(orm.UsageMetrics).filter_by(request_id=request_row.id).one()
    # Both should be present and be plausible (not asserting equality -
    # the mock adapter's actual token count won't exactly match the
    # heuristic estimate, which is realistic and exactly what
    # estimated_cost_usd vs actual_cost_usd is meant to capture).
    assert usage.estimated_cost_usd is not None
    assert usage.actual_cost_usd is not None


def test_pipeline_persists_candidates_considered_for_auditability(seeded_db):
    db, user_id = seeded_db
    request_row = run_request_pipeline(db, user_id, "Anything.", mode="auto", min_quality=80)
    opt_result = db.query(orm.OptimizationResult).filter_by(request_id=request_row.id).one()
    assert len(opt_result.candidates_considered) == 3  # all 3 models were evaluated
    ineligible = [c for c in opt_result.candidates_considered if not c["eligible"]]
    assert len(ineligible) == 1  # only mock-cheap (quality 65) fails an 80 floor
    assert ineligible[0]["ineligible_reason"] is not None
