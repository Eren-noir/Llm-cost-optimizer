"""
Health check endpoint - used to verify the app is running and can reach
the database. This is the first thing tested at the end of Phase 4.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """Basic liveness check - does not touch the database."""
    return {"status": "ok"}


@router.get("/health/db")
def health_check_db(db: Session = Depends(get_db)):
    """Readiness check - confirms the database connection actually works."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
