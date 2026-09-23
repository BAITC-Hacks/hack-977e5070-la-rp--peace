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
    collisions_status: Mapped[str] = mapped_column(Text, default="not_started")
    cascade_status: Mapped[str] = mapped_column(Text, default="not_started")
    activities_status: Mapped[str] = mapped_column(Text, default="not_started")


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
    category: Mapped[str] = mapped_column(Text, default="unclear")
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
    block_node_id: Mapped[int | None] = mapped_column(Integer)


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


class ActivityRecord(Base):
    """One standalone provision assigned to entities of a document (stage 3)."""

    __tablename__ = "activity_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    block_node_id: Mapped[int] = mapped_column(Integer)
    provision_key: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    designation: Mapped[str] = mapped_column(Text)
    record_type: Mapped[str] = mapped_column(Text)
    formulation: Mapped[str] = mapped_column(Text)
    specificity: Mapped[str] = mapped_column(Text)
    participation: Mapped[str] = mapped_column(Text)
    participant_designation: Mapped[str] = mapped_column(Text)
    participant_entity_ids: Mapped[str] = mapped_column(Text, default="[]")
    condition: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[str | None] = mapped_column(Text)
    periodicity: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text, default="pending")


class ActivitySource(Base):
    """A verbatim quote from a node that supports a record."""

    __tablename__ = "activity_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    record_id: Mapped[int] = mapped_column(Integer)
    node_id: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    quote_start: Mapped[int] = mapped_column(Integer)
    quote_end: Mapped[int] = mapped_column(Integer)
    supports: Mapped[str] = mapped_column(Text)


class ActivityBlock(Base):
    """Processing mark of one stage 3 block."""

    __tablename__ = "activity_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    node_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)


class ActivityIssue(Base):
    """A stage 3 problem, optionally tied to a record."""

    __tablename__ = "activity_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    record_id: Mapped[int | None] = mapped_column(Integer)
    issue_type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    is_blocking: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=utc_timestamp)


class EmbeddingCache(Base):
    """A cached embedding vector of one exact text under one model and text format."""

    __tablename__ = "embedding_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(Text)
    text_format: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(Text)
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)


# Stage 4.1 models (function collisions) go below this line.
class CollisionRun(Base):
    """Coverage of the latest stage 4.1 run of a document: compared sides and pairs per search path."""

    __tablename__ = "collision_runs"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    threshold: Mapped[float] = mapped_column()
    embedding_model: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    text_format: Mapped[str] = mapped_column(Text)
    compared_records: Mapped[int] = mapped_column(Integer)
    compared_views: Mapped[int] = mapped_column(Integer)
    context_records: Mapped[int] = mapped_column(Integer)
    local_pairs: Mapped[int] = mapped_column(Integer)
    local_above: Mapped[int] = mapped_column(Integer)
    category_pairs: Mapped[int] = mapped_column(Integer)
    category_above: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, default=utc_timestamp)


class CollisionView(Base):
    """A consolidated view of one joint assignment (records of one provision with joint participation)."""

    __tablename__ = "collision_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    provision_key: Mapped[str] = mapped_column(Text)
    record_type: Mapped[str] = mapped_column(Text)
    formulation: Mapped[str] = mapped_column(Text)
    participant_entity_ids: Mapped[str] = mapped_column(Text)
    parent_entity_ids: Mapped[str] = mapped_column(Text, default="[]")
    categories: Mapped[str] = mapped_column(Text, default="[]")
    embedded_text: Mapped[str] = mapped_column(Text)


class CollisionViewRecord(Base):
    """A stage 3 record consolidated into a view."""

    __tablename__ = "collision_view_records"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    view_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class CollisionPair(Base):
    """One unordered pair of assignments above the threshold and its verification outcome."""

    __tablename__ = "collision_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    pair_key: Mapped[str] = mapped_column(Text)
    side_a_kind: Mapped[str] = mapped_column(Text)
    side_a_record_id: Mapped[int | None] = mapped_column(Integer)
    side_a_view_id: Mapped[int | None] = mapped_column(Integer)
    side_b_kind: Mapped[str] = mapped_column(Text)
    side_b_record_id: Mapped[int | None] = mapped_column(Integer)
    side_b_view_id: Mapped[int | None] = mapped_column(Integer)
    bases: Mapped[str] = mapped_column(Text)
    basis_details: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column()
    embedding_model: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    text_format: Mapped[str] = mapped_column(Text)
    question_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)


class CollisionSource(Base):
    """A verified verbatim quote backing a pair's verdict."""

    __tablename__ = "collision_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    pair_id: Mapped[int] = mapped_column(Integer)
    node_id: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    quote_start: Mapped[int] = mapped_column(Integer)
    quote_end: Mapped[int] = mapped_column(Integer)
    supports: Mapped[str] = mapped_column(Text)


# Stage 4.2 models (function cascade) go below this line.


class CascadeGroup(Base):
    """An object of level N with its direct executors and the function records compared (stage 4.2)."""

    __tablename__ = "cascade_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    entity_id: Mapped[int] = mapped_column(Integer)
    child_entity_ids: Mapped[str] = mapped_column(Text)
    parent_record_ids: Mapped[str] = mapped_column(Text)
    child_record_ids: Mapped[str] = mapped_column(Text)
    uncertain_entity_ids: Mapped[str] = mapped_column(Text, default="[]")


class CascadeLink(Base):
    """The best parent candidate of one child function and the decision on it."""

    __tablename__ = "cascade_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(Integer)
    child_entity_id: Mapped[int] = mapped_column(Integer)
    child_record_id: Mapped[int] = mapped_column(Integer)
    parent_record_id: Mapped[int | None] = mapped_column(Integer)
    # The float annotation maps to REAL; no column type import needed.
    best_similarity: Mapped[float | None] = mapped_column()
    decision: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    tied_record_ids: Mapped[str] = mapped_column(Text, default="[]")
    embedding_model: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    text_format: Mapped[str] = mapped_column(Text)


class CascadeFinding(Base):
    """A cascade sign for review: parent without children, child without parent, or a link to clarify."""

    __tablename__ = "cascade_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    final: Mapped[int] = mapped_column(Integer)
    record_id: Mapped[int] = mapped_column(Integer)
    entity_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[int | None] = mapped_column(Integer)
    link_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)


class Comparison(Base):
    """A stage 5.2 comparison run of a before side and an after side, with its stored report."""

    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    before_ids: Mapped[str] = mapped_column(Text)
    after_ids: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    params: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
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
