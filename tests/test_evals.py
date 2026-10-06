"""Comprehensive tests for evaluation metrics and runner orchestration."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agent_tracing.config import settings
from agent_tracing.evals.metrics.deterministic import (
    ContainsMetric,
    ExactMatchMetric,
    JSONSchemaMetric,
    RegexMetric,
    ToolSelectionMetric,
)
from agent_tracing.evals.metrics.judge import (
    GoalAdherenceMetric,
    HallucinationMetric,
    LLMJudgeMetric,
    ToneMetric,
)
from agent_tracing.evals.runner import EvalRunner, instantiate_metric
from agent_tracing.evals.schemas import TestCase, TestSuiteReport
from agent_tracing.storage.models import Span, Trace

# ============================================================================
# JSON Schema Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_json_schema_metric_valid():
    """Test JSONSchemaMetric with valid JSON matching schema."""
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    metric = JSONSchemaMetric(schema=schema)

    result = await metric.evaluate(
        input_data="test",
        output_data='{"name": "Alice"}',
    )

    assert result.passed is True
    assert result.score == 1.0
    assert result.metric_name == "json_schema_validation"


@pytest.mark.asyncio
async def test_json_schema_metric_invalid_json():
    """Test JSONSchemaMetric with invalid JSON."""
    schema = {"type": "object"}
    metric = JSONSchemaMetric(schema=schema)

    result = await metric.evaluate(
        input_data="test",
        output_data="not valid json",
    )

    assert result.passed is False
    assert result.score == 0.0
    assert "not valid JSON" in result.reasoning


@pytest.mark.asyncio
async def test_json_schema_metric_schema_violation():
    """Test JSONSchemaMetric with JSON violating schema."""
    schema = {"type": "object", "properties": {"age": {"type": "number"}}, "required": ["age"]}
    metric = JSONSchemaMetric(schema=schema)

    result = await metric.evaluate(
        input_data="test",
        output_data='{"name": "Alice"}',
    )

    assert result.passed is False
    assert result.score == 0.0
    assert "validation failed" in result.reasoning


# ============================================================================
# Regex Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_regex_metric_match():
    """Test RegexMetric with matching pattern."""
    metric = RegexMetric(pattern=r"\d{3}-\d{4}")

    result = await metric.evaluate(
        input_data="phone",
        output_data="Call me at 555-1234 today.",
    )

    assert result.passed is True
    assert result.score == 1.0
    assert "555-1234" in result.metadata.get("matched_text", "")


@pytest.mark.asyncio
async def test_regex_metric_no_match():
    """Test RegexMetric with non-matching pattern."""
    metric = RegexMetric(pattern=r"\d{3}-\d{4}")

    result = await metric.evaluate(
        input_data="phone",
        output_data="No phone number here.",
    )

    assert result.passed is False
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_regex_metric_invalid_pattern():
    """Test RegexMetric with invalid regex pattern."""
    metric = RegexMetric(pattern=r"[invalid(")

    result = await metric.evaluate(
        input_data="test",
        output_data="test",
    )

    assert result.passed is False
    assert "Invalid regex pattern" in result.reasoning


# ============================================================================
# Exact Match Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_exact_match_metric_exact():
    """Test ExactMatchMetric with exact match."""
    metric = ExactMatchMetric(case_sensitive=True, strip_whitespace=True)

    result = await metric.evaluate(
        input_data="test",
        output_data="hello world",
        expected="hello world",
    )

    assert result.passed is True
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_exact_match_metric_case_insensitive():
    """Test ExactMatchMetric with case-insensitive comparison."""
    metric = ExactMatchMetric(case_sensitive=False)

    result = await metric.evaluate(
        input_data="test",
        output_data="Hello World",
        expected="hello world",
    )

    assert result.passed is True
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_exact_match_metric_with_whitespace():
    """Test ExactMatchMetric stripping whitespace."""
    metric = ExactMatchMetric(strip_whitespace=True)

    result = await metric.evaluate(
        input_data="test",
        output_data="  hello world  ",
        expected="hello world",
    )

    assert result.passed is True


@pytest.mark.asyncio
async def test_exact_match_metric_no_expected():
    """Test ExactMatchMetric with missing expected value."""
    metric = ExactMatchMetric()

    result = await metric.evaluate(
        input_data="test",
        output_data="hello",
        expected=None,
    )

    assert result.passed is False
    assert result.score == 0.0


# ============================================================================
# Contains Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_contains_metric_all_keywords():
    """Test ContainsMetric with all keywords mode."""
    metric = ContainsMetric(keywords=["hello", "world"], mode="all")

    result = await metric.evaluate(
        input_data="test",
        output_data="hello beautiful world",
    )

    assert result.passed is True
    assert result.score > 0.0


@pytest.mark.asyncio
async def test_contains_metric_any_keywords():
    """Test ContainsMetric with any keywords mode."""
    metric = ContainsMetric(keywords=["hello", "goodbye"], mode="any")

    result = await metric.evaluate(
        input_data="test",
        output_data="hello there",
    )

    assert result.passed is True
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_contains_metric_case_insensitive():
    """Test ContainsMetric with case-insensitive matching."""
    metric = ContainsMetric(keywords=["Hello", "World"], case_sensitive=False)

    result = await metric.evaluate(
        input_data="test",
        output_data="hello WORLD",
    )

    assert result.passed is True


@pytest.mark.asyncio
async def test_contains_metric_missing_keywords():
    """Test ContainsMetric with missing keywords."""
    metric = ContainsMetric(keywords=["hello", "world"], mode="all")

    result = await metric.evaluate(
        input_data="test",
        output_data="only hello",
    )

    assert result.passed is False
    assert "world" in result.metadata.get("missing", [])


# ============================================================================
# Tool Selection Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tool_selection_metric_correct_tool():
    """Test ToolSelectionMetric with correct tool selected."""
    metric = ToolSelectionMetric(expected_tool="search")

    result = await metric.evaluate(
        input_data="find info",
        output_data='{"name": "search", "arguments": {"query": "test"}}',
    )

    assert result.passed is True
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_tool_selection_metric_wrong_tool():
    """Test ToolSelectionMetric with wrong tool."""
    metric = ToolSelectionMetric(expected_tool="search")

    result = await metric.evaluate(
        input_data="find info",
        output_data='{"name": "database_query", "arguments": {}}',
    )

    assert result.passed is False
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_tool_selection_metric_arguments_partial_match():
    """Test ToolSelectionMetric with partial argument match."""
    metric = ToolSelectionMetric(
        expected_tool="search",
        expected_arguments={"query": "test"},
        exact_args=False,
    )

    result = await metric.evaluate(
        input_data="find info",
        output_data='{"name": "search", "arguments": {"query": "test", "limit": 10}}',
    )

    assert result.passed is True


@pytest.mark.asyncio
async def test_tool_selection_metric_arguments_exact_mismatch():
    """Test ToolSelectionMetric with exact argument mismatch."""
    metric = ToolSelectionMetric(
        expected_tool="search",
        expected_arguments={"query": "test"},
        exact_args=True,
    )

    result = await metric.evaluate(
        input_data="find info",
        output_data='{"name": "search", "arguments": {"query": "test", "limit": 10}}',
    )

    assert result.passed is False


# ============================================================================
# Hallucination Metric Tests (LLM-as-a-judge)
# ============================================================================


@pytest.mark.asyncio
async def test_hallucination_metric_no_api_key(monkeypatch):
    """Test HallucinationMetric with missing API key."""
    # Explicitly remove the API key from the application settings so this
    # test remains independent of the developer's .env file.
    monkeypatch.setattr(settings, "llm_api_key", None)

    metric = HallucinationMetric()

    result = await metric.evaluate(
        input_data="user query",
        output_data="generated response",
        context="reference context",
    )

    assert result.passed is False
    assert result.score == 0.0
    assert "not configured" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_hallucination_metric_successful():
    """Test HallucinationMetric with mocked LLM response."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "passed": True,
                            "score": 0.95,
                            "reasoning": "No hallucinations detected.",
                        }
                    )
                }
            }
        ]
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    metric = HallucinationMetric(api_key="test-key", client=mock_client)

    result = await metric.evaluate(
        input_data="user query",
        output_data="generated response",
        context="reference context",
    )

    assert result.passed is True
    assert result.score == 0.95


