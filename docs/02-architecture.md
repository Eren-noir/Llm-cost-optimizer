# Phase 2 — System Architecture

## 1. Architectural Style

Layered / modular monolith for the MVP (not microservices — unnecessary complexity for an academic-scale system). Internally organized into clearly separated modules so it *could* be split into services later, but ships as one FastAPI application talking to one PostgreSQL database.

Rationale: microservices add operational overhead (service discovery, network calls, distributed tracing) with no benefit at this scale, and would eat into project time better spent on the routing/cost/quality research components. A modular monolith with strict internal boundaries gives the same separation-of-concerns benefit without the cost.

## 2. High-Level Component Diagram

```
                        ┌─────────────────────────┐
                        │        Frontend          │
                        │   React Dashboard / UI    │
                        └────────────┬─────────────┘
                                     │ HTTPS / REST (JSON)
                        ┌────────────▼─────────────┐
                        │      FastAPI Backend      │
                        │  ┌──────────────────────┐ │
                        │  │   API Layer (routers) │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │   Task Analyzer        │ │
                        │  │ (complexity + token     │ │
                        │  │  estimation)            │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │   Model Router          │ │
                        │  │ (selection algorithm)   │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │ Provider Adapter Layer  │ │
                        │  │ ┌────────┬───────────┐ │ │
                        │  │ │ OpenAI │ Anthropic │…│ │
                        │  │ └────────┴───────────┘ │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │  Cost Engine            │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │  Quality Evaluator      │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │  Budget Manager         │ │
                        │  └──────────┬───────────┘ │
                        │  ┌──────────▼───────────┐ │
                        │  │  Metrics / Persistence  │ │
                        │  └──────────┬───────────┘ │
                        └─────────────┼─────────────┘
                                      │
                        ┌─────────────▼─────────────┐
                        │       PostgreSQL            │
                        └─────────────────────────────┘

              External:  OpenAI API · Anthropic API · Gemini API
```

## 3. Component Responsibilities

| Component | Responsibility |
|---|---|
| API Layer | HTTP endpoints, request validation, auth, orchestrates the pipeline below |
| Task Analyzer | Classifies task difficulty (simple/medium/complex), estimates input/output tokens before sending |
| Model Router | Given candidate models + constraints (quality floor, budget), selects the model to use |
| Provider Adapters | Translate a common internal request format into each provider's API call; normalize responses back into a common format |
| Cost Engine | Computes estimated cost (pre-call) and actual cost (post-call) from token counts × registry pricing |
| Quality Evaluator | Scores a response 0–100 using rubric and/or LLM-as-judge |
| Budget Manager | Tracks spend against configured budget; triggers fallback when budget/quality constraints can't both be met |
| Metrics/Persistence | Writes requests, responses, usage, quality scores, routing decisions to PostgreSQL; serves aggregated data to the dashboard |

## 4. Data Flow (request lifecycle)

```
1. Frontend submits task + mode (manual/comparison/auto) + optional constraints
2. API layer validates request, loads user's budget/quality settings
3. Task Analyzer estimates complexity + expected tokens
4. Model Router:
     - fetches candidate models from registry (status = active)
     - filters by estimated_quality >= required_quality (if auto mode)
     - filters by (estimated cost <= remaining budget)
     - selects lowest-cost candidate meeting constraints
     - [comparison mode: skips filtering, sends to multiple models]
5. Provider Adapter sends request to chosen provider(s)
6. On response: record actual tokens, actual latency
7. Cost Engine computes actual cost from real token usage
8. Quality Evaluator scores the response
9. Budget Manager updates running spend
10. Metrics layer persists: request, response, usage_metrics,
    quality_evaluation, optimization_result (which model chosen & why)
11. API layer returns response + full cost/quality breakdown to frontend
12. On failure at step 5/6: Model Router selects next-best fallback
    candidate and retries once (bounded), else returns a clear error
```

## 5. Provider Abstraction

A common interface every adapter implements:

```
class LLMProviderAdapter (interface):
    def estimate_tokens(prompt: str) -> TokenEstimate
    def send_request(prompt: str, params: RequestParams) -> ProviderResponse
    def get_model_capabilities() -> ModelCapabilities

ProviderResponse (normalized, regardless of provider):
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    raw_response: dict   # kept for debugging, not relied on elsewhere
    finish_reason: str
```

Concrete adapters: `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`. Each isolates provider-specific SDK calls, auth, and error types behind this interface — nothing outside the adapter layer imports a provider SDK directly. Adding a 4th provider means writing one new adapter class; no changes to router, cost engine, or API layer.

## 6. Routing Architecture

Two-stage design so the algorithm can grow in sophistication without changing its surrounding architecture:

**Stage 1 — Filtering.** Given the task's estimated complexity/tokens and the user's quality floor + remaining budget, filter the model registry down to *eligible* candidates (estimated_quality ≥ threshold, estimated cost ≤ remaining budget, status = active).

**Stage 2 — Selection.** Among eligible candidates, apply the active routing strategy to pick one:
- `baseline`: pick the lowest estimated-cost eligible candidate (transparent, easy to justify — this is the MVP default)
- `weighted_scoring`: score = w1·(1/cost) + w2·quality + w3·(1/latency), pick highest score (weights configurable — later addition)
- `classification_based` / `historical_performance`: pluggable strategies added post-MVP without touching Stage 1

This mirrors the provider-adapter pattern: routing strategies implement a common `RoutingStrategy.select(candidates, task, constraints) -> chosen_model` interface, swappable via config.

## 7. Technology Decisions

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python + FastAPI | Async support (useful for concurrent multi-model comparison mode), automatic OpenAPI docs, strong typing via Pydantic matches the "transparent, auditable" requirement |
| Frontend | React | Matches brief; component-based dashboard with charts is a natural fit |
| Database | PostgreSQL | Relational integrity matters here (foreign keys between requests/usage/quality/pricing_history); JSONB available for flexible fields like raw provider responses |
| ORM | SQLAlchemy + Alembic | Migrations needed since pricing/schema will evolve across phases |
| Charts | Recharts or Chart.js (frontend) | Standard, lightweight, sufficient for dashboard needs |
| Auth | Simple JWT-based auth (single-user or lightweight multi-user) | No need for a heavy auth system at academic scale; NFR1 (no keys on frontend) driven by backend proxying all provider calls |
| Testing | pytest (backend), Jest/RTL (frontend, if time permits) | Standard, aligns with Phase 13 testing plan |
| Dev/versioning | Git + GitHub | Already set up |

## 8. Cross-Cutting Concerns

- **Secrets**: provider API keys read from environment variables only (`.env`, gitignored), never touch the frontend or get logged.
- **Error handling**: each adapter maps provider-specific errors (timeout, rate limit, invalid key, context-length exceeded) to a small set of common internal exception types the router understands, enabling uniform fallback logic.
- **Logging/auditability**: every routing decision logged with its inputs (candidates considered, filters applied, why one was chosen) — satisfies NFR6 and directly supports RQ3/RQ4 analysis later.
- **Bounded retries**: fallback logic retries at most once against a different model before surfacing an error — no infinite loops.

---
*Status: Draft for review — awaiting approval before proceeding to Phase 3 (Database Design).*
