"""ORM models for uploaded documents and their parsed clauses."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Engine, Enum, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from la_rp_peace.db import Base
from la_rp_peace.enums import ClauseKind, DocFormat, DocSet, DocType


def _new_id() -> str:
    return str(uuid4())


def _str_enum[E: (DocSet, DocType, DocFormat, ClauseKind)](enum_cls: type[E]) -> Enum:
    """Store enum values (not names) as VARCHAR, portable across Postgres and SQLite."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class Document(Base):
    """An uploaded source document and its original bytes."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    filename: Mapped[str] = mapped_column(String(255))
    doc_set: Mapped[DocSet] = mapped_column("set", _str_enum(DocSet), index=True)
    doc_type: Mapped[DocType] = mapped_column(_str_enum(DocType))
    format: Mapped[DocFormat] = mapped_column(_str_enum(DocFormat))
    title: Mapped[str | None] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    clause_count: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    clauses: Mapped[list["Clause"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Clause.position",
    )


class Clause(Base):
    """One structural fragment of a document: the unit every finding cites."""

    __tablename__ = "clauses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    # Deliberately not a foreign key: clauses of one document are inserted in a single
    # flush, and row order inside a flush is not guaranteed for self-references.
    parent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[ClauseKind] = mapped_column(_str_enum(ClauseKind))
    number: Mapped[str | None] = mapped_column(String(64))
    anchor: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    sheet: Mapped[str | None] = mapped_column(String(255))
    row: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="clauses")


def create_schema(engine: Engine) -> None:
    """Create all tables that do not exist yet.

    Args:
        engine: Engine bound to the target database.
    """
    Base.metadata.create_all(engine)
