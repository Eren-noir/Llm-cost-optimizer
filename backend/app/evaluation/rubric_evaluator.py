"""
Rubric-based quality evaluator.

A deterministic, zero-cost heuristic scorer used as a fast first-pass
signal and as a fallback when an LLM judge isn't available/affordable
for every request in a benchmark run. It does NOT attempt to judge
factual correctness - see LIMITATIONS below and
docs/01-requirements.md §13.

Design: two severe-failure signals (empty response, and refusal/error
patterns) act as score CAPS rather than as just one of several
equally-weighted additive components. An earlier version scored them
additively alongside unrelated positive signals (e.g. "finished
naturally", "plausible length") - which let an outright refusal still
score 80/100, because the other components passed by default and
diluted the penalty. Caught by
tests/test_quality_evaluation.py::test_rubric_penalizes_refusal during
Phase 8 testing. A refusal or an empty response should dominate the
score, not be averaged away by unrelated signals - fixed by capping
the achievable total when either is detected, rather than treating
all four checks as independent and equally weighted.

Scored out of 100:
  - severe-failure cap: empty response caps at 15; refusal/error
    pattern caps at 35 (both checked first)
  - response completed rather than being cut off (25 pts, via finish_reason)
  - length is plausible for the request                (25 pts)
  - (remaining points allocated to "no severe failure detected", so a
    clean response with no refusal/error/truncation/length issues
    reaches 100)

LIMITATIONS (documented per docs/01-requirements.md §8/§13):
This rubric cannot assess whether a response is factually correct,
whether code actually runs, or whether reasoning is sound - it can
only detect gross failure signals (empty output, visible refusals,
truncation, wildly implausible length). It is a floor-level quality
check, not a substitute for LLM-as-judge or human evaluation. Treat a
high rubric score as "not an obvious failure," not as "a good
response."
"""
from __future__ import annotations

from app.evaluation.models import METHOD_RUBRIC, QualityScore
from app.providers.base import ProviderResponse

_REFUSAL_PATTERNS = (
    "i cannot help with that",
    "i can't help with that",
    "i'm not able to",
    "i am not able to",
    "as an ai language model",
    "i cannot assist",
)
_ERROR_PATTERNS = (
    "error:", "traceback (most recent call last)", "undefined is not a function",
    "nullpointerexception", "500 internal server error",
)

_EMPTY_RESPONSE_CAP = 15
_SEVERE_PATTERN_CAP = 35


class RubricEvaluator:
    method = METHOD_RUBRIC

    def evaluate(self, prompt: str, response: ProviderResponse, expected_output_tokens: int | None = None) -> QualityScore:
        text = (response.text or "").strip()
        lowered = text.lower()

        components: list[tuple[str, int, int]] = []

        # Severe-failure signals are checked first and determine the cap -
        # see module docstring for why this is not simple additive scoring.
        if len(text) == 0:
            components.append(("empty response - score capped", 0, 25))
            cap = _EMPTY_RESPONSE_CAP
        elif any(p in lowered for p in _REFUSAL_PATTERNS):
            components.append(("response looks like a refusal - score capped", 0, 25))
            cap = _SEVERE_PATTERN_CAP
        elif any(p in lowered for p in _ERROR_PATTERNS):
            components.append(("response contains an error/traceback pattern - score capped", 0, 25))
            cap = _SEVERE_PATTERN_CAP
        else:
            components.append(("non-empty, no refusal/error patterns detected", 25, 25))
            cap = 100

        # Completion signal
        if response.finish_reason == "stop":
            components.append(("finished naturally (finish_reason=stop)", 25, 25))
        elif response.finish_reason in ("length", "max_tokens"):
            components.append(("response was truncated (hit max tokens)", 10, 25))
        else:
            components.append((f"finish_reason='{response.finish_reason}' (unrecognized)", 15, 25))

        # Plausible length
        target = expected_output_tokens or max(response.output_tokens, 1)
        ratio = response.output_tokens / target if target else 0
        if 0.2 <= ratio <= 3.0:
            components.append(("output length plausible relative to expectation", 25, 25))
        elif ratio < 0.2:
            components.append(("output much shorter than expected", 8, 25))
        else:
            components.append(("output much longer than expected", 15, 25))

        uncapped_total = sum(earned for _, earned, _ in components)
        total = min(uncapped_total, cap)
        notes = "; ".join(f"{label} ({earned}/{possible})" for label, earned, possible in components)
        if total < uncapped_total:
            notes += f"; TOTAL CAPPED at {cap} due to severe-failure signal"

        return QualityScore(score=total, method=self.method, notes=notes)
