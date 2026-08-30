# Phase 8 — Quality Evaluation

## 1. What Was Built

- `app/evaluation/models.py` — `QualityScore` dataclass (0–100, method, notes), mirrors the `quality_evaluations` table.
- `app/evaluation/rubric_evaluator.py` — deterministic, zero-cost heuristic scorer. No LLM call, no cost, usable on every single request in a benchmark run without burning API budget.
- `app/evaluation/llm_judge_evaluator.py` — uses any `LLMProviderAdapter` (including `MockAdapter`) as a judge, prompts it for a structured `{"score": ..., "justification": ...}` response, and parses it via a pure, independently-tested `parse_judge_output()` function.
- `tests/test_quality_evaluation.py` — 18 tests across both evaluators.

## 2. Two Evaluation Methods, and Why Both

| | Rubric | LLM-as-judge |
|---|---|---|
| Cost | Free, instant | One extra LLM call per evaluation |
| Can detect | Empty output, refusals, truncation, wildly wrong length | Relevance, apparent correctness, completeness, instruction-following |
| Cannot detect | Anything requiring actual understanding of the content | Ground-truth correctness (it's still an LLM guessing) |
| Use case | Cheap first-pass filter; runs on 100% of benchmark requests | Primary quality signal for the smaller sample it's affordable to run on |

Per `docs/01-requirements.md` §8 and §18, the research plan calls for comparing automated evaluation against a human-evaluated sample where possible — both evaluators here write the same `QualityScore` shape (`method` field distinguishes `rubric` / `llm_judge` / `human`), so a small human-annotated subset can be scored by hand later and compared directly against both automated methods with no format mismatch.

## 3. Two Bugs Caught During Testing (stated honestly, per Rule 11)

Testing the rubric evaluator surfaced a real design flaw, not just a threshold issue:

**The problem:** the first version scored four checks (non-empty, no-refusal, completed-naturally, plausible-length) as independent, equally-weighted 25-point components, added together. An outright refusal ("I'm not able to help with that request.") still scored **80/100**, because the other three unrelated checks (it finished cleanly, it wasn't empty, its length was "plausible") passed by default and diluted the one real problem.

**Root cause:** additive scoring treats all failure modes as equally severe and independent, which is wrong — a refusal or an empty response is a *disqualifying* signal, not one-quarter of the picture.

**Fix:** severe-failure signals (empty response, refusal pattern, error pattern) now act as a **cap** on the total achievable score (empty → capped at 15, refusal/error → capped at 35) rather than as one additive term among several. A clean response with no severe-failure signal is uncapped and can still reach 100 via the other components. Three tests (`test_rubric_penalizes_empty_response`, `test_rubric_penalizes_refusal`, `test_rubric_penalizes_error_pattern`) failed against the first implementation and passed after the fix — full detail is in the code comments in `rubric_evaluator.py`, left in place rather than deleted, since the reasoning is useful for the project write-up's methodology/limitations discussion.

## 4. LLM-Judge: Fails Loudly, Not Silently

If the judge model doesn't return valid, in-range JSON, `parse_judge_output()` raises `JudgeParsingError` rather than guessing or defaulting to some score. This was a deliberate choice: a benchmark run that silently substitutes a fallback score for unparseable judge output would quietly corrupt the experimental results in Phase 11 in a way that's hard to detect afterward. A visible failure is preferable to a silently wrong number, especially for a component whose entire job is producing numbers other analysis will be built on.

## 5. Limitations (documented per docs/01-requirements.md §8/§13 — not just here, but worth restating with implementation-specific detail)

- The rubric **cannot** assess factual correctness, whether code runs, or whether reasoning is sound. It only catches gross failure signals.
- The LLM judge is itself an LLM, with the biases documented in the LLM-as-judge literature (verbosity bias, susceptibility to confident-but-wrong answers). Using an LLM to judge LLM output is somewhat circular — cross-checking against a human-evaluated sample (§8) is planned, not yet done, and should happen before final results are reported in Phase 11/18.
- Neither evaluator has been run against a real provider response yet — testing so far uses `MockAdapter` with a canned response, since no real API keys are configured. This is appropriate for verifying the evaluators' *logic* (parsing, scoring, capping) but the actual judge-model prompt (`_JUDGE_SYSTEM_PROMPT` in `llm_judge_evaluator.py`) hasn't been validated against how a real model actually responds to it — worth a manual spot-check once real credentials are available, before relying on it for benchmark runs.

## 6. Testing — What Was Actually Run

```
$ pytest tests/ -v
66 passed in 0.57s
```

18 new tests: `QualityScore` validation, rubric scoring across good/empty/refusal/error/truncated/implausible-length responses (including the capping fix), judge-output parsing (valid JSON, JSON embedded in surrounding text, missing/invalid/out-of-range score, missing justification), and one full evaluator-level test using `MockAdapter`'s new `canned_response_text` option to control what the "judge" says.

---
*Status: Draft for review — awaiting approval before proceeding to Phase 9 (Frontend).*
