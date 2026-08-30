"""
Shared pytest fixtures.

`db_session` gives tests a real, working database (in-memory SQLite)
to exercise actual persistence logic - not just mocked calls. This is
possible because app/models/orm.py uses portable SQLAlchemy types
(Uuid, JSON-with-postgresql-variant) rather than Postgres-only ones -
see the comment in orm.py for why. Production still runs on
PostgreSQL (docs/03-database.md); this fixture exists purely to let
CI/local test runs verify real DB behavior without requiring a live
Postgres instance.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import orm  # noqa: F401 - ensures all models are registered


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