# ============================================================================
# Goal Adherence Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_goal_adherence_metric_successful():
    """Test GoalAdherenceMetric with mocked LLM response."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "passed": True,
                            "score": 0.88,
                            "reasoning": "Goal successfully achieved.",
                        }
                    )
                }
            }
        ]
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    metric = GoalAdherenceMetric(api_key="test-key", client=mock_client)

    result = await metric.evaluate(
        input_data="retrieve user data",
        output_data="user data successfully retrieved",
        expected="fetch user information",
    )

    assert result.passed is True
    assert result.score == 0.88


# ============================================================================
# Tone Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tone_metric_successful():
    """Test ToneMetric with mocked LLM response."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "passed": True,
                            "score": 0.92,
                            "reasoning": "Professional and concise tone maintained.",
                        }
                    )
                }
            }
        ]
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    metric = ToneMetric(
        target_tone="professional, concise, and helpful",
        api_key="test-key",
        client=mock_client,
    )

    result = await metric.evaluate(
        input_data="help with a task",
        output_data="Here is the solution to your task...",
    )

    assert result.passed is True
    assert result.score == 0.92


# ============================================================================
# Custom LLM Judge Metric Tests
# ============================================================================


@pytest.mark.asyncio
async def test_llm_judge_metric_custom_rubric():
    """Test LLMJudgeMetric with custom rubric."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "passed": True,
                            "score": 0.85,
                            "reasoning": "Meets custom rubric criteria.",
                        }
                    )
                }
            }
        ]
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    metric = LLMJudgeMetric(
        rubric="Output must be clear, accurate, and concise.",
        metric_custom_name="clarity_accuracy_check",
        api_key="test-key",
        client=mock_client,
    )

    result = await metric.evaluate(
        input_data="explain concept",
        output_data="The concept is clearly explained.",
    )

    assert result.passed is True
    assert result.metric_name == "clarity_accuracy_check"


# ============================================================================
# Metric Instantiation Tests
# ============================================================================


def test_instantiate_metric_json_schema():
    """Test instantiate_metric for JSON Schema."""
    metric = instantiate_metric({"type": "json_schema", "schema": {"type": "object"}})
    assert isinstance(metric, JSONSchemaMetric)


def test_instantiate_metric_regex():
    """Test instantiate_metric for Regex."""
    metric = instantiate_metric({"type": "regex", "pattern": r"\d+"})
    assert isinstance(metric, RegexMetric)


def test_instantiate_metric_exact_match():
    """Test instantiate_metric for Exact Match."""
    metric = instantiate_metric({"type": "exact_match"})
    assert isinstance(metric, ExactMatchMetric)


def test_instantiate_metric_contains():
    """Test instantiate_metric for Contains."""
    metric = instantiate_metric({"type": "contains", "keywords": ["test"]})
    assert isinstance(metric, ContainsMetric)


def test_instantiate_metric_tool_selection():
    """Test instantiate_metric for Tool Selection."""
    metric = instantiate_metric({"type": "tool_selection", "expected_tool": "search"})
    assert isinstance(metric, ToolSelectionMetric)


def test_instantiate_metric_hallucination():
    """Test instantiate_metric for Hallucination."""
    metric = instantiate_metric({"type": "hallucination", "api_key": "test"})
    assert isinstance(metric, HallucinationMetric)


def test_instantiate_metric_goal_adherence():
    """Test instantiate_metric for Goal Adherence."""
    metric = instantiate_metric({"type": "goal_adherence", "api_key": "test"})
    assert isinstance(metric, GoalAdherenceMetric)


def test_instantiate_metric_tone():
    """Test instantiate_metric for Tone."""
    metric = instantiate_metric({"type": "tone", "api_key": "test"})
    assert isinstance(metric, ToneMetric)


def test_instantiate_metric_llm_judge():
    """Test instantiate_metric for LLM Judge."""
    metric = instantiate_metric({"type": "llm_judge", "rubric": "test", "api_key": "test"})
    assert isinstance(metric, LLMJudgeMetric)


def test_instantiate_metric_unknown_type():
    """Test instantiate_metric with unknown type."""
    with pytest.raises(ValueError, match="Unknown metric type"):
        instantiate_metric({"type": "unknown_metric"})


# ============================================================================
# EvalRunner Tests
# ============================================================================


@pytest.mark.asyncio
async def test_eval_runner_single_test_case():
    """Test EvalRunner evaluating single test case."""
    metrics = [
        ExactMatchMetric(),
        RegexMetric(pattern=r"hello"),
    ]
    runner = EvalRunner(metrics=metrics, max_workers=2)

    test_case = TestCase(
        name="test1",
        input_data="greet",
        output_data="hello world",
        expected="hello world",
    )

    result = await runner.evaluate_test_case(test_case)

    assert result.test_case_name == "test1"
    assert len(result.metrics) == 2
    assert all(m.passed for m in result.metrics)


@pytest.mark.asyncio
async def test_eval_runner_suite():
    """Test EvalRunner running full test suite."""
    metrics = [ExactMatchMetric(), RegexMetric(pattern=r"\w+")]
    runner = EvalRunner(metrics=metrics)

    test_cases = [
        TestCase(
            name="tc1",
            input_data="input1",
            output_data="hello",
            expected="hello",
        ),
        TestCase(
            name="tc2",
            input_data="input2",
            output_data="world",
            expected="world",
        ),
    ]

    report = await runner.run_suite(
        suite_name="test_suite",
        test_cases=test_cases,
    )

    assert isinstance(report, TestSuiteReport)
    assert report.suite_name == "test_suite"
    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.pass_rate == 1.0


@pytest.mark.asyncio
async def test_eval_runner_mixed_results():
    """Test EvalRunner with mixed pass/fail results."""
    metrics = [ExactMatchMetric()]
    runner = EvalRunner(metrics=metrics)

    test_cases = [
        TestCase(
            name="pass_case",
            input_data="test",
            output_data="expected",
            expected="expected",
        ),
        TestCase(
            name="fail_case",
            input_data="test",
            output_data="unexpected",
            expected="expected",
        ),
    ]

    report = await runner.run_suite(
        suite_name="mixed_suite",
        test_cases=test_cases,
    )

    assert report.total_cases == 2
    assert report.passed_cases == 1
    assert report.failed_cases == 1
    assert report.pass_rate == 0.5


@pytest.mark.asyncio
async def test_eval_runner_evaluate_trace(db_session):  # noqa: F841
    """Test EvalRunner evaluating a trace."""
    # Create mock trace with spans
    trace = Trace(
        trace_id="trace123",
        resource_attributes={},
    )

    span = Span(
        trace_id=1,
        span_id="span1",
        name="agent_action",
        attributes={"gen_ai.prompt": "what is 2+2?", "gen_ai.completion": "the answer is 4"},
        events={},
        links={},
        start_time_unix_nano=1000,
        end_time_unix_nano=2000,
    )
    trace.spans = [span]

    metrics = [RegexMetric(pattern=r"\d")]
    runner = EvalRunner(metrics=metrics)

    result = await runner.evaluate_trace(trace)

    assert result.test_case_name == "trace_trace123"
    assert len(result.metrics) == 1


@pytest.mark.asyncio
async def test_eval_runner_concurrency():
    """Test EvalRunner respects max_workers concurrency limit."""
    metrics = [ExactMatchMetric()]
    runner = EvalRunner(metrics=metrics, max_workers=1)

    test_cases = [
        TestCase(name=f"tc{i}", input_data="x", output_data="test", expected="test")
        for i in range(3)
    ]

    report = await runner.run_suite("concurrent_test", test_cases)

    assert report.total_cases == 3
    assert report.passed_cases == 3
