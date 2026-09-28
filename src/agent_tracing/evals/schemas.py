"""Pydantic schemas for the evaluation framework."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class EvalResult(BaseModel):
    """Result of an individual metric evaluation."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = Field(default=0.0, ge=0.0)


class TestCase(BaseModel):
    """A single test case for evaluation."""

    model_config = ConfigDict(extra="forbid")

    name: str
    input_data: str
    output_data: str
    expected: str | None = None
    context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestCaseResult(BaseModel):
    """Evaluation results for a single test case across one or more metrics."""

    model_config = ConfigDict(extra="forbid")

    test_case_name: str
    passed: bool
    metrics: list[EvalResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestSuiteRunRequest(BaseModel):
    """Request payload to execute an evaluation suite."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    test_cases: list[TestCase] = Field(min_length=1)
    metrics: list[dict[str, Any]] = Field(
        min_length=1,
        description="List of metric configurations, e.g. [{'type': 'json_schema', 'schema': {...}}]",
    )


class TraceEvalRequest(BaseModel):
    """Request payload to evaluate an existing trace."""

    model_config = ConfigDict(extra="forbid")

    metrics: list[dict[str, Any]] = Field(
        min_length=1,
        description="List of metric configurations, e.g. [{'type': 'hallucination'}]",
    )


class TestSuiteReport(BaseModel):
    """Aggregated evaluation report for a test suite run."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float = Field(ge=0.0, le=1.0)
    average_score: float = Field(ge=0.0, le=1.0)
    results: list[TestCaseResult] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    duration_ms: float = Field(default=0.0, ge=0.0)
