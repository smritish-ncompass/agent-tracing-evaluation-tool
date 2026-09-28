"""LLM-as-a-judge evaluation metrics using structured LLM scoring."""

import json
import time
from typing import Any

import httpx

from agent_tracing.config import settings
from agent_tracing.evals.metrics.base import BaseMetric
from agent_tracing.evals.schemas import EvalResult


class BaseLLMJudge(BaseMetric):
    """Base class for LLM-as-a-judge metrics using HTTP API calls."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url or "https://api.openai.com/v1").rstrip(
            "/"
        )
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds
        self._client = client

    async def _call_llm(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        """Send chat completion request to LLM API and parse JSON response."""
        if not self.api_key:
            return {
                "passed": False,
                "score": 0.0,
                "reasoning": "LLM API key not configured (set LLM_API_KEY environment variable).",
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

        async def _request(c: httpx.AsyncClient) -> dict[str, Any]:
            response = await c.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            result: dict[str, Any] = json.loads(raw_content)
            return result

        try:
            if self._client:
                return await _request(self._client)
            async with httpx.AsyncClient() as client:
                return await _request(client)
        except Exception as exc:
            return {
                "passed": False,
                "score": 0.0,
                "reasoning": f"LLM judge API call failed: {exc}",
            }


class HallucinationMetric(BaseLLMJudge):
    """Evaluates whether the agent output contains hallucinations or unsupported claims."""

    @property
    def name(self) -> str:
        return "hallucination_detection"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        reference_info = context or expected or "No reference context provided."

        system_prompt = (
            "You are an impartial evaluation judge assessing AI outputs for hallucinations and factual accuracy. "
            "Evaluate whether all factual claims in the output are strictly supported by the reference context. "
            "You must return a JSON object with keys: "
            "'passed' (boolean), 'score' (float from 0.0 to 1.0 where 1.0 means completely faithful and no hallucinations), "
            "and 'reasoning' (a clear explanation of any ungrounded or hallucinated claims)."
        )

        user_prompt = (
            f"### Reference Context / Ground Truth:\n{reference_info}\n\n"
            f"### User Input / Prompt:\n{input_data}\n\n"
            f"### Agent Output:\n{output_data}\n\n"
            "Assess whether the output contains any hallucinations or unsupported claims. Return JSON only."
        )

        llm_response = await self._call_llm(user_prompt, system_prompt)
        duration = (time.perf_counter() - start_time) * 1000

        score = float(llm_response.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        passed = bool(llm_response.get("passed", score >= 0.7))
        reasoning = str(llm_response.get("reasoning", "Evaluation completed."))

        return EvalResult(
            metric_name=self.name,
            passed=passed,
            score=score,
            reasoning=reasoning,
            metadata={"model": self.model},
            execution_time_ms=duration,
        )


class GoalAdherenceMetric(BaseLLMJudge):
    """Evaluates whether the agent successfully accomplished the user's intended goal."""

    @property
    def name(self) -> str:
        return "goal_adherence"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        expected_clause = f"\n### Expected Outcome:\n{expected}" if expected else ""

        system_prompt = (
            "You are an impartial evaluation judge evaluating whether an AI agent successfully completed the task "
            "requested by the user. Rate goal adherence on a scale from 0.0 (completely failed) to 1.0 (fully accomplished). "
            "You must return a JSON object with keys: "
            "'passed' (boolean, true if score >= 0.7), 'score' (float from 0.0 to 1.0), "
            "and 'reasoning' (detailed explanation of how well the output addresses the goals and instructions)."
        )

        user_prompt = (
            f"### User Request / Instructions:\n{input_data}\n"
            f"{expected_clause}\n"
            f"### Agent Output / Actions:\n{output_data}\n\n"
            "Assess whether the agent adhered to and fulfilled the requested goal. Return JSON only."
        )

        llm_response = await self._call_llm(user_prompt, system_prompt)
        duration = (time.perf_counter() - start_time) * 1000

        score = float(llm_response.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        passed = bool(llm_response.get("passed", score >= 0.7))
        reasoning = str(llm_response.get("reasoning", "Evaluation completed."))

        return EvalResult(
            metric_name=self.name,
            passed=passed,
            score=score,
            reasoning=reasoning,
            metadata={"model": self.model},
            execution_time_ms=duration,
        )


class ToneMetric(BaseLLMJudge):
    """Evaluates whether the agent response matches desired tone and style criteria."""

    def __init__(
        self,
        target_tone: str = "professional, concise, and helpful",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            client=client,
        )
        self.target_tone = target_tone

    @property
    def name(self) -> str:
        return "tone_and_style"

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()
        target = expected or self.target_tone

        system_prompt = (
            "You are an impartial evaluation judge evaluating whether an AI agent's response meets specific tone, "
            f"style, and communication guidelines: '{target}'. "
            "Rate adherence from 0.0 to 1.0. "
            "You must return a JSON object with keys: "
            "'passed' (boolean, true if score >= 0.7), 'score' (float from 0.0 to 1.0), "
            "and 'reasoning' (explanation of tone strengths or deficiencies)."
        )

        user_prompt = (
            f"### Target Tone Guidelines:\n{target}\n\n"
            f"### User Input:\n{input_data}\n\n"
            f"### Agent Output:\n{output_data}\n\n"
            "Assess whether the output aligns with the target tone. Return JSON only."
        )

        llm_response = await self._call_llm(user_prompt, system_prompt)
        duration = (time.perf_counter() - start_time) * 1000

        score = float(llm_response.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        passed = bool(llm_response.get("passed", score >= 0.7))
        reasoning = str(llm_response.get("reasoning", "Evaluation completed."))

        return EvalResult(
            metric_name=self.name,
            passed=passed,
            score=score,
            reasoning=reasoning,
            metadata={"target_tone": target, "model": self.model},
            execution_time_ms=duration,
        )


class LLMJudgeMetric(BaseLLMJudge):
    """Customizable LLM-as-a-judge metric accepting arbitrary evaluation rubrics."""

    def __init__(
        self,
        rubric: str,
        metric_custom_name: str = "custom_llm_judge",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            client=client,
        )
        self.rubric = rubric
        self._custom_name = metric_custom_name

    @property
    def name(self) -> str:
        return self._custom_name

    async def evaluate(
        self,
        input_data: str,
        output_data: str,
        expected: str | None = None,
        context: str | None = None,
        **kwargs: Any,
    ) -> EvalResult:
        start_time = time.perf_counter()

        system_prompt = (
            "You are an impartial evaluation judge. Grade the agent output against the following custom rubric:\n"
            f"{self.rubric}\n\n"
            "You must return a JSON object with keys: "
            "'passed' (boolean), 'score' (float from 0.0 to 1.0), and 'reasoning' (detailed rationale)."
        )

        user_prompt = (
            f"### User Input:\n{input_data}\n\n"
            f"### Context / Expected:\n{context or expected or 'None'}\n\n"
            f"### Agent Output:\n{output_data}\n\n"
            "Evaluate according to the rubric. Return JSON only."
        )

        llm_response = await self._call_llm(user_prompt, system_prompt)
        duration = (time.perf_counter() - start_time) * 1000

        score = float(llm_response.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        passed = bool(llm_response.get("passed", score >= 0.7))
        reasoning = str(llm_response.get("reasoning", "Evaluation completed."))

        return EvalResult(
            metric_name=self.name,
            passed=passed,
            score=score,
            reasoning=reasoning,
            metadata={"rubric": self.rubric, "model": self.model},
            execution_time_ms=duration,
        )
