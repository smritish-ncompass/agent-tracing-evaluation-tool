"""Base interface for all evaluation metrics."""

from abc import ABC, abstractmethod
from typing import Any

from agent_tracing.evals.schemas import EvalResult


class BaseMetric(ABC):
    """Abstract base class for deterministic and LLM-as-a-judge metrics."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the metric."""
        pass

    @abstractmethod
    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        """
        Evaluate an agent input/output pair against expected criteria.

        :param input_data: The prompt or user input supplied to the agent.
        :param output_data: The generated response or action output from the agent.
        :param expected: Optional expected ground truth, regex pattern, or schema.
        :param context: Optional background context or retrieved reference documents.
        :param kwargs: Additional metric-specific parameters.
        :return: An EvalResult containing boolean pass status, normalized score, and reasoning.
        """
        pass
