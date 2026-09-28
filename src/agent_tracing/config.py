"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")

    # Application
    app_name: str = "agent-tracing-evaluation-tool"
    environment: str = "development"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/agent_tracing"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # OTLP Collector
    otlp_host: str = "0.0.0.0"
    otlp_port: int = 8080

    # LLM Judge
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o"
    llm_base_url: str | None = None
    llm_timeout_seconds: int = 60

    # Eval runner
    eval_max_workers: int = 4


settings = Settings()
