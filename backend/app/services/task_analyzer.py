"""
Task Analyzer - estimates task complexity before a request is routed
(docs/02-architecture.md workflow, step 1). This is a deliberately
simple, transparent heuristic for the MVP baseline (see
docs/01-requirements.md, Recommended MVP and Limitations: "Task
complexity estimation is a heuristic, not a certainty"). More
sophisticated approaches (classifier-based) are explicitly deferred to
post-MVP (Advanced Features).

The heuristic considers:
- prompt length (longer prompts tend to carry more complex tasks)
- presence of keywords associated with harder task types (code,
  multi-step reasoning, analysis, math)
- requested output length, if the caller specifies one

This is intentionally simple and auditable - every classification can
be explained in one sentence, which matters for RQ3 (how much does
estimation accuracy affect routing quality) and NFR6 (auditability).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.providers.token_estimation import estimate_token_count

COMPLEXITY_SIMPLE = "simple"
COMPLEXITY_MEDIUM = "medium"
COMPLEXITY_COMPLEX = "complex"

# Keywords loosely associated with harder task categories, per the
# benchmark task tiers defined in docs/01-requirements.md section 9.
_COMPLEX_KEYWORDS = (
    "algorithm", "prove", "optimi", "architecture", "refactor",
    "debug", "concurren", "distributed", "derive", "theorem",
    "asymptotic", "recursion", "compile",
)
_MEDIUM_KEYWORDS = (
    "summarize", "compare", "analyze", "explain why", "classify",
    "code", "function", "write a", "translate", "reason",
)

# Token-count thresholds for the length component of the heuristic.
_SIMPLE_TOKEN_CEILING = 60
_MEDIUM_TOKEN_CEILING = 300


@dataclass(frozen=True)
class ComplexityEstimate:
    complexity: str
    input_tokens_estimated: int
    reasoning: str


def estimate_complexity(prompt: str) -> ComplexityEstimate:
    """Heuristic complexity classification. Combines prompt length with
    keyword matching; longer + keyword-matched prompts escalate the
    tier. Ties are broken toward the higher tier (safer to slightly
    over-estimate complexity than under-estimate, since
    under-estimating risks routing a hard task to a model too weak to
    handle it)."""
    if not prompt or not prompt.strip():
        return ComplexityEstimate(
            complexity=COMPLEXITY_SIMPLE,
            input_tokens_estimated=0,
            reasoning="Empty prompt.",
        )

    tokens = estimate_token_count(prompt)
    lowered = prompt.lower()

    has_complex_kw = any(kw in lowered for kw in _COMPLEX_KEYWORDS)
    has_medium_kw = any(kw in lowered for kw in _MEDIUM_KEYWORDS)

    if tokens > _MEDIUM_TOKEN_CEILING or has_complex_kw:
        reason_parts = []
        if tokens > _MEDIUM_TOKEN_CEILING:
            reason_parts.append(f"prompt length ~{tokens} tokens exceeds medium ceiling ({_MEDIUM_TOKEN_CEILING})")
        if has_complex_kw:
            reason_parts.append("matched complex-task keyword")
        return ComplexityEstimate(
            complexity=COMPLEXITY_COMPLEX,
            input_tokens_estimated=tokens,
            reasoning="; ".join(reason_parts),
        )

    if tokens > _SIMPLE_TOKEN_CEILING or has_medium_kw:
        reason_parts = []
        if tokens > _SIMPLE_TOKEN_CEILING:
            reason_parts.append(f"prompt length ~{tokens} tokens exceeds simple ceiling ({_SIMPLE_TOKEN_CEILING})")
        if has_medium_kw:
            reason_parts.append("matched medium-task keyword")
        return ComplexityEstimate(
            complexity=COMPLEXITY_MEDIUM,
            input_tokens_estimated=tokens,
            reasoning="; ".join(reason_parts),
        )

    return ComplexityEstimate(
        complexity=COMPLEXITY_SIMPLE,
        input_tokens_estimated=tokens,
        reasoning=f"Short prompt (~{tokens} tokens), no complexity keywords matched.",
    )


# Default expected output length per complexity tier, used when the
# caller hasn't specified max_output_tokens - deliberately conservative.
DEFAULT_OUTPUT_TOKENS_BY_COMPLEXITY = {
    COMPLEXITY_SIMPLE: 128,
    COMPLEXITY_MEDIUM: 512,
    COMPLEXITY_COMPLEX: 1024,
}
