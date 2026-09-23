"""FastAPI application factory.

Run with ``uv run uvicorn la_rp_peace.api.app:create_app --factory --reload``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from la_rp_peace.activities.pipeline import ActivityStage
from la_rp_peace.api import activities, cascade, documents, entities, sources
from la_rp_peace.cascade.pipeline import CascadeStage
from la_rp_peace.config import Settings, get_settings
from la_rp_peace.db import make_engine
from la_rp_peace.embeddings import Embedder, OpenAIEmbedder
from la_rp_peace.entities.pipeline import EntityStage
from la_rp_peace.ingestion.pipeline import ParsingQueue, PostParseStage
from la_rp_peace.llm import ChatModel, OpenAIChatModel
from la_rp_peace.logging_config import configure_logging, get_logger
from la_rp_peace.models import create_schema

log = get_logger(__name__)


def _default_model(settings: Settings) -> ChatModel | None:
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key or not settings.openai_model:
        log.warning("chat_model_not_configured", hint="set OPENAI_API_KEY and OPENAI_MODEL")
        return None
    return OpenAIChatModel(
        api_key,
        settings.openai_model,
        base_url=settings.openai_base_url or None,
        reasoning_effort=settings.openai_reasoning_effort,
    )


def _default_embedder(settings: Settings) -> Embedder | None:
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        log.warning("embedder_not_configured", hint="set OPENAI_API_KEY; stage 4.2 is left out")
        return None
    return OpenAIEmbedder(api_key, settings.openai_embedding_model, base_url=settings.openai_base_url or None)


def _post_parse_stages(settings: Settings, model: ChatModel) -> list[PostParseStage]:
    """Stages chained after stage 1, in order; each later stage builds on the earlier ones."""
    stages: list[PostParseStage] = [
        EntityStage(model, settings.entity_block_max_chars, settings.entity_retries),
        ActivityStage(model, max_chars=settings.activity_block_max_chars, retries=settings.activity_retries),
    ]
    embedder = _default_embedder(settings)
    if embedder is not None:
        stages.append(CascadeStage(model, embedder, retries=settings.analysis_retries))
    return stages


def create_app(settings: Settings | None = None, model: ChatModel | None = None) -> FastAPI:
    """Build the API app with its own engine and parsing queue.

    Args:
        settings: Configuration to use; read from the environment when omitted.
        model: Chat model for the pipeline; built from the OpenAI settings when omitted.
            Without one, uploads are refused with 503.

    Returns:
        The configured application.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    model = model or _default_model(settings)
    queue = (
        ParsingQueue(
            session_factory,
            model,
            max_chars=settings.profile_max_chars,
            retries=settings.profile_retries,
            workers=settings.parser_workers,
            stages=_post_parse_stages(settings, model),
        )
        if model is not None
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
    app.include_router(entities.router)
    app.include_router(activities.router)
    app.include_router(cascade.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
