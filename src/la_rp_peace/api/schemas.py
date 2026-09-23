"""Request and response models of the HTTP API."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from la_rp_peace.enums import ActivitiesStatus, DocSet, EntitiesStatus, NodeType, ParseStatus


class DocumentOut(BaseModel):
    """A registered document: file facts, metadata card and parsing status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    doc_set: DocSet | None = Field(serialization_alias="set")
    source_format: str
    file_size_bytes: int
    content_sha256: str
    uploaded_at: str
    parse_status: ParseStatus
    entities_status: EntitiesStatus
    activities_status: ActivitiesStatus
    title: str | None
    document_type: str | None
    organization: str | None
    revision: str | None
    approved_by: str | None
    approval_document_type: str | None
    approval_number: str | None
    document_created_on: str | None
    approved_on: str | None
    effective_from: str | None
    node_count: int = 0
    blocking_issues: int = 0
    other_issues: int = 0


class DocumentPatch(BaseModel):
    """User correction of the document type."""

    document_type: str = Field(min_length=1)


class NodeOut(BaseModel):
    """One tree node with its human-readable place in the document."""

    id: int
    parent_id: int | None
    position: int
    node_type: NodeType
    marker: str | None
    text: str
    source_start: int
    source_end: int
    anchor: str
    path: str
    location: dict[str, Any]


class IssueOut(BaseModel):
    """A parsing issue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int | None
    issue_type: str
    message: str
    is_blocking: bool
    resolved_at: str | None
    created_at: str


class ProfileOut(BaseModel):
    """What the agent decided about a document, for review."""

    parsing_profile: dict[str, Any] | None
    metadata_evidence: dict[str, Any]
    file_metadata: dict[str, Any]
