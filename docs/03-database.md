# Phase 3 — Database Design

## 1. Design Principles

- Normalized (3NF) — pricing, models, and providers change independently of requests, so they're separated to avoid update anomalies.
- `pricing_history` is append-only and never overwritten, so cost calculations remain reproducible even after a provider changes prices (NFR4: transparency/auditability).
- Every cost figure stored is traceable back to the token counts and the exact pricing row used — no cost value is ever stored without its inputs.
- Routing decisions are stored separately from requests so the "why this model was chosen" reasoning (NFR6) survives independently of the request/response payloads.

## 2. Entity-Relationship Diagram (textual)

```
users ──1:N──> requests ──1:1──> responses
                  │                  │
                  │                  └──1:1──> quality_evaluations
                  │
                  ├──1:1──> usage_metrics
                  │
                  └──1:1──> optimization_results ──N:1──> models

providers ──1:N──> models ──1:N──> pricing_history
                              │
                              └──1:N──> requests (model actually used)
                              │
                              └──N:N──> optimization_results (candidates_considered)

users ──1:1──> budget_settings
```

## 3. Table Definitions

### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | VARCHAR UNIQUE NOT NULL | |
| password_hash | VARCHAR NOT NULL | |
| created_at | TIMESTAMPTZ DEFAULT now() | |

### `budget_settings`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users.id UNIQUE | one active budget config per user |
| monthly_budget_usd | NUMERIC(10,4) NOT NULL | |
| min_quality_threshold | SMALLINT NOT NULL | 0–100 |
| updated_at | TIMESTAMPTZ DEFAULT now() | |

### `providers`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR UNIQUE NOT NULL | e.g. "openai", "anthropic", "gemini" |
| status | VARCHAR NOT NULL DEFAULT 'active' | active / disabled |

### `models`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| provider_id | UUID FK → providers.id NOT NULL | |
| model_name | VARCHAR NOT NULL | e.g. "gpt-4o-mini" |
| context_limit | INTEGER NOT NULL | tokens |
| capabilities | JSONB | e.g. {"vision": true, "function_calling": true} |
| estimated_quality | SMALLINT NOT NULL | 0–100, baseline benchmark score |
| status | VARCHAR NOT NULL DEFAULT 'active' | active / disabled |
| UNIQUE(provider_id, model_name) | | |

### `pricing_history`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| model_id | UUID FK → models.id NOT NULL | |
| input_price_per_1k | NUMERIC(10,6) NOT NULL | USD |
| output_price_per_1k | NUMERIC(10,6) NOT NULL | USD |
| effective_from | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| effective_to | TIMESTAMPTZ NULL | NULL = still current |
| INDEX(model_id, effective_from) | | for fast "price at time T" lookups |

### `requests`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users.id NOT NULL | |
| mode | VARCHAR NOT NULL | 'manual' / 'comparison' / 'auto' |
| prompt_text | TEXT NOT NULL | |
| estimated_complexity | VARCHAR | 'simple' / 'medium' / 'complex' |
| model_id | UUID FK → models.id NOT NULL | model actually used |
| status | VARCHAR NOT NULL | 'success' / 'failed' / 'fallback_used' |
| created_at | TIMESTAMPTZ DEFAULT now() | |
| INDEX(user_id, created_at) | | dashboard time-range queries |

### `responses`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| request_id | UUID FK → requests.id UNIQUE NOT NULL | |
| response_text | TEXT NOT NULL | |
| finish_reason | VARCHAR | |
| raw_response | JSONB | full provider payload, for debugging |
| created_at | TIMESTAMPTZ DEFAULT now() | |

### `usage_metrics`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| request_id | UUID FK → requests.id UNIQUE NOT NULL | |
| input_tokens_estimated | INTEGER | |
| output_tokens_estimated | INTEGER | |
| input_tokens_actual | INTEGER NOT NULL | |
| output_tokens_actual | INTEGER NOT NULL | |
| latency_ms | INTEGER NOT NULL | |
| estimated_cost_usd | NUMERIC(10,6) NOT NULL | |
| actual_cost_usd | NUMERIC(10,6) NOT NULL | |

### `quality_evaluations`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| request_id | UUID FK → requests.id UNIQUE NOT NULL | |
| quality_score | SMALLINT NOT NULL | 0–100 |
| evaluation_method | VARCHAR NOT NULL | 'rubric' / 'llm_judge' / 'human' |
| evaluator_notes | TEXT NULL | |
| created_at | TIMESTAMPTZ DEFAULT now() | |

### `optimization_results`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| request_id | UUID FK → requests.id UNIQUE NOT NULL | |
| routing_strategy | VARCHAR NOT NULL | 'baseline' / 'weighted_scoring' / etc. |
| candidates_considered | JSONB NOT NULL | array of {model_id, estimated_cost, estimated_quality, eligible} |
| chosen_model_id | UUID FK → models.id NOT NULL | |
| chosen_reason | TEXT NOT NULL | human-readable justification |
| fallback_triggered | BOOLEAN DEFAULT false | |
| created_at | TIMESTAMPTZ DEFAULT now() | |

## 4. Relationships Summary

- `users` 1:N `requests`; `users` 1:1 `budget_settings`
- `providers` 1:N `models`; `models` 1:N `pricing_history`
- `requests` 1:1 `responses`, 1:1 `usage_metrics`, 1:1 `quality_evaluations`, 1:1 `optimization_results`
- `requests` N:1 `models` (the model actually used)
- `optimization_results.candidates_considered` stores a denormalized JSONB snapshot rather than a join table — candidates considered is a point-in-time decision log, not a queryable relationship that needs referential integrity.

## 5. Primary/Foreign Keys & Indexes — rationale

- All PKs are UUIDs (not auto-increment ints) since this avoids leaking request volume and works cleanly if the system is later split into services.
- `requests.user_id + created_at` composite index: the dashboard's primary access pattern is "this user's activity over a time range."
- `pricing_history.model_id + effective_from` index: cost recalculation/audits need fast "what was the price at time T" lookups.
- `models(provider_id, model_name)` unique constraint: prevents duplicate registry entries for the same provider+model.

## 6. SQL Migration (initial)

See `backend/migrations/001_initial_schema.sql` in the repo for the runnable DDL (Alembic-managed going forward).

---
*Status: Draft for review — awaiting approval before proceeding to Phase 4 (Backend Foundation).*
