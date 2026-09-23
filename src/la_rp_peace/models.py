"""ORM mapping of the database schema in ``schema.sql``.

The tables follow stage 1 of the methodology (methodology/01_document_parsing.md). They are
created by ``schema.sql`` (see ``create_schema``), never by SQLAlchemy, so the columns below
mirror the SQL and add no constraints of their own.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, ForeignKey, Integer, LargeBinary, Text, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from la_rp_peace.db import Base

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def utc_timestamp() -> str:
    """Return the current time in the methodology's format, e.g. 2026-09-23T10:00:00.000Z."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class Document(Base):
    """A registered file, its metadata card and its extracted text."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(Text)
    source_format: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approval_document_type: Mapped[str | None] = mapped_column(Text)
    approval_number: Mapped[str | None] = mapped_column(Text)
    document_created_on: Mapped[str | None] = mapped_column(Text)
    approved_on: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[str | None] = mapped_column(Text)
    metadata_evidence: Mapped[str] = mapped_column(Text, default="{}")
    file_metadata: Mapped[str] = mapped_column(Text, default="{}")
    original_text: Mapped[str | None] = mapped_column(Text)
    source_map: Mapped[str] = mapped_column(Text, default="[]")
    parsing_profile: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(Text, default="pending")
    uploaded_at: Mapped[str] = mapped_column(Text, default=utc_timestamp)
    doc_set: Mapped[str | None] = mapped_column(Text)
    entities_status: Mapped[str] = mapped_column(Text, default="not_started")


class DocumentFile(Base):
    """The uploaded bytes of a document."""

    __tablename__ = "document_files"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class DocumentNode(Base):
    """One element of a document tree; ``text`` is its own text, the range covers its children."""

    __tablename__ = "document_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    node_type: Mapped[str] = mapped_column(Text)
    marker: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    source_start: Mapped[int] = mapped_column(Integer)
    source_end: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship()


class ParsingIssue(Base):
    """A problem found while parsing a document, optionally tied to one node."""

    __tablename__ = "parsing_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    node_id: Mapped[int | None] = mapped_column(Integer)
    issue_type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    is_blocking: Mapped[int] = mapped_column(Integer, default=1)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=utc_timestamp)


class Entity(Base):
    """An organisational object of one document (stage 2)."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(Integer)
    parent_status: Mapped[str] = mapped_column(Text)
    parent_candidates: Mapped[str] = mapped_column(Text, default="[]")
    name: Mapped[str] = mapped_column(Text)
    aliases: Mapped[str] = mapped_column(Text, default="[]")
    entity_type: Mapped[str] = mapped_column(Text)
    position_type: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[str] = mapped_column(Text, default="[]")
    review_status: Mapped[str] = mapped_column(Text, default="pending")


class EntityRelation(Base):
    """A relation between two entities other than organisational membership."""

    __tablename__ = "entity_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    from_entity_id: Mapped[int] = mapped_column(Integer)
    to_entity_id: Mapped[int] = mapped_column(Integer)
    relation_type: Mapped[str] = mapped_column(Text)
    conditions: Mapped[str | None] = mapped_column(Text)


class EntitySource(Base):
    """A verbatim quote from a node that supports an entity or relation claim."""

    __tablename__ = "entity_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    relation_id: Mapped[int | None] = mapped_column(Integer)
    node_id: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    quote_start: Mapped[int] = mapped_column(Integer)
    quote_end: Mapped[int] = mapped_column(Integer)
    supports: Mapped[str] = mapped_column(Text)


class EntityBlock(Base):
    """Processing mark of one block sent to the model."""

    __tablename__ = "entity_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    node_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)


class EntityIssue(Base):
    """A stage 2 problem, optionally tied to an entity or relation."""

    __tablename__ = "entity_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    relation_id: Mapped[int | None] = mapped_column(Integer)
    issue_type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    is_blocking: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=utc_timestamp)


def create_schema(engine: Engine) -> None:
    """Create all tables on a new database.

    Existing databases are left untouched; there are no migrations.

    Args:
        engine: Engine bound to the target SQLite database.

    Raises:
        TypeError: If the engine is not backed by the sqlite3 driver.
    """
    if inspect(engine).has_table("documents"):
        return
    raw = engine.raw_connection()
    try:
        connection = raw.driver_connection
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("The schema scripts need a sqlite3 connection")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        raw.close()
