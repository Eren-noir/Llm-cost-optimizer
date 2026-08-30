"""
Lightweight, provider-agnostic token estimation.

This is a heuristic (~4 characters per token, in line with commonly
cited averages for English text) used for the *pre-call* estimate
that the Task Analyzer and Cost Engine need before a request is sent.
It intentionally does NOT try to replicate each provider's exact
tokenizer - see docs/01-requirements.md, Limitations, on complexity
estimation being heuristic rather than exact. Actual token counts
always come from the provider's own response (see ProviderResponse),
and that is what actual cost is computed from.
"""


def estimate_token_count(text: str) -> int:
    if not text:
        return 0
    # ~4 chars/token heuristic, minimum of 1 token for any non-empty text
    return max(1, len(text) // 4)
