# Phase 7 — Model Router

## 1. What Was Built

- `app/services/task_analyzer.py` — heuristic complexity classifier (simple/medium/complex) based on prompt length + keyword matching. Deliberately simple and auditable for the MVP baseline.
- `app/routing/models.py` — `ModelCandidate`, `RoutingConstraints`, `CandidateEvaluation`, `RoutingDecision` dataclasses. `RoutingDecision.as_optimization_result_dict()` maps directly onto the `optimization_results` table.
- `app/routing/strategies.py` — pluggable `RoutingStrategy` interface with two implementations:
  - `BaselineStrategy` (MVP default): picks the lowest-cost eligible candidate.
  - `WeightedScoringStrategy`: normalized weighted sum of cost and quality (latency term stubbed at 0 pending historical latency data - post-MVP).
- `app/routing/router.py` — `ModelRouter`: Stage 1 filtering (quality floor, budget, active status, exclusions) + Stage 2 selection (delegated to the active strategy), plus `route_with_fallback()` for bounded-retry fallback (FR8).
- `tests/test_router.py` — 25 tests, including a fixture that mirrors the exact worked example from `docs/01-requirements.md` §4 (Model A/B/C at quality 65/84/93).

## 2. Verifying Against the Requirements Doc's Worked Example

`docs/01-requirements.md` §4 gives a concrete worked example:

```
Model A: cost=$0.01, quality=65
Model B: cost=$0.05, quality=84
Model C: cost=$0.20, quality=93

Required quality 80 -> Model B should be preferred
Required quality 90 -> Model C may be selected
```

`tests/test_router.py` reproduces this almost verbatim as a fixture and asserts the router picks B at `min_quality=80` and C at `min_quality=90` - this is a direct test of the router against the spec it was written from, not just an abstract unit test.

## 3. A Bug Caught During Testing (stated honestly, per Rule 11)

The first implementation of `WeightedScoringStrategy` scored cost as raw `1 / cost`. This is unbounded - a cheap model's `1/cost` term can be two orders of magnitude larger than a `0-1` quality term, so **the cost term swamped quality regardless of how the weights were set**. A test written specifically to check "quality should win when quality is weighted at 0.9" failed, catching this before it shipped.

Fix: cost is now min-max normalized *within the eligible candidate set* (cheapest → 1.0, most expensive → 0.0) before the weighted sum, putting both terms on the same 0-1 scale so the configured weights actually control the tradeoff. Re-ran the full suite after the fix - 48/48 pass. This is exactly the kind of thing Phase 7's "test it against benchmark tasks" step in the master plan is meant to surface before the routing algorithm is trusted for the Phase 11 experiments.

## 4. Design Notes

- **Two-stage separation is enforced structurally, not just by convention**: `ModelRouter._evaluate_candidates()` does all filtering and produces `CandidateEvaluation` objects (eligible or not, with a reason) *before* any strategy sees the data. A strategy's `select()` only ever receives the already-eligible list - it cannot accidentally select an ineligible candidate.
- **Every decision is fully auditable** (NFR6): `CandidateEvaluation` records why each candidate was or wasn't eligible, and `chosen_reason` is a human-readable sentence, not just a score. This is what will get persisted into `optimization_results.candidates_considered`.
- **Bounded fallback** (FR8): `route_with_fallback(max_attempts=2)` returns an ordered list of decisions to *try*, excluding the previously-chosen model on each subsequent attempt - it does not itself call any provider or retry indefinitely. The execution pipeline (wired up in a later phase, once the API layer orchestrates adapters + router + cost engine together) is responsible for attempting them in order and stopping at the first success.
- **`NoEligibleModelError`** (from Phase 4) is raised, not silently swallowed, when no candidate can satisfy the constraints - matches the explicitly-designed-for case in `docs/01-requirements.md` §12.

## 5. Testing — What Was Actually Run

```
$ pytest tests/ -v
48 passed in 0.54s
```

25 new tests: task analyzer classification (simple/medium/complex, keyword and length triggers, empty-prompt edge case), the worked-example reproduction above, budget/quality filtering, inactive-model exclusion, empty-candidate-list handling, both strategies (including the normalization fix), and fallback ordering/termination behavior.

---
*Status: Draft for review — awaiting approval before proceeding to Phase 8 (Quality Evaluation).*
