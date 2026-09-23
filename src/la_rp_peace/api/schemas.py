"""Request and response models of the HTTP API (contract: .agents/frontend.md §4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from la_rp_peace.enums import ClauseKind, DocFormat, DocSet, DocType


class DocumentOut(BaseModel):
    """An uploaded document, without its content."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    doc_set: DocSet = Field(serialization_alias="set")
    doc_type: DocType
    format: DocFormat
    title: str | None
    size: int
    clause_count: int
    created_at: datetime


class DocumentPatch(BaseModel):
    """User override of the detected document type."""

    doc_type: DocType


class ClauseOut(BaseModel):
    """One citable fragment; ``parent_id`` lets the client rebuild the tree."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    position: int
    kind: ClauseKind
    number: str | None
    anchor: str
    text: str
    paragraph_index: int | None
    page: int | None
    sheet: str | None
    row: int | None
