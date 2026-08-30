"""
LLM-as-judge quality evaluator.

Uses another LLM (via any LLMProviderAdapter, including MockAdapter
for testing) to score a response 0-100 against the original task.
More capable of assessing relevance/correctness/instruction-following
than the rubric evaluator, but is itself an LLM call - it costs money
and time, and it is an imperfect proxy for true quality (see
LIMITATIONS below and docs/01-requirements.md §8/§13).

LIMITATIONS (documented per docs/01-requirements.md §8):
- The judge model has its own biases and blind spots; it can be
  fooled by confident-sounding but wrong answers, and tends to
  favor longer or more elaborately formatted responses (a
  well-documented bias in LLM-as-judge literature).
- Using an LLM to judge LLM output is circular in a way pure human
  evaluation is not - it should be cross-checked against a human-
  evaluated sample rather than trusted as ground truth on its own.
- Judge output parsing can fail if the judge doesn't follow the
  requested format; this module fails loudly (raises) rather than
  silently guessing a score, so failures are visible rather than
  quietly corrupting benchmark results.
"""
from __future__ import annotations

import json
import re

from app.core.errors import AppError
from app.evaluation.models import METHOD_LLM_JUDGE, QualityScore
from app.providers.base import LLMProviderAdapter, RequestParams

_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial evaluator scoring an AI assistant's response to a task. "
    "Score strictly on: relevance to the task, correctness (to the extent you can "
    "assess it), completeness, and instruction-following. Do not reward length or "
    "confident tone on their own. "
    "Respond with ONLY a JSON object of the exact form: "
    '{"score": <integer 0-100>, "justification": "<one or two sentences>"}. '
    "No other text."
)

_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


class JudgeParsingError(AppError):
    status_code = 502
    default_message = "Could not parse a valid score from the judge model's response."


def _build_judge_prompt(task_prompt: str, response_text: str) -> str:
    return (
        f"TASK GIVEN TO THE ASSISTANT:\n{task_prompt}\n\n"
        f"ASSISTANT'S RESPONSE:\n{response_text}\n\n"
        "Score this response now, following the required JSON format exactly."
    )


def parse_judge_output(raw_text: str) -> QualityScore:
    """Pure parsing function, tested independently of any adapter -
    extracts the JSON object the judge was asked to produce and
    validates the score is a 0-100 integer."""
    match = _JSON_OBJECT_PATTERN.search(raw_text or "")
    if not match:
        raise JudgeParsingError(f"No JSON object found in judge output: {raw_text!r}")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParsingError(f"Judge output was not valid JSON: {exc}") from exc

    if "score" not in parsed:
        raise JudgeParsingError(f"Judge JSON missing 'score' field: {parsed!r}")

    try:
        score = int(parsed["score"])
    except (TypeError, ValueError) as exc:
        raise JudgeParsingError(f"Judge 'score' was not an integer: {parsed.get('score')!r}") from exc

    if not 0 <= score <= 100:
        raise JudgeParsingError(f"Judge score {score} out of range 0-100")

    justification = str(parsed.get("justification", "")).strip() or "(no justification provided by judge)"

    return QualityScore(score=score, method=METHOD_LLM_JUDGE, notes=justification)


class LLMJudgeEvaluator:
    method = METHOD_LLM_JUDGE

    def __init__(self, judge_adapter: LLMProviderAdapter, max_output_tokens: int = 200):
        self.judge_adapter = judge_adapter
        self.max_output_tokens = max_output_tokens

    def evaluate(self, task_prompt: str, response_text: str) -> QualityScore:
        judge_prompt = _build_judge_prompt(task_prompt, response_text)
        params = RequestParams(
            max_output_tokens=self.max_output_tokens,
            temperature=0.0,  # deterministic-as-possible judging
            system_prompt=_JUDGE_SYSTEM_PROMPT,
        )
        judge_response = self.judge_adapter.send_request(judge_prompt, params)
        return parse_judge_output(judge_response.text)
