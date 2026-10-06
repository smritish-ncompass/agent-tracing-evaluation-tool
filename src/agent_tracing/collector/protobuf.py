"""Decode OTLP/HTTP protobuf payloads into the collector's Pydantic models.

The ingestion and storage layers operate on the Pydantic models defined in
``agent_tracing.collector.models``. This module isolates the wire encoding:
it parses an ``ExportTraceServiceRequest`` protobuf message and converts it
into the equivalent Pydantic model so the existing service logic is reused
unchanged for both protobuf and JSON encodings.
"""

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from agent_tracing.collector.models import (
    AnyValue,
    ArrayValue,
    ExportTraceServiceRequest,
    InstrumentationScope,
    KeyValue,
    KeyValueList,
    Resource,
    ResourceSpans,
    ScopeSpans,
    Span,
    SpanEvent,
    SpanLink,
    SpanStatus,
)


def decode_export_trace_request(payload: bytes) -> ExportTraceServiceRequest:
    """Parse OTLP protobuf bytes into an ``ExportTraceServiceRequest``.

    Raises ``google.protobuf.message.DecodeError`` if the payload is not valid
    protobuf.
    """
    proto = trace_service_pb2.ExportTraceServiceRequest()
    proto.ParseFromString(payload)
    return _convert_request(proto)


def _convert_request(
    proto: trace_service_pb2.ExportTraceServiceRequest,
) -> ExportTraceServiceRequest:
    return ExportTraceServiceRequest(
        resource_spans=[_convert_resource_spans(rs) for rs in proto.resource_spans]
    )


def _convert_resource_spans(proto: trace_pb2.ResourceSpans) -> ResourceSpans:
    return ResourceSpans(
        resource=_convert_resource(proto.resource) if proto.HasField("resource") else None,
        scope_spans=[_convert_scope_spans(ss) for ss in proto.scope_spans],
        schema_url=proto.schema_url,
    )


def _convert_resource(proto: resource_pb2.Resource) -> Resource:
    return Resource(
        attributes=[_convert_key_value(kv) for kv in proto.attributes],
        dropped_attributes_count=proto.dropped_attributes_count,
    )


def _convert_scope_spans(proto: trace_pb2.ScopeSpans) -> ScopeSpans:
    return ScopeSpans(
        scope=_convert_scope(proto.scope) if proto.HasField("scope") else None,
        spans=[_convert_span(span) for span in proto.spans],
        schema_url=proto.schema_url,
    )


def _convert_scope(proto: common_pb2.InstrumentationScope) -> InstrumentationScope:
    return InstrumentationScope(
        name=proto.name,
        version=proto.version,
        attributes=[_convert_key_value(kv) for kv in proto.attributes],
        dropped_attributes_count=proto.dropped_attributes_count,
    )


def _convert_span(proto: trace_pb2.Span) -> Span:
    return Span(
        trace_id=proto.trace_id.hex(),
        span_id=proto.span_id.hex(),
        trace_state=proto.trace_state,
        parent_span_id=proto.parent_span_id.hex(),
        name=proto.name,
        kind=int(proto.kind),
        start_time_unix_nano=proto.start_time_unix_nano,
        end_time_unix_nano=proto.end_time_unix_nano,
        attributes=[_convert_key_value(kv) for kv in proto.attributes],
        dropped_attributes_count=proto.dropped_attributes_count,
        events=[_convert_event(event) for event in proto.events],
        dropped_events_count=proto.dropped_events_count,
        links=[_convert_link(link) for link in proto.links],
        dropped_links_count=proto.dropped_links_count,
        status=_convert_status(proto.status) if proto.HasField("status") else None,
    )


def _convert_event(proto: trace_pb2.Span.Event) -> SpanEvent:
    return SpanEvent(
        time_unix_nano=proto.time_unix_nano,
        name=proto.name,
        attributes=[_convert_key_value(kv) for kv in proto.attributes],
        dropped_attributes_count=proto.dropped_attributes_count,
    )


def _convert_link(proto: trace_pb2.Span.Link) -> SpanLink:
    return SpanLink(
        trace_id=proto.trace_id.hex(),
        span_id=proto.span_id.hex(),
        trace_state=proto.trace_state,
        attributes=[_convert_key_value(kv) for kv in proto.attributes],
        dropped_attributes_count=proto.dropped_attributes_count,
    )


def _convert_status(proto: trace_pb2.Status) -> SpanStatus:
    return SpanStatus(code=int(proto.code), message=proto.message)


def _convert_key_value(proto: common_pb2.KeyValue) -> KeyValue:
    return KeyValue(
        key=proto.key,
        value=_convert_any_value(proto.value) if proto.HasField("value") else None,
    )


def _convert_any_value(proto: common_pb2.AnyValue) -> AnyValue:
    kind = proto.WhichOneof("value")
    if kind == "string_value":
        return AnyValue(string_value=proto.string_value)
    if kind == "bool_value":
        return AnyValue(bool_value=proto.bool_value)
    if kind == "int_value":
        return AnyValue(int_value=proto.int_value)
    if kind == "double_value":
        return AnyValue(double_value=proto.double_value)
    if kind == "array_value":
        return AnyValue(
            array_value=ArrayValue(values=[_convert_any_value(v) for v in proto.array_value.values])
        )
    if kind == "kvlist_value":
        return AnyValue(
            kvlist_value=KeyValueList(
                values=[_convert_key_value(kv) for kv in proto.kvlist_value.values]
            )
        )
    if kind == "bytes_value":
        return AnyValue(bytes_value=proto.bytes_value)
    # Unset AnyValue (or an unknown future variant): represent as a null value.
    return AnyValue()
