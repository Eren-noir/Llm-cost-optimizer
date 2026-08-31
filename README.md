# Intelligent Multi-LLM Cost Optimization and Model Routing Platform

A university Computer Science project that dynamically routes LLM requests across multiple providers (OpenAI, Anthropic Claude, and Google Gemini) to reduce operating cost while satisfying a configurable quality requirement.

## Project objective

The project investigates whether intelligent, per-task model selection can reduce LLM operating cost without an unacceptable loss in response quality.

**Optimization objective:** minimize estimated/actual LLM cost subject to a minimum quality threshold.

## Current capabilities

- Multi-provider adapter architecture for OpenAI, Anthropic, and Gemini
- Token usage tracking and deterministic cost calculation
- Historical pricing representation
- Task-complexity estimation
- Quality-constrained model routing
- Transparent cheapest-eligible baseline strategy
- Weighted cost/quality/latency routing strategy
- Bounded fallback decision generation
- Rubric-based quality evaluation and optional LLM judging
- End-to-end request pipeline: analysis → routing → provider → cost → evaluation → persistence
- Dashboard API and React frontend
- Routing-strategy controls in the dashboard
- Monthly what-if cost simulator
- Controlled benchmark task dataset
- Reproducible benchmark collection and offline strategy replay tooling
- CI for backend tests and frontend builds

## Architecture

```text
User
  ↓
React Dashboard
  ↓
FastAPI
  ↓
Task Analyzer
  ↓
Model Router ← Pricing / Model Registry / Historical Latency
  ↓
Provider Adapter
  ├── OpenAI
  ├── Anthropic
  └── Gemini
  ↓
LLM Response
  ↓
Cost Engine + Quality Evaluation
  ↓
PostgreSQL
  ↓
Dashboard / Experiments
```

## Repository structure

```text
backend/       FastAPI application, routing, providers, cost engine and evaluation
frontend/      React/Vite dashboard
benchmarks/    Controlled benchmark tasks and ignored generated results
experiments/   Benchmark collection and offline analysis tools
docs/          Requirements, architecture, database and research documentation
```

## Technology stack

- Backend: Python, FastAPI, SQLAlchemy
- Frontend: React, Vite
- Database: PostgreSQL
- APIs: official OpenAI, Anthropic and Google Gemini APIs
- Testing: pytest
- Version control: Git/GitHub

## Local development

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` from `backend/.env.example`, apply `backend/migrations/001_initial_schema.sql` to PostgreSQL, populate the model/pricing registry, then run:

```bash
uvicorn app.main:app --reload
```

The API documentation is available at `/docs` when the backend is running.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` if the backend is not running at `http://localhost:8000`.

## Environment and secrets

Copy `backend/.env.example` to a local `.env` and provide credentials there. **Never commit real API keys or secrets to GitHub.**

## Research methodology

The benchmark compares a transparent cheapest-eligible baseline against weighted routing across simple, medium, and complex tasks. Each task is first collected independently on every active model. Routing strategies are then replayed offline from pre-request signals, while the selected model's observed cost, quality and latency are used for evaluation. This prevents extra provider calls from being required just to compare strategies.

Run the benchmark with:

```bash
python experiments/run_benchmark.py --base-url http://localhost:8000
python experiments/analyze_results.py benchmarks/results/raw_results.json
```

Benchmark execution makes real provider calls and may incur API charges. Results are intentionally not fabricated or committed automatically.

## Project status

The software foundation is implemented through the routing, evaluation, frontend, simulator and benchmark-tooling stages. The remaining research work is empirical: populate and verify the current model/pricing registry, run controlled provider experiments, repeat runs where practical, analyze cost/quality/latency trade-offs, and document the actual findings.

## License

MIT (see `LICENSE`).
