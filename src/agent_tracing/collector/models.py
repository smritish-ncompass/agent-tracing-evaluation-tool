"""Pydantic models for OTLP trace ingestion via HTTP/Protobuf/JSON."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnyValue(BaseModel):
    """OTLP AnyValue message - represents any JSON-serializable value."""

    model_config = ConfigDict(extra="forbid")

    string_value: str | None = None
    bool_value: bool | None = None
    int_value: int | None = None
    double_value: float | None = None
    array_value: Optional["ArrayValue"] = None
    kvlist_value: Optional["KeyValueList"] = None
    bytes_value: bytes | None = None

    def to_python(self) -> Any:
        """Convert OTLP AnyValue to native Python value."""
        if self.string_value is not None:
            return self.string_value
        if self.bool_value is not None:
            return self.bool_value
        if self.int_value is not None:
            return self.int_value
        if self.double_value is not None:
            return self.double_value
        if self.array_value is not None:
            return self.array_value.to_python()
        if self.kvlist_value is not None:
            return self.kvlist_value.to_python()
        if self.bytes_value is not None:
            return self.bytes_value
        return None


class ArrayValue(BaseModel):
    """OTLP ArrayValue message."""

    model_config = ConfigDict(extra="forbid")

    values: list[AnyValue] = Field(default_factory=list)

    def to_python(self) -> list[Any]:
        return [v.to_python() for v in self.values]


class KeyValue(BaseModel):
    """OTLP KeyValue message."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: AnyValue | None = None

    def to_python(self) -> tuple[str, Any]:
        return (self.key, self.value.to_python() if self.value else None)


class KeyValueList(BaseModel):
    """OTLP KeyValueList message."""

    model_config = ConfigDict(extra="forbid")

    values: list[KeyValue] = Field(default_factory=list)

    def to_python(self) -> dict[str, Any]:
        return {k: v for k, v in (kv.to_python() for kv in self.values) if v is not None}


class SpanEvent(BaseModel):
    """OTLP SpanEvent message."""

    model_config = ConfigDict(extra="forbid")

    time_unix_nano: int
    name: str
    attributes: list[KeyValue] = Field(default_factory=list)
    dropped_attributes_count: int = 0


class SpanLink(BaseModel):
    """OTLP SpanLink message."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    span_id: str
    trace_state: str | None = None
    attributes: list[KeyValue] = Field(default_factory=list)
    dropped_attributes_count: int = 0


class SpanStatus(BaseModel):
    """OTLP SpanStatus message."""

    model_config = ConfigDict(extra="forbid")

    code: int = 0  # 0=UNSET, 1=OK, 2=ERROR
    message: str = ""


class InstrumentationScope(BaseModel):
    """OTLP InstrumentationScope message."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    version: str = ""
    attributes: list[KeyValue] = Field(default_factory=list)
    dropped_attributes_count: int = 0


class Span(BaseModel):
    """OTLP Span message."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = ""
    span_id: str = ""
    trace_state: str = ""
    parent_span_id: str = ""
    name: str = ""
    kind: int = 0
    start_time_unix_nano: int = 0
    end_time_unix_nano: int = 0
    attributes: list[KeyValue] = Field(default_factory=list)
    dropped_attributes_count: int = 0
    events: list[SpanEvent] = Field(default_factory=list)
    dropped_events_count: int = 0
    links: list[SpanLink] = Field(default_factory=list)
    dropped_links_count: int = 0
    status: SpanStatus | None = None

    @field_validator("trace_id", "span_id", "parent_span_id", mode="before")
    @classmethod
    def _validate_hex_id(cls, v: Any) -> str:
        """Accept bytes, hex string, or int for trace/span IDs."""
        if isinstance(v, bytes):
            return v.hex()
        if isinstance(v, int):
            return format(v, "032x") if v.bit_length() > 64 else format(v, "016x")
        if isinstance(v, str):
            return v
        return str(v)


class ResourceSpans(BaseModel):
    """OTLP ResourceSpans message."""

    model_config = ConfigDict(extra="forbid")

    resource: Optional["Resource"] = None
    scope_spans: list["ScopeSpans"] = Field(default_factory=list)
    schema_url: str = ""


class Resource(BaseModel):
    """OTLP Resource message."""

    model_config = ConfigDict(extra="forbid")

    attributes: list[KeyValue] = Field(default_factory=list)
    dropped_attributes_count: int = 0


class ScopeSpans(BaseModel):
    """OTLP ScopeSpans message."""

    model_config = ConfigDict(extra="forbid")

    scope: InstrumentationScope | None = None
    spans: list[Span] = Field(default_factory=list)
    schema_url: str = ""


class ExportTraceServiceRequest(BaseModel):
    """OTLP ExportTraceServiceRequest message - root of OTLP/HTTP protobuf payload."""

    model_config = ConfigDict(extra="forbid")

    resource_spans: list[ResourceSpans] = Field(default_factory=list)
