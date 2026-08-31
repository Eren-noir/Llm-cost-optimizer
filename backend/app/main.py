"""
FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.models import router as models_router
from app.api.requests import router as requests_router
from app.api.simulator import router as simulator_router
from app.core.errors import register_error_handlers

app = FastAPI(
    title="LLM Cost Optimization Platform",
    description="Intelligent multi-provider LLM cost optimization and routing API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(requests_router)
app.include_router(models_router)
app.include_router(dashboard_router)
app.include_router(simulator_router)


@app.get("/")
def root():
    return {"message": "LLM Cost Optimization Platform API", "docs": "/docs"}
