"""Database engine construction and the declarative base."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

_CONNECT_TIMEOUT_SECONDS = 5


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(url: str) -> Engine:
    """Create an engine for the given URL.

    In-memory SQLite (used by the test suite) needs a single shared connection that
    may be used from FastAPI's worker threads. Postgres connections time out quickly so
    a stopped database fails startup with an error instead of hanging it.

    Args:
        url: SQLAlchemy database URL.

    Returns:
        A configured engine.
    """
    if url.startswith("sqlite") and ":memory:" in url:
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url.startswith("postgresql"):
        return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS})
    return create_engine(url, pool_pre_ping=True)
