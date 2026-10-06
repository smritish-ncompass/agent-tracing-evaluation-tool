"""FastAPI router for OTLP trace ingestion endpoints."""

import gzip
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from agent_tracing.collector.models import ExportTraceServiceRequest
from agent_tracing.collector.protobuf import decode_export_trace_request
from agent_tracing.collector.service import OTLPService
from agent_tracing.database import get_db_session
from agent_tracing.storage.repository import TraceRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/traces", tags=["OTLP Traces"])

PROTOBUF_CONTENT_TYPE = "application/x-protobuf"
JSON_CONTENT_TYPE = "application/json"


async def get_trace_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TraceRepository:
    """Dependency provider for TraceRepository."""
    return TraceRepository(session)


def _protobuf_success_response() -> Response:
    """Return an OTLP/HTTP protobuf success response (empty ExportTraceServiceResponse)."""
    body = trace_service_pb2.ExportTraceServiceResponse().SerializeToString()
    return Response(content=body, media_type=PROTOBUF_CONTENT_TYPE)


def _json_error_response(status_code: int, message: str) -> JSONResponse:
    """Return a JSON error response that never echoes the raw (binary) request body."""
    return JSONResponse(status_code=status_code, content={"error": message})


def _parse_otlp_request(raw_body: bytes, content_type: str) -> ExportTraceServiceRequest:
    """Decode an OTLP request body per its content type.

    Supports ``application/x-protobuf`` (standard OTLP/HTTP) and ``application/json``
    (OTLP JSON encoding). Raises ``HTTPException`` with a safe message on malformed input.
    """
    if content_type.startswith(PROTOBUF_CONTENT_TYPE):
        try:
            return decode_export_trace_request(raw_body)
        except (DecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed OTLP protobuf payload: {exc}",
            ) from exc

    if content_type.startswith(JSON_CONTENT_TYPE) or content_type == "":
        try:
            return ExportTraceServiceRequest.model_validate_json(raw_body)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed OTLP JSON payload.",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"Unsupported content type '{content_type}'. "
            f"Use '{PROTOBUF_CONTENT_TYPE}' or '{JSON_CONTENT_TYPE}'."
        ),
    )


@router.post(
    "/",
    status_code=status.HTTP_200_OK,
    description=(
        "Ingest OpenTelemetry Protocol (OTLP) traces via HTTP POST. "
        "Accepts both protobuf (application/x-protobuf) and JSON (application/json) encodings, "
        "optionally gzip-compressed via Content-Encoding."
    ),
)
async def ingest_traces(
    request: Request,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
) -> Response:
    """Accept a raw OTLP ExportTraceServiceRequest and persist traces to PostgreSQL.

    The body is read as bytes so binary protobuf is never coerced into JSON.
    """
    raw_body = await request.body()

    # Transparently decompress gzip-encoded bodies (OTLP/HTTP allows Content-Encoding: gzip).
    content_encoding = request.headers.get("content-encoding", "").lower().strip()
    if content_encoding and content_encoding != "identity":
        if content_encoding == "gzip":
            try:
                raw_body = gzip.decompress(raw_body)
            except (OSError, EOFError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid gzip-encoded request body: {exc}",
                ) from exc
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported Content-Encoding '{content_encoding}'.",
            )

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    otlp_request = _parse_otlp_request(raw_body, content_type)

    service = OTLPService(repository)
    try:
        trace_ids = await service.ingest(otlp_request)
    except Exception as exc:
        logger.exception("Failed to ingest OTLP traces")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest traces: {exc}",
        ) from exc

    logger.info("Ingested OTLP traces", extra={"trace_count": len(trace_ids)})

    if content_type.startswith(JSON_CONTENT_TYPE):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "received": len(otlp_request.resource_spans),
                "trace_ids": trace_ids,
                "status": "accepted",
            },
        )

    return _protobuf_success_response()


@router.get("/", response_model=dict[str, Any])
async def list_traces(
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
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
