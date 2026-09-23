"""FastAPI application factory.

Run with ``uv run uvicorn la_rp_peace.api.app:create_app --factory --reload``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from la_rp_peace.api import documents
from la_rp_peace.config import Settings, get_settings
from la_rp_peace.db import make_engine
from la_rp_peace.logging_config import configure_logging, get_logger
from la_rp_peace.models import create_schema

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API app with its own engine; tables are created on startup.

    Args:
        settings: Configuration to use; read from the environment when omitted.

    Returns:
        The configured application.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        create_schema(engine)
        log.info("api_started", database=engine.url.render_as_string(hide_password=True))
        yield
        engine.dispose()

    app = FastAPI(title="la(rp)-peace: анализ оргструктуры", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(documents.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
