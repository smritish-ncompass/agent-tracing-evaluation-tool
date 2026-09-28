"""Shared test fixtures for the agent tracing evaluation tool."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import agent_tracing.storage.models  # noqa: F401
from agent_tracing.database import Base
from agent_tracing.storage.repository import TraceRepository

# Use sqlite for tests if no PostgreSQL available
DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncTestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an isolated database session for testing."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncTestSession() as session:
        yield session
        await session.close()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def trace_repository(db_session: AsyncSession) -> TraceRepository:
    """Provide a TraceRepository backed by an in-memory test database."""
    return TraceRepository(db_session)
