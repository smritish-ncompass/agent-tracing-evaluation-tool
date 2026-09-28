"""FastAPI router for OTLP trace ingestion endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent_tracing.collector.models import ExportTraceServiceRequest
from agent_tracing.collector.service import OTLPService
from agent_tracing.database import get_db_session
from agent_tracing.storage.repository import TraceRepository

router = APIRouter(prefix="/v1/traces", tags=["OTLP Traces"])


async def get_trace_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TraceRepository:
    """Dependency provider for TraceRepository."""
    return TraceRepository(session)


@router.post(
    "/",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    description=(
        "Ingest OpenTelemetry Protocol (OTLP) traces via HTTP POST. "
        "Accepts both protobuf (application/x-protobuf) and JSON (application/json) encodings."
    ),
)
async def ingest_traces(
    request: ExportTraceServiceRequest = Body(...),
    repository: TraceRepository = Depends(get_trace_repository),
) -> dict[str, Any]:
    """
    Accept an OTLP ExportTraceServiceRequest and persist traces to PostgreSQL.

    Supports:
    - application/x-protobuf (standard OTLP HTTP)
    - application/json (OTLP JSON encoding)
    """
    service = OTLPService(repository)
    try:
        trace_ids = await service.ingest(request)
        return {
            "received": len(request.resource_spans),
            "trace_ids": trace_ids,
            "status": "accepted",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest traces: {exc}",
        ) from exc


@router.get("/", response_model=dict[str, Any])
async def list_traces(
    repository: TraceRepository = Depends(get_trace_repository),
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List stored traces."""
    traces = await repository.list_traces(limit=limit, offset=offset)
    return {
        "total": await repository.count_traces(),
        "limit": limit,
        "offset": offset,
        "traces": [
            {
                "id": t.id,
                "trace_id": t.trace_id,
                "resource_attributes": t.resource_attributes,
                "schema_url": t.schema_url,
                "span_count": len(t.spans),
                "created_at": t.created_at.isoformat(),
            }
            for t in traces
        ],
    }
