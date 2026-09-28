"""Asynchronous repository layer for trace and span persistence."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent_tracing.storage.models import Span, Trace
from agent_tracing.storage.schemas import SpanCreate, TraceCreate


class TraceRepository:
    """Repository for async trace and span CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async session."""
        self.session = session

    async def create_trace(self, trace_data: TraceCreate) -> Trace:
        """Create a trace and its spans atomically."""
        trace = Trace(
            trace_id=trace_data.trace_id,
            resource_attributes=trace_data.resource_attributes,
            schema_url=trace_data.schema_url,
        )
        for span_data in trace_data.spans:
            span = self._build_span(span_data)
            trace.spans.append(span)
        self.session.add(trace)
        await self.session.flush()
        await self.session.refresh(trace)
        return trace

    @staticmethod
    def _build_span(span_data: SpanCreate) -> Span:
        """Build a span ORM object from a schema."""
        duration_ms = span_data.duration_ms
        if duration_ms is None:
            duration_ms = max(
                0.0, (span_data.end_time_unix_nano - span_data.start_time_unix_nano) / 1_000_000
            )
        return Span(
            span_id=span_data.span_id,
            parent_span_id=span_data.parent_span_id,
            name=span_data.name,
            kind=span_data.kind,
            attributes=span_data.attributes,
            events=span_data.events,
            links=span_data.links,
            status_code=span_data.status_code,
            status_description=span_data.status_description,
            start_time_unix_nano=span_data.start_time_unix_nano,
            end_time_unix_nano=span_data.end_time_unix_nano,
            duration_ms=duration_ms,
            prompt_tokens=span_data.prompt_tokens,
            completion_tokens=span_data.completion_tokens,
            total_tokens=span_data.total_tokens,
            span_metadata=span_data.metadata,
            scope_name=span_data.scope_name,
            scope_version=span_data.scope_version,
            scope_attributes=span_data.scope_attributes,
        )

    async def get_trace_by_id(self, trace_id: str) -> Trace | None:
        """Fetch a trace by its hex trace id with spans eagerly loaded."""
        result = await self.session.execute(
            select(Trace).where(Trace.trace_id == trace_id).options(selectinload(Trace.spans))
        )
        return result.scalar_one_or_none()

    async def get_trace_by_pk(self, trace_pk: int) -> Trace | None:
        """Fetch a trace by its primary key with spans eagerly loaded."""
        result = await self.session.execute(
            select(Trace).where(Trace.id == trace_pk).options(selectinload(Trace.spans))
        )
        return result.scalar_one_or_none()

    async def list_traces(self, limit: int = 100, offset: int = 0) -> list[Trace]:
        """List traces ordered by creation time descending."""
        result = await self.session.execute(
            select(Trace)
            .order_by(Trace.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Trace.spans))
        )
        return list(result.scalars().all())

    async def delete_trace(self, trace_pk: int) -> bool:
        """Delete a trace by primary key. Returns True if deleted."""
        trace = await self.get_trace_by_pk(trace_pk)
        if trace is None:
            return False
        await self.session.delete(trace)
        await self.session.flush()
        return True

    async def count_traces(self) -> int:
        """Count total traces."""
        result = await self.session.execute(select(func.count(Trace.id)))
        return int(result.scalar_one())
