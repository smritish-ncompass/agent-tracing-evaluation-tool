"""SQLAlchemy ORM models for trace and span persistence in PostgreSQL."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_tracing.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(UTC)


class Trace(Base):
    """A single agent trace containing one or more spans."""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    resource_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    schema_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spans: Mapped[list["Span"]] = relationship(
        back_populates="trace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Span(Base):
    """A single span within a trace."""

    __tablename__ = "spans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[int] = mapped_column(
        ForeignKey("traces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    span_id: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    events: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    links: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time_unix_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_time_unix_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    # Token counts extracted from span attributes
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Arbitrary metadata for agent-specific context
    span_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, default=dict, nullable=False
    )
    # Instrumentation scope metadata
    scope_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    trace: Mapped[Trace] = relationship(back_populates="spans")
