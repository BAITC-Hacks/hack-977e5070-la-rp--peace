"""Upload, inspect and delete source documents."""

from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from la_rp_peace.api.deps import SessionDep, SettingsDep
from la_rp_peace.api.schemas import ClauseOut, DocumentOut, DocumentPatch
from la_rp_peace.enums import DocSet
from la_rp_peace.ingestion.service import MEDIA_TYPES, DocumentParseError, UnsupportedFormatError, parse_upload
from la_rp_peace.ingestion.types import ParsedDocument
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import Clause, Document

log = get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_or_404(session: Session, document_id: str) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return document


def _to_model(filename: str, doc_set: DocSet, data: bytes, parsed: ParsedDocument) -> Document:
    document = Document(
        id=str(uuid4()),
        filename=filename,
        doc_set=doc_set,
        doc_type=parsed.doc_type,
        format=parsed.format,
        title=parsed.title,
        size=len(data),
        clause_count=len(parsed.clauses),
        content=data,
    )
    ids = [str(uuid4()) for _ in parsed.clauses]
    document.clauses = [
        Clause(
            id=ids[position],
            parent_id=None if clause.parent is None else ids[clause.parent],
            position=position,
            kind=clause.kind,
            number=clause.number,
            anchor=clause.anchor,
            text=clause.text,
            paragraph_index=clause.location.paragraph_index,
            page=clause.location.page,
            sheet=clause.location.sheet,
            row=clause.location.row,
        )
        for position, clause in enumerate(parsed.clauses)
    ]
    return document


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentOut)
def upload_document(
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    doc_set: Annotated[DocSet, Form(alias="set")],
) -> Document:
    """Parse an uploaded .docx/.pdf/.xlsx file and store it with its clauses."""
    filename = file.filename or "document"
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Файл больше {settings.max_upload_mb} МБ")
    try:
        parsed = parse_upload(filename, data)
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    document = _to_model(filename, doc_set, data, parsed)
    session.add(document)
    session.commit()
    log.info("document_stored", document_id=document.id, filename=filename, doc_set=doc_set)
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(session: SessionDep, doc_set: Annotated[DocSet | None, Query(alias="set")] = None) -> list[Document]:
    """List uploaded documents, newest first, optionally filtered by set."""
    query = select(Document).order_by(Document.created_at.desc())
    if doc_set is not None:
        query = query.where(Document.doc_set == doc_set)
    return list(session.scalars(query))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(session: SessionDep, document_id: str) -> Document:
    """Return one document's metadata."""
    return _get_or_404(session, document_id)


@router.get("/{document_id}/clauses", response_model=list[ClauseOut])
def list_clauses(session: SessionDep, document_id: str) -> list[Clause]:
    """Return the document's clauses in reading order."""
    _get_or_404(session, document_id)
    query = select(Clause).where(Clause.document_id == document_id).order_by(Clause.position)
    return list(session.scalars(query))


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(session: SessionDep, document_id: str, patch: DocumentPatch) -> Document:
    """Override the detected document type."""
    document = _get_or_404(session, document_id)
    document.doc_type = patch.doc_type
    session.commit()
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(session: SessionDep, document_id: str) -> None:
    """Delete a document together with its clauses."""
    session.delete(_get_or_404(session, document_id))
    session.commit()


@router.get("/{document_id}/file")
def download_document(session: SessionDep, document_id: str) -> Response:
    """Return the original file as uploaded."""
    document = session.scalars(
        select(Document).where(Document.id == document_id).options(undefer(Document.content)),
    ).one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    disposition = f"attachment; filename*=UTF-8''{quote(document.filename)}"
    return Response(
        content=document.content,
        media_type=MEDIA_TYPES[document.format],
        headers={"Content-Disposition": disposition},
    )
