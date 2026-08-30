"""
Quality evaluation data model - mirrors the `quality_evaluations`
table (docs/03-database.md).
"""
from __future__ import annotations

from dataclasses import dataclass

METHOD_RUBRIC = "rubric"
METHOD_LLM_JUDGE = "llm_judge"
METHOD_HUMAN = "human"


@dataclass(frozen=True)
class QualityScore:
    score: int  # 0-100
    method: str  # 'rubric' | 'llm_judge' | 'human'
    notes: str

    def __post_init__(self):
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.method not in (METHOD_RUBRIC, METHOD_LLM_JUDGE, METHOD_HUMAN):
            raise ValueError(f"Unknown evaluation method: {self.method}")
