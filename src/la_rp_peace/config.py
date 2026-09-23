"""Application settings loaded from the environment and an optional .env file."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend.

    Attributes:
        database_url: SQLAlchemy SQLite URL of the database file.
        max_upload_mb: Largest accepted upload, in megabytes.
        cors_origins: Origins allowed to call the API from a browser.
        log_level: Minimum structlog level.
        openai_api_key: Key for the profiling model; parsing is unavailable without it.
        openai_model: Model name for the profiling call; required together with the key.
        openai_base_url: Alternative OpenAI-compatible endpoint, if any.
        profile_max_chars: Documents rendered longer than this are sampled for the model.
        profile_retries: Corrected answers requested after the first one.
        parser_workers: Documents parsed in parallel.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/larp.sqlite3"
    max_upload_mb: int = 20
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    profile_max_chars: int = Field(default=150_000, ge=1_000)
    profile_retries: int = Field(default=2, ge=0)
    parser_workers: int = Field(default=2, ge=1)

    @property
    def max_upload_bytes(self) -> int:
        """Return the upload limit in bytes."""
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
