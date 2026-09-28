"""FastAPI router for executing evaluations on test cases and stored traces."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent_tracing.database import get_db_session
from agent_tracing.evals.runner import EvalRunner, instantiate_metric
from agent_tracing.evals.schemas import (
    TestCaseResult,
    TestSuiteReport,
    TestSuiteRunRequest,
    TraceEvalRequest,
)
from agent_tracing.storage.repository import TraceRepository

router = APIRouter(prefix="/v1/evals", tags=["Evaluations"])


async def get_trace_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TraceRepository:
    """Dependency provider for TraceRepository."""
    return TraceRepository(session)


@router.post("/run", response_model=TestSuiteReport, status_code=status.HTTP_200_OK)
async def run_evaluation_suite(
    payload: TestSuiteRunRequest = Body(...),
) -> TestSuiteReport:
    """Run an evaluation suite across multiple test cases and metrics."""
    try:
        metric_instances = [instantiate_metric(m) for m in payload.metrics]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to instantiate evaluation metrics: {exc}",
        ) from exc

    runner = EvalRunner(metrics=metric_instances)
    report = await runner.run_suite(
        suite_name=payload.suite_name,
        test_cases=payload.test_cases,
    )
    return report


@router.post(
    "/trace/{trace_id}",
    response_model=TestCaseResult,
    status_code=status.HTTP_200_OK,
)
async def evaluate_trace(
    trace_id: str,
    payload: TraceEvalRequest = Body(...),
    repository: TraceRepository = Depends(get_trace_repository),
) -> TestCaseResult:
    """Evaluate a stored trace against specified evaluation metrics."""
    trace = await repository.get_trace_by_id(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with ID '{trace_id}' not found.",
        )

    try:
        metric_instances = [instantiate_metric(m) for m in payload.metrics]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to instantiate evaluation metrics: {exc}",
        ) from exc

    runner = EvalRunner(metrics=metric_instances)
    result = await runner.evaluate_trace(trace=trace)
    return result
