"""FastAPI application factory.

Run with ``uv run uvicorn la_rp_peace.api.app:create_app --factory --reload``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from la_rp_peace.api import documents, sources
from la_rp_peace.config import Settings, get_settings
from la_rp_peace.db import make_engine
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.ingestion.profiler import OpenAIProfiler, Profiler
from la_rp_peace.logging_config import configure_logging, get_logger
from la_rp_peace.models import create_schema

log = get_logger(__name__)


def _default_profiler(settings: Settings) -> Profiler | None:
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key or not settings.openai_model:
        log.warning("profiler_not_configured", hint="set OPENAI_API_KEY and OPENAI_MODEL")
        return None
    return OpenAIProfiler(
        api_key,
        settings.openai_model,
        base_url=settings.openai_base_url or None,
        reasoning_effort=settings.openai_reasoning_effort,
    )


def create_app(settings: Settings | None = None, profiler: Profiler | None = None) -> FastAPI:
    """Build the API app with its own engine and parsing queue.

    Args:
        settings: Configuration to use; read from the environment when omitted.
        profiler: Model client for parsing; built from the OpenAI settings when omitted.
            Without one, uploads are refused with 503.

    Returns:
        The configured application.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    profiler = profiler or _default_profiler(settings)
    queue = (
        ParsingQueue(
            session_factory,
            profiler,
            max_chars=settings.profile_max_chars,
            retries=settings.profile_retries,
            workers=settings.parser_workers,
        )
        if profiler is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        create_schema(engine)
        requeued = queue.requeue_pending() if queue is not None else 0
        log.info("api_started", database=engine.url.render_as_string(hide_password=True), requeued=requeued)
        yield
        if queue is not None:
            queue.shutdown()
        engine.dispose()

    app = FastAPI(title="la(rp)-peace: анализ оргструктуры", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.parsing_queue = queue
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(documents.router)
    app.include_router(sources.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
