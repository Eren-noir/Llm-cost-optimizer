"""
Smoke tests for Phase 4: confirms the FastAPI app boots and the
liveness endpoint responds correctly. The DB-dependent endpoint is
exercised separately once a real database is available (see README
in this directory for how to run against PostgreSQL or SQLite).
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
