"""SQLite engine construction and the declarative base."""

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _configure_connection(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
    # Foreign keys are off by default in SQLite and apply per connection; cascades and the
    # methodology's composite keys depend on them, so refuse a connection without them.
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        if cursor.execute("PRAGMA foreign_keys").fetchone() != (1,):
            raise RuntimeError("SQLite refused to enable foreign keys")
        # WAL lets the background parser write while API requests read.
        cursor.execute("PRAGMA journal_mode = WAL")
    finally:
        cursor.close()


def make_engine(url: str) -> Engine:
    """Create a SQLite engine with foreign keys enforced on every connection.

    In-memory databases (the test suite) share one connection across FastAPI's worker
    threads; file databases get their parent directory created.

    Args:
        url: SQLAlchemy SQLite URL, e.g. ``sqlite:///data/larp.sqlite3``.

    Returns:
        A configured engine.

    Raises:
        ValueError: If the URL is not a SQLite URL.
    """
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        raise ValueError(f"Only SQLite is supported, got {parsed.get_backend_name()!r}")
    connect_args = {"check_same_thread": False}
    if parsed.database in (None, "", ":memory:"):
        engine = create_engine(url, connect_args=connect_args, poolclass=StaticPool)
    else:
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args=connect_args)
    event.listen(engine, "connect", _configure_connection)
    return engine
