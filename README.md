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
- Baseline cheapest-eligible routing strategy
- Weighted cost/quality routing strategy
- Bounded fallback decisions
- Rubric-based quality evaluation and optional LLM judging
- Request pipeline connecting analysis → routing → provider → cost → evaluation → persistence
- Dashboard API and React frontend
- Monthly what-if cost simulator
- Benchmark task dataset for controlled experiments

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
Model Router ← Pricing / Model Registry
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
benchmarks/    Controlled benchmark tasks
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

The benchmark compares a baseline strategy against intelligent routing across simple, medium, and complex tasks. Evaluation should report cost, token usage, latency, response quality, and savings. Results must be generated from actual controlled runs; this repository does not contain fabricated experimental results.

## Project status

The backend currently contains the core routing, provider, cost, evaluation, and API pipeline. The React dashboard and monthly cost simulator are now being developed. Benchmark execution, empirical optimization, and final validation remain to be completed.

## License

MIT (see `LICENSE`).
