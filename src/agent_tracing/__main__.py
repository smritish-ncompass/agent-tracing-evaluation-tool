"""Run the FastAPI application with uvicorn."""

import uvicorn

from agent_tracing.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "agent_tracing.main:app",
        host=settings.otlp_host,
        port=settings.otlp_port,
        reload=settings.debug,
    )
