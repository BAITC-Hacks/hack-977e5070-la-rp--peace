"""Application settings loaded from the environment and an optional .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
        openai_reasoning_effort: Reasoning effort for reasoning models; empty to omit the
            parameter for models that do not accept it.
        profile_max_chars: Documents rendered longer than this are sampled for the model.
        profile_retries: Corrected answers requested after the first one.
        parser_workers: Documents parsed in parallel.
        entity_block_max_chars: Size limit of one stage 2 block shown to the model; larger
            sections are split at child boundaries.
        entity_retries: Corrected stage 2 answers requested after the first, per call.
        activity_block_max_chars: Size limit of one stage 3 block shown to the model.
        activity_retries: Corrected stage 3 answers requested per block after the first.
        entity_parallel: Stage 2 blocks asked at once (waves read against the registry so far).
        activity_parallel: Stage 3 blocks asked at once.
        openai_embedding_model: Embedding model of stages 4.1/4.2; their thresholds assume it.
        analysis_retries: Corrected answers requested per verification batch after the first.
        analysis_parallel: Verification batches of stages 4.1/4.2 asked at once.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/larp.sqlite3"
    max_upload_mb: int = 20
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    log_level: str = "INFO"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    openai_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = "none"
    # Stage 1 (structure profile) needs some reasoning: with "none" edition 9 ends in needs_review.
    profile_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = "low"
    profile_max_chars: int = Field(default=150_000, ge=1_000)
    profile_retries: int = Field(default=2, ge=0)
    parser_workers: int = Field(default=2, ge=1)
    entity_block_max_chars: int = Field(default=4_000, ge=1_000)
    entity_retries: int = Field(default=2, ge=0)
    activity_block_max_chars: int = Field(default=4_000, ge=1_000)
    activity_retries: int = Field(default=2, ge=0)
    entity_parallel: int = Field(default=64, ge=1)
    activity_parallel: int = Field(default=64, ge=1)
    openai_embedding_model: str = "text-embedding-3-large"
    analysis_retries: int = Field(default=2, ge=0)
    analysis_parallel: int = Field(default=32, ge=1)

    @field_validator("openai_reasoning_effort", "profile_reasoning_effort", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def max_upload_bytes(self) -> int:
        """Return the upload limit in bytes."""
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
