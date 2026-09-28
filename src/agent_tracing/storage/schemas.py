"""Pydantic schemas for trace and span storage."""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class SpanCreate(BaseModel):
    """Schema for creating a span."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    span_id: str = Field(min_length=1, max_length=32)
    parent_span_id: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    kind: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict)
    status_code: int | None = None
    status_description: str | None = None
    start_time_unix_nano: int = Field(ge=0)
    end_time_unix_nano: int = Field(ge=0)
    duration_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias=AliasChoices("metadata", "span_metadata")
    )
    scope_name: str | None = Field(default=None, max_length=255)
    scope_version: str | None = Field(default=None, max_length=64)
    scope_attributes: dict[str, Any] = Field(default_factory=dict)


class TraceCreate(BaseModel):
    """Schema for creating a trace."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1, max_length=64)
    resource_attributes: dict[str, Any] = Field(default_factory=dict)
    schema_url: str | None = Field(default=None, max_length=255)
    spans: list[SpanCreate] = Field(default_factory=list)


class SpanRead(BaseModel):
    """Schema for reading a span."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    trace_id: int
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: int | None = None
    attributes: dict[str, Any]
    events: dict[str, Any]
    links: dict[str, Any]
    status_code: int | None = None
    status_description: str | None = None
    start_time_unix_nano: int
    end_time_unix_nano: int
    duration_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("span_metadata", "metadata"),
        serialization_alias="metadata",
    )
    scope_name: str | None = None
    scope_version: str | None = None
    scope_attributes: dict[str, Any]
    created_at: datetime


class TraceRead(BaseModel):
    """Schema for reading a trace with its spans."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    resource_attributes: dict[str, Any]
    schema_url: str | None = None
    spans: list[SpanRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
