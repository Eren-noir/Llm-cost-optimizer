"""
API-level tests: exercises the actual FastAPI app over HTTP (via
TestClient), with app.core.database.get_db overridden to point at an
in-memory SQLite DB instead of the configured PostgreSQL URL. This
proves the full stack - routing, request/response schemas, DB
persistence, dashboard aggregation - works together, not just each
layer in isolation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import orm  # noqa: F401
from tests.test_pipeline import _seed_registry, _seed_user


@pytest.fixture
def client():
    # StaticPool is required for an in-memory SQLite DB to be shared
    # across the multiple connections FastAPI's request-scoped sessions
    # open - without it, each new connection sees its own separate,
    # empty in-memory database (caught while writing this fixture: the
    # seed data and the tables it created were invisible to the app's
    # own DB session, raising "no such table: users").
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed a small registry directly through a session, same helper the
    # pipeline tests use, so behavior stays consistent across test files.
    with Session(engine) as session:
        _seed_registry(session, [
            {"provider": "mock", "model_name": "mock-cheap", "quality": 65, "input_price": "0.0067", "output_price": "0.0067"},
            {"provider": "mock", "model_name": "mock-mid", "quality": 84, "input_price": "0.0333", "output_price": "0.0333"},
            {"provider": "mock", "model_name": "mock-premium", "quality": 93, "input_price": "0.1333", "output_price": "0.1333"},
        ])

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


def test_list_models_endpoint(client):
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    names = {m["model_name"] for m in data}
    assert names == {"mock-cheap", "mock-mid", "mock-premium"}
    assert all(m["input_price_per_1k"] is not None for m in data)


def test_submit_task_auto_mode(client):
    response = client.post("/api/requests", json={"prompt": "What is the capital of Kenya?", "mode": "auto", "min_quality": 0})
    assert response.status_code == 200
    data = response.json()
    assert data["model_name"] == "mock-cheap"  # cheapest with no quality floor
    assert data["status"] == "success"
    assert data["response_text"]
    assert float(data["actual_cost_usd"]) >= 0
    assert 0 <= data["quality_score"] <= 100


def test_submit_task_auto_mode_with_quality_floor(client):
    response = client.post("/api/requests", json={"prompt": "Explain quantum computing.", "mode": "auto", "min_quality": 90})
    assert response.status_code == 200
    data = response.json()
    assert data["model_name"] == "mock-premium"


def test_submit_task_no_eligible_model_returns_422(client):
    response = client.post("/api/requests", json={"prompt": "Impossible.", "mode": "auto", "min_quality": 99})
    assert response.status_code == 422
    assert response.json()["error"] == "NoEligibleModelError"


def test_submit_task_manual_mode(client):
    models_response = client.get("/api/models")
    mid_model_id = next(m["model_id"] for m in models_response.json() if m["model_name"] == "mock-mid")

    response = client.post("/api/requests", json={"prompt": "Translate hello to French.", "mode": "manual", "manual_model_id": mid_model_id})
    assert response.status_code == 200
    assert response.json()["model_id"] == mid_model_id


def test_compare_endpoint(client):
    models_response = client.get("/api/models").json()
    model_ids = [m["model_id"] for m in models_response]

    response = client.post("/api/requests/compare", json={"prompt": "Say hi.", "mode": "comparison", "model_ids": model_ids})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3
    assert {r["model_name"] for r in results} == {"mock-cheap", "mock-mid", "mock-premium"}


def test_dashboard_summary_empty(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 0


def test_dashboard_summary_after_requests(client):
    client.post("/api/requests", json={"prompt": "Q1", "mode": "auto"})
    client.post("/api/requests", json={"prompt": "Q2", "mode": "auto", "min_quality": 90})

    response = client.get("/api/dashboard/summary")
    data = response.json()
    assert data["total_requests"] == 2
    assert float(data["total_cost_usd"]) > 0
    assert data["average_quality"] is not None
    assert sum(data["requests_by_model"].values()) == 2
