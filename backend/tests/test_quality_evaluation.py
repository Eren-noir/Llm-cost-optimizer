"""
Tests for Phase 8: quality evaluation (rubric + LLM-as-judge).
"""
import pytest

from app.evaluation.llm_judge_evaluator import (
    JudgeParsingError,
    LLMJudgeEvaluator,
    parse_judge_output,
)
from app.evaluation.models import METHOD_LLM_JUDGE, METHOD_RUBRIC, QualityScore
from app.evaluation.rubric_evaluator import RubricEvaluator
from app.providers.base import ProviderResponse
from app.providers.mock_adapter import MockAdapter


# --- QualityScore validation ---------------------------------------------

def test_quality_score_rejects_out_of_range():
    with pytest.raises(ValueError):
        QualityScore(score=150, method=METHOD_RUBRIC, notes="x")
    with pytest.raises(ValueError):
        QualityScore(score=-1, method=METHOD_RUBRIC, notes="x")


def test_quality_score_rejects_unknown_method():
    with pytest.raises(ValueError):
        QualityScore(score=50, method="vibes", notes="x")


# --- Rubric evaluator -----------------------------------------------------

def _response(text="This is a solid, complete answer to the question.", finish_reason="stop", output_tokens=12):
    return ProviderResponse(
        text=text, input_tokens=20, output_tokens=output_tokens,
        latency_ms=100, finish_reason=finish_reason,
    )


def test_rubric_scores_good_response_highly():
    evaluator = RubricEvaluator()
    result = evaluator.evaluate("Explain photosynthesis briefly.", _response(), expected_output_tokens=15)
    assert result.score >= 75
    assert result.method == METHOD_RUBRIC


def test_rubric_penalizes_empty_response():
    evaluator = RubricEvaluator()
    result = evaluator.evaluate("Explain photosynthesis.", _response(text="", output_tokens=0))
    assert result.score < 50


def test_rubric_penalizes_refusal():
    evaluator = RubricEvaluator()
    result = evaluator.evaluate(
        "Tell me a joke.",
        _response(text="I'm not able to help with that request."),
    )
    assert result.score < 75


def test_rubric_penalizes_error_pattern():
    evaluator = RubricEvaluator()
    result = evaluator.evaluate(
        "Write a function.",
        _response(text="Error: Traceback (most recent call last): something broke"),
    )
    assert result.score < 75


def test_rubric_penalizes_truncation():
    evaluator = RubricEvaluator()
    good = evaluator.evaluate("Explain X.", _response(finish_reason="stop"))
    truncated = evaluator.evaluate("Explain X.", _response(finish_reason="length"))
    assert truncated.score < good.score


def test_rubric_penalizes_implausible_length():
    evaluator = RubricEvaluator()
    result = evaluator.evaluate(
        "Explain X in detail.",
        _response(text="ok", output_tokens=1),
        expected_output_tokens=200,
    )
    assert result.score < 75


def test_rubric_notes_show_component_breakdown():
    """NFR4/NFR6-style transparency: the score should be explainable, not opaque."""
    evaluator = RubricEvaluator()
    result = evaluator.evaluate("Explain X.", _response())
    assert "(" in result.notes and "/" in result.notes  # e.g. "... (25/25)"


# --- LLM judge: pure parsing function --------------------------------------

def test_parse_judge_output_valid_json():
    raw = '{"score": 82, "justification": "Accurate and complete."}'
    result = parse_judge_output(raw)
    assert result.score == 82
    assert result.method == METHOD_LLM_JUDGE
    assert "Accurate" in result.notes


def test_parse_judge_output_with_surrounding_text():
    """Judges sometimes wrap JSON in explanation despite instructions -
    the parser should still find the object."""
    raw = 'Sure, here is my evaluation:\n{"score": 60, "justification": "Partially correct."}\nHope that helps!'
    result = parse_judge_output(raw)
    assert result.score == 60


def test_parse_judge_output_missing_json_raises():
    with pytest.raises(JudgeParsingError):
        parse_judge_output("The response was pretty good, I'd say about an 80.")


def test_parse_judge_output_score_out_of_range_raises():
    with pytest.raises(JudgeParsingError):
        parse_judge_output('{"score": 150, "justification": "way too generous"}')


def test_parse_judge_output_missing_score_field_raises():
    with pytest.raises(JudgeParsingError):
        parse_judge_output('{"justification": "forgot the score field"}')


def test_parse_judge_output_non_integer_score_raises():
    with pytest.raises(JudgeParsingError):
        parse_judge_output('{"score": "excellent", "justification": "n/a"}')


def test_parse_judge_output_missing_justification_still_succeeds():
    result = parse_judge_output('{"score": 70}')
    assert result.score == 70
    assert result.notes  # falls back to placeholder text, never empty


# --- LLM judge: end-to-end with a mock adapter -----------------------------

def test_llm_judge_evaluator_end_to_end_success():
    judge_adapter = MockAdapter(
        model_name="mock-judge",
        canned_response_text='{"score": 88, "justification": "Directly answers the question with correct facts."}',
    )
    evaluator = LLMJudgeEvaluator(judge_adapter=judge_adapter)
    result = evaluator.evaluate("What is the capital of Kenya?", "The capital of Kenya is Nairobi.")
    assert result.score == 88
    assert result.method == METHOD_LLM_JUDGE


def test_llm_judge_evaluator_raises_on_malformed_judge_output():
    """Fails loudly rather than silently guessing - a malformed judge
    response should not quietly corrupt benchmark results."""
    judge_adapter = MockAdapter(model_name="mock-judge", canned_response_text="I think it's pretty good, no complaints.")
    evaluator = LLMJudgeEvaluator(judge_adapter=judge_adapter)
    with pytest.raises(JudgeParsingError):
        evaluator.evaluate("Some task", "Some response")
