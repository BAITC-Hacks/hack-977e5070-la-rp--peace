"""Application settings loaded from the environment and an optional .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend.

    Attributes:
        database_url: SQLAlchemy SQLite URL of the database file.
        max_upload_mb: Largest accepted upload, in megabytes.
        cors_origins: Origins allowed to call the API from a browser.
        log_level: Minimum structlog level.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/larp.sqlite3"
    max_upload_mb: int = 20
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @property
    def max_upload_bytes(self) -> int:
        """Return the upload limit in bytes."""
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
