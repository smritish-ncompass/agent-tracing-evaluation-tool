"""Deterministic evaluation metrics: JSON schema, regex, tool selection, exact match."""

import json
import re
import time
from typing import Any

import jsonschema
from jsonschema.exceptions import ValidationError

from agent_tracing.evals.metrics.base import BaseMetric
from agent_tracing.evals.schemas import EvalResult


class JSONSchemaMetric(BaseMetric):
    """Validates that output is valid JSON conforming to a JSON Schema."""

    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self.schema = schema

    @property
    def name(self) -> str:
        return "json_schema_validation"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        target_schema = self.schema
        if target_schema is None and expected is not None:
            try:
                target_schema = json.loads(expected)
            except Exception as e:
                duration = (time.perf_counter() - start_time) * 1000
                return EvalResult(
                    metric_name=self.name,
                    passed=False,
                    score=0.0,
                    reasoning=f"Invalid expected JSON Schema provided: {e}",
                    execution_time_ms=duration,
                )

        if target_schema is None:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning="No JSON Schema provided in metric configuration or expected parameter.",
                execution_time_ms=duration,
            )

        try:
            parsed_output = json.loads(output_data)
        except json.JSONDecodeError as exc:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning=f"Output is not valid JSON: {exc.msg} at line {exc.lineno} col {exc.colno}",
                execution_time_ms=duration,
            )

        try:
            jsonschema.validate(instance=parsed_output, schema=target_schema)
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=True,
                score=1.0,
                reasoning="Output successfully conforms to JSON Schema.",
                execution_time_ms=duration,
            )
        except ValidationError as exc:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning=f"JSON Schema validation failed: {exc.message} (path: {list(exc.path)})",
                metadata={"schema_path": list(exc.schema_path)},
                execution_time_ms=duration,
            )


class RegexMetric(BaseMetric):
    """Validates that output matches a given regular expression pattern."""

    def __init__(self, pattern: str | None = None, flags: int = 0) -> None:
        self.pattern = pattern
        self.flags = flags

    @property
    def name(self) -> str:
        return "regex_match"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        target_pattern = self.pattern or expected
        if target_pattern is None:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning="No regex pattern provided in metric configuration or expected parameter.",
                execution_time_ms=duration,
            )

        try:
            compiled = re.compile(target_pattern, self.flags)
        except re.error as err:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning=f"Invalid regex pattern '{target_pattern}': {err}",
                execution_time_ms=duration,
            )

        match = compiled.search(output_data)
        duration = (time.perf_counter() - start_time) * 1000
        if match is not None:
            return EvalResult(
                metric_name=self.name,
                passed=True,
                score=1.0,
                reasoning=f"Output matches pattern '{target_pattern}'.",
                metadata={"matched_text": match.group(0)},
                execution_time_ms=duration,
            )

        return EvalResult(
            metric_name=self.name,
            passed=False,
            score=0.0,
            reasoning=f"Output does not match regex pattern '{target_pattern}'.",
            execution_time_ms=duration,
        )


class ExactMatchMetric(BaseMetric):
    """Validates exact equality between output and expected string."""

    def __init__(self, case_sensitive: bool = True, strip_whitespace: bool = True) -> None:
        self.case_sensitive = case_sensitive
        self.strip_whitespace = strip_whitespace

    @property
    def name(self) -> str:
        return "exact_match"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        if expected is None:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning="No expected value provided for exact match.",
                execution_time_ms=duration,
            )

        actual_cmp = output_data.strip() if self.strip_whitespace else output_data
        expected_cmp = expected.strip() if self.strip_whitespace else expected

        if not self.case_sensitive:
            actual_cmp = actual_cmp.lower()
            expected_cmp = expected_cmp.lower()

        passed = actual_cmp == expected_cmp
        duration = (time.perf_counter() - start_time) * 1000
        return EvalResult(
            metric_name=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            reasoning="Output matches expected value exactly."
            if passed
            else "Output does not match expected value.",
            execution_time_ms=duration,
        )


