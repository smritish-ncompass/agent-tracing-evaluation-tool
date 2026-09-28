"""FastAPI application for OTLP trace ingestion."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import agent_tracing.storage.models  # noqa: F401 - ensure models are registered with Base.metadata
from agent_tracing.collector.router import router as traces_router
from agent_tracing.database import Base, engine
from agent_tracing.evals.router import router as evals_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create database tables on startup and clean up on shutdown."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Agent Tracing & Evaluation",
    description="OpenTelemetry trace ingestion and LLM evaluation framework.",
    version=__import__("agent_tracing").__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(traces_router)
app.include_router(evals_router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok", "service": "agent-tracing-evaluation-tool"}
