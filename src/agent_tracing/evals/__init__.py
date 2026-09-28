"""Evaluation framework for deterministic and LLM-as-a-judge metrics."""

from agent_tracing.evals.metrics import (
    BaseMetric,
    ContainsMetric,
    ExactMatchMetric,
    GoalAdherenceMetric,
    HallucinationMetric,
    JSONSchemaMetric,
    LLMJudgeMetric,
    RegexMetric,
    ToneMetric,
    ToolSelectionMetric,
)
from agent_tracing.evals.runner import EvalRunner, instantiate_metric
from agent_tracing.evals.schemas import (
    EvalResult,
    TestCase,
    TestCaseResult,
    TestSuiteReport,
    TestSuiteRunRequest,
    TraceEvalRequest,
)

__all__ = [
    # Metrics
    "BaseMetric",
    "JSONSchemaMetric",
    "RegexMetric",
    "ExactMatchMetric",
    "ContainsMetric",
    "ToolSelectionMetric",
    "HallucinationMetric",
    "GoalAdherenceMetric",
    "ToneMetric",
    "LLMJudgeMetric",
    # Runner
    "EvalRunner",
    "instantiate_metric",
    # Schemas
    "EvalResult",
    "TestCase",
    "TestCaseResult",
    "TestSuiteReport",
    "TestSuiteRunRequest",
    "TraceEvalRequest",
]
