"""OTLP trace ingestion service: converts OTLP spans to storage models."""

from typing import Any

from agent_tracing.collector.models import (
    ExportTraceServiceRequest,
    KeyValue,
    KeyValueList,
    ResourceSpans,
    ScopeSpans,
    Span,
    SpanEvent,
    SpanLink,
)
from agent_tracing.storage.repository import TraceRepository
from agent_tracing.storage.schemas import SpanCreate, TraceCreate


class OTLPService:
    """Converts OTLP messages to storage schemas and persists them."""

    def __init__(self, repository: TraceRepository) -> None:
        self.repository = repository

    async def ingest(self, request: ExportTraceServiceRequest) -> list[str]:
        """Ingest an OTLP ExportTraceServiceRequest. Returns created trace IDs."""
        trace_ids: list[str] = []
        for resource_span in request.resource_spans:
            for scope_span in resource_span.scope_spans:
                trace = self._build_trace(resource_span, scope_span)
                if trace is None:
                    continue
                await self.repository.create_trace(trace)
                trace_ids.append(trace.trace_id)
        return trace_ids

    def _build_trace(
        self, resource_span: ResourceSpans, scope_span: ScopeSpans
    ) -> TraceCreate | None:
        """Convert OTLP ResourceSpans + ScopeSpans to a TraceCreate schema."""
        if not scope_span.spans:
            return None

        spans: list[SpanCreate] = []
        trace_id: str | None = None
        for otel_span in scope_span.spans:
            span = self._build_span(otel_span, resource_span, scope_span)
            if span is not None:
                spans.append(span)
                if trace_id is None and otel_span.trace_id:
                    trace_id = otel_span.trace_id

        if not spans or trace_id is None:
            return None

        resource_attrs = (
            KeyValueList(values=resource_span.resource.attributes).to_python()
            if resource_span.resource
            else {}
        )
        return TraceCreate(
            trace_id=trace_id,
            resource_attributes=resource_attrs,
            schema_url=resource_span.schema_url or None,
            spans=spans,
        )

    def _build_span(
        self, otel_span: Span, resource_span: ResourceSpans, scope_span: ScopeSpans
    ) -> SpanCreate | None:
        """Convert an OTLP Span to a SpanCreate storage schema."""
        if not otel_span.trace_id or not otel_span.span_id:
            return None

        attributes = _otel_attributes_to_dict(otel_span.attributes)
        events = _otel_events_to_dict(otel_span.events)
        links = _otel_links_to_dict(otel_span.links)

        # Extract token counts from span attributes using semantic conventions
        prompt_tokens = _extract_int_attr(attributes, "gen_ai.usage.prompt_tokens")
        completion_tokens = _extract_int_attr(attributes, "gen_ai.usage.completion_tokens")
        total_tokens = _extract_int_attr(attributes, "gen_ai.usage.total_tokens")

        # If total_tokens not present but components are, derive it
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        scope = scope_span.scope
        return SpanCreate(
            span_id=otel_span.span_id,
            parent_span_id=otel_span.parent_span_id or None,
            name=otel_span.name,
            kind=otel_span.kind or None,
            attributes=attributes,
            events=events,
            links=links,
            status_code=otel_span.status.code if otel_span.status else None,
            status_description=otel_span.status.message if otel_span.status else None,
            start_time_unix_nano=otel_span.start_time_unix_nano,
            end_time_unix_nano=otel_span.end_time_unix_nano,
            duration_ms=None,  # computed in repository
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            metadata={},  # populated separately if needed
            scope_name=scope.name if scope else None,
            scope_version=scope.version if scope else None,
            scope_attributes=_otel_attributes_to_dict(scope.attributes) if scope else {},
        )


def _otel_attributes_to_dict(attributes: list[KeyValue]) -> dict[str, Any]:
    """Convert a list of OTLP KeyValues to a Python dict."""
    result: dict[str, Any] = {}
    for kv in attributes:
        key = kv.key
        value = kv.value.to_python() if kv.value else None
        # Handle duplicate keys by storing in a list
        if key in result:
            if isinstance(result[key], list):
                result[key].append(value)
            else:
                result[key] = [result[key], value]
        else:
            result[key] = value
    return result


def _otel_events_to_dict(events: list[SpanEvent]) -> dict[str, Any]:
    """Convert OTLP span events to a dict keyed by event name."""
    result: dict[str, Any] = {}
    for event in events:
        attrs = _otel_attributes_to_dict(event.attributes)
        result[event.name] = {"time_unix_nano": event.time_unix_nano, "attributes": attrs}
    return result


def _otel_links_to_dict(links: list[SpanLink]) -> dict[str, Any]:
    """Convert OTLP span links to a dict keyed by span_id."""
    result: dict[str, Any] = {}
    for link in links:
        result[link.span_id] = {
            "trace_id": link.trace_id,
            "trace_state": link.trace_state,
            "attributes": _otel_attributes_to_dict(link.attributes),
        }
    return result


def _extract_int_attr(attributes: dict[str, Any], key: str) -> int | None:
    """Safely extract an integer attribute value."""
    val = attributes.get(key)
    if isinstance(val, int):
        return val
    return None
