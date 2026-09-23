"""Upload documents, follow their parsing, and read the results."""

import json
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from la_rp_peace.api.deps import SessionDep, SettingsDep
from la_rp_peace.api.schemas import DocumentOut, DocumentPatch, IssueOut, NodeOut, ProfileOut
from la_rp_peace.enums import DocFormat, DocSet, NodeType
from la_rp_peace.ingestion.extract import MEDIA_TYPES, UnsupportedFormatError
from la_rp_peace.ingestion.pipeline import ParsingQueue, register
from la_rp_peace.models import Document, DocumentFile, DocumentNode, ParsingIssue
from la_rp_peace.navigation import describe

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_or_404(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return document


def _out(session: Session, document: Document) -> DocumentOut:
    nodes = session.scalar(select(func.count()).where(DocumentNode.document_id == document.id)) or 0
    issues = session.execute(
        select(ParsingIssue.is_blocking, func.count())
        .where(ParsingIssue.document_id == document.id, ParsingIssue.resolved_at.is_(None))
        .group_by(ParsingIssue.is_blocking),
    ).all()
    counts = {bool(blocking): count for blocking, count in issues}
    out = DocumentOut.model_validate(document)
    return out.model_copy(
        update={"node_count": nodes, "blocking_issues": counts.get(True, 0), "other_issues": counts.get(False, 0)},
    )


def _queue(request: Request) -> ParsingQueue:
    queue: ParsingQueue | None = request.app.state.parsing_queue
    if queue is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Разбор недоступен: не заданы OPENAI_API_KEY и OPENAI_MODEL",
        )
    return queue


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentOut)
def upload_document(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    doc_set: Annotated[DocSet, Form(alias="set")],
) -> DocumentOut:
    """Store an upload and queue it for parsing; poll GET /{id} for ``parse_status``."""
    queue = _queue(request)
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Файл больше {settings.max_upload_mb} МБ")
    try:
        document = register(session, file.filename or "document", data, doc_set)
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    queue.submit(document.id)
    return _out(session, document)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    session: SessionDep, doc_set: Annotated[DocSet | None, Query(alias="set")] = None
) -> list[DocumentOut]:
    """List documents, newest first, optionally filtered by set."""
    query = select(Document).order_by(Document.id.desc())
    if doc_set is not None:
        query = query.where(Document.doc_set == doc_set.value)
    return [_out(session, document) for document in session.scalars(query)]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(session: SessionDep, document_id: int) -> DocumentOut:
    """Return a document's card and parsing status."""
    return _out(session, _get_or_404(session, document_id))


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(session: SessionDep, document_id: int, patch: DocumentPatch) -> DocumentOut:
    """Correct the document type."""
    document = _get_or_404(session, document_id)
    document.document_type = patch.document_type
    session.commit()
    return _out(session, document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(session: SessionDep, document_id: int) -> None:
    """Delete a document with its file, tree and issues."""
    session.delete(_get_or_404(session, document_id))
    session.commit()


@router.get("/{document_id}/nodes", response_model=list[NodeOut])
def list_nodes(session: SessionDep, document_id: int) -> list[NodeOut]:
    """Return the document tree as a flat list in reading order."""
    document = _get_or_404(session, document_id)
    nodes = session.scalars(
        select(DocumentNode).where(DocumentNode.document_id == document_id).order_by(DocumentNode.id),
    ).all()
    places = describe(nodes, json.loads(document.source_map))
    return [
        NodeOut(
            id=node.id,
            parent_id=node.parent_id,
            position=node.position,
            node_type=NodeType(node.node_type),
            marker=node.marker,
            text=node.text,
            source_start=node.source_start,
            source_end=node.source_end,
            anchor=places[node.id].anchor,
            path=places[node.id].path,
            location=places[node.id].location,
        )
        for node in nodes
    ]


@router.get("/{document_id}/issues", response_model=list[IssueOut])
def list_issues(session: SessionDep, document_id: int) -> list[ParsingIssue]:
    """Return the parsing issues of a document."""
    _get_or_404(session, document_id)
    query = select(ParsingIssue).where(ParsingIssue.document_id == document_id).order_by(ParsingIssue.id)
    return list(session.scalars(query))


@router.get("/{document_id}/profile", response_model=ProfileOut)
def get_profile(session: SessionDep, document_id: int) -> ProfileOut:
    """Return the agent's parsing profile and the evidence for the metadata card."""
    document = _get_or_404(session, document_id)
    return ProfileOut(
        parsing_profile=json.loads(document.parsing_profile) if document.parsing_profile else None,
        metadata_evidence=json.loads(document.metadata_evidence),
        file_metadata=json.loads(document.file_metadata),
    )


@router.get("/{document_id}/file")
def download_document(session: SessionDep, document_id: int) -> Response:
    """Return the original file as uploaded."""
    document = _get_or_404(session, document_id)
    stored = session.get(DocumentFile, document_id)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл документа не найден")
    return Response(
        content=stored.content,
        media_type=MEDIA_TYPES[DocFormat(document.source_format)],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.file_name)}"},
    )
