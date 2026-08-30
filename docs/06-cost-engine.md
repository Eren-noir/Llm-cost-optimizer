# Phase 6 — Cost Engine

## 1. What Was Built

- `app/services/cost_engine.py` — pure calculation functions (`estimate_cost`, `actual_cost`, `calculate_cost`), `PricingSnapshot` and `CostBreakdown` dataclasses. No database or network dependency, so this is exhaustively unit-testable.
- `app/services/pricing_repository.py` — DB-backed pricing registry: `get_current_pricing`, `get_pricing_at` (point-in-time lookup for audits), `update_pricing` (append-only history, never overwrites).
- `app/services/token_tracking.py` — thin glue connecting Phase 5's `TokenEstimate`/`ProviderResponse` to the cost engine.
- `tests/test_cost_engine.py` — 13 tests covering arithmetic correctness, edge cases (zero/negative tokens), estimate-vs-actual flagging, and the estimate/actual delta used later for RQ3 analysis.

## 2. Design Decisions

**Decimal, not float, for all money.** Floating-point arithmetic on currency accumulates rounding error across thousands of requests. Every price and cost figure uses Python's `Decimal`, matching the `NUMERIC` columns in the schema.

**Pure functions separated from DB access.** The actual cost formula lives in `cost_engine.py` with zero database dependency, so it can be unit tested completely without a live Postgres instance. `pricing_repository.py` is a thin wrapper that fetches a `PricingSnapshot` from the DB and hands it to the pure functions — keeping the untested-in-this-sandbox surface area (DB access) as small as possible. This was a deliberate choice given no live Postgres instance is running in this development environment; see the honesty note below.

**`is_estimate` flag is structural, not just documentation.** Every `CostBreakdown` carries `is_estimate: bool` so callers (API responses, persistence layer) cannot accidentally present an estimate as an actual charge — this directly satisfies FR3/NFR4.

**Append-only pricing history, enforced in code.** `update_pricing()` never mutates an existing `pricing_history` row — it closes the current one (`effective_to = now`) and inserts a new one. This means a cost computed last month remains reproducible today even if the provider has since changed prices, via `get_pricing_at()`.

## 3. Cost Formula (implemented exactly as specified in docs/01-requirements.md §6)

```
input_cost  = (input_tokens  / 1000) * input_price_per_1k
output_cost = (output_tokens / 1000) * output_price_per_1k
total_cost  = input_cost + output_cost
```

All results rounded to 6 decimal places (`ROUND_HALF_UP`), matching the `NUMERIC(10,6)` columns.

## 4. Testing — What Was Actually Run

```
$ pytest tests/ -v
27 passed in 0.54s
```

13 of those are new cost-engine tests: basic arithmetic, linear scaling (10x tokens → 10x cost), zero-token edge case, negative-token rejection, estimate/actual flagging, premium-vs-cheap cost comparison, full traceability of the breakdown (`as_dict()` fields reconstruct the total), and the estimate-vs-actual delta calculation.

## 5. Known Limitation (stated honestly, per Rule 11 — no fabricated results)

`pricing_repository.py` (the DB-backed half of the registry) is **not** covered by an automated test in this sandbox, because no live PostgreSQL instance is running here. It was verified to import cleanly and its logic was manually reviewed against the schema, but it has not been exercised against a real database yet. This should be the first thing verified once PostgreSQL is set up locally (`backend/README.md` has setup steps) — a quick manual check (insert a model + provider, call `update_pricing`, then `get_current_pricing`) would close this gap before Phase 11 (Benchmarking) relies on it.

---
*Status: Draft for review — awaiting approval before proceeding to Phase 7 (Model Router).*
