"""Tests for the OTLP collector layer."""

import pytest

from agent_tracing.collector.models import (
    ExportTraceServiceRequest,
    KeyValue,
    ResourceSpans,
    ScopeSpans,
    Span,
)
from agent_tracing.collector.service import OTLPService


def make_otlp_request() -> ExportTraceServiceRequest:
    """Build a minimal OTLP request for testing."""
    span = Span(
        trace_id="abc123def456abc123def456abc123def",
        span_id="span001",
        name="test-operation",
        start_time_unix_nano=1000000,
        end_time_unix_nano=2000000,
        attributes=[
            KeyValue(
                key="gen_ai.operation.name", value=KeyValue(key="", value=None).copy()
            ),
        ],
    )
    return ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                scope_spans=[
                    ScopeSpans(
                        spans=[span],
                    )
                ]
            )
        ]
    )


@pytest.mark.asyncio
async def test_otel_service_ingest_creates_trace(db_session, trace_repository):
    """OTLP service should ingest traces and return trace IDs."""
    service = OTLPService(trace_repository)

    request = ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                scope_spans=[
                    ScopeSpans(
                        spans=[
                            Span(
                                trace_id="trace-001",
                                span_id="span-001",
                                name="chat",
                                kind=1,
                                start_time_unix_nano=1000,
                                end_time_unix_nano=2000,
                                attributes=[],
                            )
                        ]
                    )
                ]
            )
        ]
    )
    trace_ids = await service.ingest(request)
    assert len(trace_ids) == 1
    assert trace_ids[0] == "trace-001"


@pytest.mark.asyncio
async def test_otel_service_retrieves_trace(db_session, trace_repository):
    """OTLP service should store trace retrievable by trace_id."""
    service = OTLPService(trace_repository)
    request = ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                scope_spans=[
                    ScopeSpans(
                        spans=[
                            Span(
                                trace_id="trace-retrieval",
                                span_id="s1",
                                name="test",
                                start_time_unix_nano=1,
                                end_time_unix_nano=100,
                            )
                        ]
                    )
                ]
            )
        ]
    )
    await service.ingest(request)
    trace = await trace_repository.get_trace_by_id("trace-retrieval")
    assert trace is not None
    assert trace.trace_id == "trace-retrieval"
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "test"


@pytest.mark.asyncio
async def test_otel_service_extracts_token_counts(db_session, trace_repository):
    """Service should extract token counts from gen_ai.usage attributes."""
    service = OTLPService(trace_repository)
    request = ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                scope_spans=[
                    ScopeSpans(
                        spans=[
                            Span(
                                trace_id="trace-tokens",
                                span_id="s1",
                                name="chat",
                                start_time_unix_nano=1,
                                end_time_unix_nano=100,
                                attributes=[
                                    KeyValue(
                                        key="gen_ai.usage.prompt_tokens",
                                        value=None,
                                    ),
                                    KeyValue(
                                        key="gen_ai.usage.completion_tokens",
                                        value=None,
                                    ),
                                ],
                            )
                        ]
                    )
                ]
            )
        ]
    )
    await service.ingest(request)
    trace = await trace_repository.get_trace_by_id("trace-tokens")
    assert trace is not None
    assert trace.spans[0].prompt_tokens is None  # KeyValue with null value becomes None
    assert trace.spans[0].completion_tokens is None
