from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Secrets only come from environment variables. Defaults deliberately start in
    mock mode so a new learner can explore the architecture without buying API
    credits or accidentally sending private learning data to a model provider.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Margin Notes · Business English Coach"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    secret_key: str = "change-this-in-production-32-chars"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    database_url: str = "sqlite:///./data/coach.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173"

    ai_provider: str = "mock"
    ai_api_key: str = ""
    ai_base_url: str | None = None
    ai_model: str = "gpt-4.1-mini"
    evaluator_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    speech_provider: str = "mock"
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "coral"

    upload_dir: Path = Field(default=Path("data/uploads"))
    max_upload_mb: int = 10
    context_message_limit: int = 12
    context_token_budget: int = 7000
    tool_timeout_seconds: float = 12.0
    max_tool_retries: int = 2
    mcp_server_url: str = "http://mcp:8010/mcp"
    metrics_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
