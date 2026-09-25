"""Application settings.

Values are read from environment variables first, then from the project-root .env file.
Nothing secret is ever written in this file. See .env.example for every variable.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

# backend/app/core/config.py -> parents[3] is the project root, where .env lives.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        # The same .env also holds frontend (VITE_*) values; the backend ignores them.
        extra="ignore",
    )

    app_name: str = "AI Support Platform"
    app_env: str = "development"
    app_version: str = "0.1.0"

    # Comma-separated list of frontend origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:5173"

    # ---- Database ----
    # The same POSTGRES_* values configure the Docker container, so they are set only once.
    postgres_user: str = "support"
    # No default on purpose: the app refuses to start without a password.
    postgres_password: SecretStr
    postgres_db: str = "support"
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    # Separate database for pytest, so tests never touch development data.
    test_postgres_db: str = "support_test"
    # Full URL override, e.g. for AWS RDS. When set, the POSTGRES_* parts above are ignored.
    database_url_override: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")

    # ---- Authentication ----
    # Signs access tokens. Required, at least 32 characters. Anyone who knows it can forge tokens.
    jwt_secret_key: SecretStr = Field(min_length=32)
    # Short-lived: a stolen access token is only useful for a few minutes.
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    # Secure cookies are only sent over HTTPS (browsers also allow http://localhost).
    # Keep True everywhere except automated tests.
    auth_cookie_secure: bool = True
    # Limit login and register attempts per IP address (needs Redis). Tests turn it off.
    rate_limit_enabled: bool = True

    # ---- Redis + Celery (background jobs) ----
    # REDIS_PORT is also the host port Docker publishes Redis on.
    redis_host: str = "localhost"
    redis_port: int = 6380
    # How often the SLA check runs (seconds).
    sla_check_interval_seconds: int = Field(default=300, ge=10)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # ---- Knowledge base (RAG) ----
    # Chunk size and overlap in characters (~4 characters per token for English).
    rag_chunk_size: int = Field(default=800, ge=200, le=4000)
    rag_chunk_overlap: int = Field(default=150, ge=0, le=1000)
    # How many chunks to give the LLM as context.
    rag_top_k: int = Field(default=4, ge=1, le=10)
    # Chunks less similar than this (cosine similarity, 0-1) are ignored. If none pass, the answer
    # is "I don't know" without calling the LLM. Tuned with evals/run_rag.py.
    rag_min_similarity: float = Field(default=0.55, ge=0.0, le=1.0)
    knowledge_max_upload_mb: int = Field(default=5, ge=1, le=50)

    # ---- Tickets ----
    # How long after a ticket is RESOLVED the customer may still reopen it.
    ticket_reopen_window_days: int = Field(default=7, ge=0, le=90)

    # ---- AI ----
    # Which LLM backend to use. Only "ollama" (local, free) exists today; others plug in
    # by implementing app.ai.providers.base.LLMProvider.
    ai_provider: Literal["ollama"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"
    # Context window in tokens. Ollama's own default is small and silently cuts long prompts.
    ollama_num_ctx: int = Field(default=8192, ge=2048, le=131072)
    # Low temperature = more predictable answers, which is what classification needs.
    ai_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    # CPU-only machines can take a minute or more per answer.
    ai_timeout_seconds: float = Field(default=120.0, gt=0)
    # Extra attempts when the model returns JSON that fails validation.
    ai_max_output_retries: int = Field(default=1, ge=0, le=3)
    # Classify every new ticket in the background (Celery). Turn off to run without AI.
    ai_triage_enabled: bool = True
    # The AI's answer is only used when its confidence is at least this. Below it, a person decides.
    ai_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def database_url(self, *, test: bool = False) -> URL:
        """SQLAlchemy URL for the app database, or the test database when test=True.

        Built with URL.create so special characters in the password need no escaping.
        """
        if self.database_url_override is not None and not test:
            return make_url(self.database_url_override.get_secret_value())
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.test_postgres_db if test else self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    """Build settings once and reuse them. Tests can clear the cache to change values."""
    return Settings()
