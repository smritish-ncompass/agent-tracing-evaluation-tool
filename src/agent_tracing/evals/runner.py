"""Orchestrator and test runner for executing evaluations concurrently."""

import asyncio
import time
from typing import Any

from agent_tracing.config import settings
from agent_tracing.evals.metrics.base import BaseMetric
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
from agent_tracing.evals.schemas import (
    EvalResult,
    TestCase,
    TestCaseResult,
    TestSuiteReport,
    utc_now,
)
from agent_tracing.storage.models import Trace


def instantiate_metric(config: dict[str, Any]) -> BaseMetric:
    """Instantiate a metric from a configuration dictionary."""
    metric_type = config.get("type", "").lower()

    if metric_type in ("json_schema", "jsonschema"):
        return JSONSchemaMetric(schema=config.get("schema"))
    if metric_type == "regex":
        return RegexMetric(pattern=config.get("pattern"), flags=config.get("flags", 0))
    if metric_type == "exact_match":
        return ExactMatchMetric(
            case_sensitive=config.get("case_sensitive", True),
            strip_whitespace=config.get("strip_whitespace", True),
        )
    if metric_type in ("contains", "keywords"):
        return ContainsMetric(
            keywords=config.get("keywords"),
            mode=config.get("mode", "all"),
            case_sensitive=config.get("case_sensitive", False),
        )
    if metric_type in ("tool_selection", "tool_call"):
        return ToolSelectionMetric(
            expected_tool=config.get("expected_tool"),
            expected_arguments=config.get("expected_arguments"),
            exact_args=config.get("exact_args", False),
        )
    if metric_type in ("hallucination", "hallucination_detection"):
        return HallucinationMetric(
            model=config.get("model"),
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )
    if metric_type == "goal_adherence":
        return GoalAdherenceMetric(
            model=config.get("model"),
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )
    if metric_type in ("tone", "tone_and_style"):
        return ToneMetric(
            target_tone=config.get("target_tone", "professional, concise, and helpful"),
            model=config.get("model"),
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )
    if metric_type in ("llm_judge", "custom_judge"):
        return LLMJudgeMetric(
            rubric=config.get("rubric", "Evaluate quality and accuracy."),
            metric_custom_name=config.get("name", "custom_llm_judge"),
            model=config.get("model"),
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )

    raise ValueError(f"Unknown metric type: '{metric_type}'")


class EvalRunner:
    """Orchestrates test case evaluations across multiple metrics asynchronously."""

    def __init__(
        self,
        metrics: list[BaseMetric] | None = None,
        max_workers: int | None = None,
    ) -> None:
        self.metrics = metrics or []
        self.max_workers = max_workers or settings.eval_max_workers
        self._semaphore = asyncio.Semaphore(self.max_workers)

    async def evaluate_test_case(
        self,
        test_case: TestCase,
        metrics: list[BaseMetric] | None = None,
    ) -> TestCaseResult:
        """Evaluate a single test case against all specified metrics."""
        active_metrics = metrics or self.metrics
        results: list[EvalResult] = []

        async def _eval_one(m: BaseMetric) -> EvalResult:
            async with self._semaphore:
                return await m.evaluate(
                    input_data=test_case.input_data,
                    output_data=test_case.output_data,
                    expected=test_case.expected,
                    context=test_case.context,
                )

        eval_tasks = [_eval_one(m) for m in active_metrics]
        results = await asyncio.gather(*eval_tasks)

        all_passed = all(r.passed for r in results) if results else True
        return TestCaseResult(
            test_case_name=test_case.name,
            passed=all_passed,
            metrics=list(results),
            metadata=test_case.metadata,
        )

    async def run_suite(
        self,
        suite_name: str,
        test_cases: list[TestCase],
        metrics: list[BaseMetric] | None = None,
    ) -> TestSuiteReport:
        """Execute a full evaluation suite and return an aggregated report."""
        started_at = utc_now()
        start_time = time.perf_counter()
        active_metrics = metrics or self.metrics

        case_tasks = [
            self.evaluate_test_case(test_case=tc, metrics=active_metrics) for tc in test_cases
        ]
        results = await asyncio.gather(*case_tasks)

        duration_ms = (time.perf_counter() - start_time) * 1000
        completed_at = utc_now()

        total_cases = len(results)
        passed_cases = sum(1 for r in results if r.passed)
        failed_cases = total_cases - passed_cases
        pass_rate = (passed_cases / total_cases) if total_cases > 0 else 1.0

        all_scores = [metric_res.score for test_res in results for metric_res in test_res.metrics]
        average_score = (sum(all_scores) / len(all_scores)) if all_scores else 1.0

        return TestSuiteReport(
            suite_name=suite_name,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=round(pass_rate, 4),
            average_score=round(average_score, 4),
            results=list(results),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2),
        )

    async def evaluate_trace(
        self,
        trace: Trace,
        metrics: list[BaseMetric] | None = None,
    ) -> TestCaseResult:
        """
        Reconstruct agent input/output from trace spans and evaluate.
        """
        prompt = ""
        completion = ""
        context = ""

        # Extract info from spans
        for span in trace.spans:
            attrs = span.attributes or {}
            if "gen_ai.prompt" in attrs:
                prompt = str(attrs["gen_ai.prompt"])
            if "gen_ai.completion" in attrs:
                completion = str(attrs["gen_ai.completion"])
            if "gen_ai.context" in attrs:
                context = str(attrs["gen_ai.context"])

        # Fallback if completion or prompt not in standard gen_ai keys
        if not prompt and trace.spans:
            prompt = trace.spans[0].name
        if not completion and trace.spans:
            completion = str(trace.spans[-1].status_description or trace.spans[-1].name)

        test_case = TestCase(
            name=f"trace_{trace.trace_id}",
            input_data=prompt,
            output_data=completion,
            context=context or None,
            metadata={"trace_id": trace.trace_id, "span_count": len(trace.spans)},
        )
        return await self.evaluate_test_case(test_case, metrics=metrics)
