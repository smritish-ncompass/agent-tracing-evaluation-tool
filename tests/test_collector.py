"""Tests for the OTLP collector layer."""

import gzip

import httpx
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from agent_tracing.collector.models import (
    ExportTraceServiceRequest,
    KeyValue,
    ResourceSpans,
    ScopeSpans,
    Span,
)
from agent_tracing.collector.protobuf import decode_export_trace_request
from agent_tracing.collector.router import get_trace_repository
from agent_tracing.collector.service import OTLPService
from agent_tracing.main import app


def make_otlp_request() -> ExportTraceServiceRequest:
    """Build a minimal OTLP request for testing."""
    span = Span(
        trace_id="abc123def456abc123def456abc123def",
        span_id="span001",
        name="test-operation",
        start_time_unix_nano=1000000,
        end_time_unix_nano=2000000,
        attributes=[
            KeyValue(key="gen_ai.operation.name", value=KeyValue(key="", value=None).copy()),
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


# ============================================================================
# OTLP/HTTP protobuf ingestion
# ============================================================================


def build_otlp_protobuf() -> bytes:
    """Build a serialized OTLP ExportTraceServiceRequest protobuf with one span."""
    otlp_request = trace_service_pb2.ExportTraceServiceRequest()
    resource_spans = otlp_request.resource_spans.add()
    resource_spans.resource.attributes.append(
        common_pb2.KeyValue(
            key="service.name",
            value=common_pb2.AnyValue(string_value="claude-code"),
        )
    )
    scope_spans = resource_spans.scope_spans.add()
    scope_spans.scope.name = "claude-code"
    span = scope_spans.spans.add()
    span.trace_id = bytes.fromhex("0123456789abcdef0123456789abcdef")
    span.span_id = bytes.fromhex("0123456789abcdef")
    span.name = "chat"
    span.kind = trace_pb2.Span.SpanKind.SPAN_KIND_CLIENT
    span.start_time_unix_nano = 1_000_000
    span.end_time_unix_nano = 2_000_000
    span.attributes.append(
        common_pb2.KeyValue(
            key="gen_ai.usage.prompt_tokens",
            value=common_pb2.AnyValue(int_value=12),
        )
    )
    return otlp_request.SerializeToString()


def test_decode_export_trace_request_roundtrip():
    """Protobuf payload should decode into the Pydantic model with expected values."""
    decoded = decode_export_trace_request(build_otlp_protobuf())

    assert len(decoded.resource_spans) == 1
    resource_span = decoded.resource_spans[0]
    assert resource_span.resource is not None
    assert resource_span.resource.attributes[0].key == "service.name"
    assert resource_span.resource.attributes[0].value is not None
    assert resource_span.resource.attributes[0].value.to_python() == "claude-code"

    span = resource_span.scope_spans[0].spans[0]
    assert span.trace_id == "0123456789abcdef0123456789abcdef"
    assert span.span_id == "0123456789abcdef"
    assert span.name == "chat"
    assert span.kind == trace_pb2.Span.SpanKind.SPAN_KIND_CLIENT


async def test_ingest_endpoint_accepts_protobuf(db_session, trace_repository):
    """POSTing protobuf should return an OTLP protobuf success response."""
    app.dependency_overrides[get_trace_repository] = lambda: trace_repository
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/traces/",
                content=build_otlp_protobuf(),
                headers={"content-type": "application/x-protobuf"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Response must be valid protobuf, not an attempted UTF-8 decode of binary.
    assert response.headers["content-type"].startswith("application/x-protobuf")
    trace_service_pb2.ExportTraceServiceResponse().ParseFromString(response.content)

    stored = await trace_repository.get_trace_by_id("0123456789abcdef0123456789abcdef")
    assert stored is not None
    assert stored.spans[0].name == "chat"
    assert stored.spans[0].prompt_tokens == 12


async def test_ingest_endpoint_accepts_gzipped_protobuf(db_session, trace_repository):
    """A gzip Content-Encoding body should be decompressed before decoding."""
    app.dependency_overrides[get_trace_repository] = lambda: trace_repository
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/traces/",
                content=gzip.compress(build_otlp_protobuf()),
                headers={
                    "content-type": "application/x-protobuf",
                    "content-encoding": "gzip",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


async def test_ingest_endpoint_rejects_malformed_protobuf(db_session, trace_repository):
    """Malformed binary should return a JSON 400, never a 500 with raw bytes echoed."""
    app.dependency_overrides[get_trace_repository] = lambda: trace_repository
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/traces/",
                content=b"\n\x8a\x0b\x12\xfc\tnot-valid-protobuf\xff\xfe",
                headers={"content-type": "application/x-protobuf"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert "detail" in body
    # The raw binary payload must never be echoed back into the response.
    assert "not-valid-protobuf" not in response.text


async def test_ingest_endpoint_accepts_json(db_session, trace_repository):
    """OTLP JSON encoding should still be accepted."""
    app.dependency_overrides[get_trace_repository] = lambda: trace_repository
    payload = {
        "resource_spans": [
            {
                "scope_spans": [
                    {
                        "spans": [
                            {
                                "trace_id": "json-trace",
                                "span_id": "json-span",
                                "name": "json-op",
                                "start_time_unix_nano": 1,
                                "end_time_unix_nano": 2,
                            }
                        ]
                    }
                ]
            }
        ]
    }
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/traces/", json=payload, headers={"content-type": "application/json"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["trace_ids"] == ["json-trace"]