class ContainsMetric(BaseMetric):
    """Validates that output contains required keywords or substrings."""

    def __init__(
        self,
        keywords: list[str] | None = None,
        mode: str = "all",  # "all" or "any"
        case_sensitive: bool = False,
    ) -> None:
        self.keywords = keywords or []
        self.mode = mode.lower()
        self.case_sensitive = case_sensitive

    @property
    def name(self) -> str:
        return "contains_keywords"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        target_keywords = list(self.keywords)
        if expected is not None:
            try:
                parsed = json.loads(expected)
                if isinstance(parsed, list):
                    target_keywords.extend(str(item) for item in parsed)
                else:
                    target_keywords.append(str(parsed))
            except json.JSONDecodeError:
                target_keywords.append(expected)

        if not target_keywords:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning="No keywords provided to check for containment.",
                execution_time_ms=duration,
            )

        text_to_check = output_data if self.case_sensitive else output_data.lower()
        matched: list[str] = []
        missing: list[str] = []

        for kw in target_keywords:
            kw_to_check = kw if self.case_sensitive else kw.lower()
            if kw_to_check in text_to_check:
                matched.append(kw)
            else:
                missing.append(kw)

        if self.mode == "any":
            passed = len(matched) > 0
            score = 1.0 if passed else 0.0
        else:  # mode == "all"
            passed = len(missing) == 0
            score = len(matched) / len(target_keywords) if target_keywords else 0.0

        duration = (time.perf_counter() - start_time) * 1000
        reasoning = (
            f"Found {len(matched)}/{len(target_keywords)} required keywords."
            if passed
            else f"Missing required keywords: {missing}"
        )

        return EvalResult(
            metric_name=self.name,
            passed=passed,
            score=round(score, 4),
            reasoning=reasoning,
            metadata={"matched": matched, "missing": missing, "mode": self.mode},
            execution_time_ms=duration,
        )


class ToolSelectionMetric(BaseMetric):
    """Validates that agent selected the expected tool and arguments."""

    def __init__(
        self,
        expected_tool: str | None = None,
        expected_arguments: dict[str, Any] | None = None,
        exact_args: bool = False,
    ) -> None:
        self.expected_tool = expected_tool
        self.expected_arguments = expected_arguments
        self.exact_args = exact_args

    @property
    def name(self) -> str:
        return "tool_selection_accuracy"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        target_tool = self.expected_tool
        target_args = self.expected_arguments

        if expected is not None:
            try:
                parsed_expected = json.loads(expected)
                if isinstance(parsed_expected, dict):
                    target_tool = parsed_expected.get("name") or target_tool
                    target_args = parsed_expected.get("arguments") or target_args
            except json.JSONDecodeError:
                target_tool = target_tool or expected

        if target_tool is None:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning="No expected tool name specified.",
                execution_time_ms=duration,
            )

        try:
            actual_call = json.loads(output_data)
            if not isinstance(actual_call, dict):
                raise ValueError("Output is not a JSON object representing a tool call.")
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning=f"Failed to parse tool call from output: {exc}",
                execution_time_ms=duration,
            )

        actual_tool = actual_call.get("name") or actual_call.get("tool")
        actual_args = (
            actual_call.get("arguments")
            or actual_call.get("args")
            or actual_call.get("parameters")
            or {}
        )

        if actual_tool != target_tool:
            duration = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                metric_name=self.name,
                passed=False,
                score=0.0,
                reasoning=f"Selected tool '{actual_tool}' does not match expected '{target_tool}'.",
                metadata={"actual_tool": actual_tool, "expected_tool": target_tool},
                execution_time_ms=duration,
            )

        # Tool name matches, check arguments if specified
        if target_args is not None:
            if self.exact_args:
                if actual_args != target_args:
                    duration = (time.perf_counter() - start_time) * 1000
                    return EvalResult(
                        metric_name=self.name,
                        passed=False,
                        score=0.5,
                        reasoning=f"Tool '{actual_tool}' matched but arguments did not match exactly.",
                        metadata={"actual_args": actual_args, "expected_args": target_args},
                        execution_time_ms=duration,
                    )
            else:
                missing_keys: list[str] = []
                mismatched_keys: list[str] = []
                for k, v in target_args.items():
                    if k not in actual_args:
                        missing_keys.append(k)
                    elif actual_args[k] != v:
                        mismatched_keys.append(k)

                if missing_keys or mismatched_keys:
                    duration = (time.perf_counter() - start_time) * 1000
                    reason_parts = []
                    if missing_keys:
                        reason_parts.append(f"missing argument keys: {missing_keys}")
                    if mismatched_keys:
                        reason_parts.append(f"mismatched argument keys: {mismatched_keys}")
                    return EvalResult(
                        metric_name=self.name,
                        passed=False,
                        score=0.5,
                        reasoning=f"Tool matched but argument check failed: {', '.join(reason_parts)}",
                        metadata={"actual_args": actual_args, "expected_args": target_args},
                        execution_time_ms=duration,
                    )

        duration = (time.perf_counter() - start_time) * 1000
        return EvalResult(
            metric_name=self.name,
            passed=True,
            score=1.0,
            reasoning=f"Tool '{target_tool}' and arguments verified successfully.",
            metadata={"tool": actual_tool, "arguments": actual_args},
            execution_time_ms=duration,
        )
