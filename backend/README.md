# Backend

FastAPI backend for the LLM Cost Optimization Platform.

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill in real values - never commit .env
```

## Database

Requires PostgreSQL 14+. Create the database, then apply the schema:

```bash
createdb llm_cost_optimizer
psql llm_cost_optimizer < migrations/001_initial_schema.sql
```

(Alembic will manage migrations going forward as the schema evolves past
this initial version - `alembic upgrade head` once `alembic/` is wired up
in a later phase.)

## Run

```bash
uvicorn app.main:app --reload
```

Then visit:
- http://127.0.0.1:8000/ - basic root response
- http://127.0.0.1:8000/health - liveness check
- http://127.0.0.1:8000/health/db - confirms DB connectivity
- http://127.0.0.1:8000/docs - interactive OpenAPI docs

## Test

```bash
pytest tests/ -v
```

## Project Layout

```
app/
  core/       config, database session, shared error types
  models/     SQLAlchemy ORM models (mirrors docs/03-database.md)
  api/        FastAPI routers
  schemas/    Pydantic request/response schemas (added in later phases)
  main.py     application entrypoint
migrations/   raw SQL migrations (001 = initial schema)
tests/        pytest test suite
```
