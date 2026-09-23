"""Register uploads and parse them in the background (methodology §0–§8 end to end).

Registration stores the file and a ``pending`` document in the request. A worker thread then
extracts the text, runs the profiling analysis and writes text, card, tree, issues and final
status in one transaction. Any failure leaves the document in ``needs_review`` with a
blocking issue — never silently ``pending``.
"""

import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.enums import DocSet, IssueType, ParseStatus
from la_rp_peace.ingestion.analysis import AnalysisResult, analyse
from la_rp_peace.ingestion.extract import ExtractionError, detect_format, extract
from la_rp_peace.ingestion.extract.types import Extraction
from la_rp_peace.ingestion.profiler import Profiler, ProfilerError
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import Document, DocumentFile, DocumentNode, ParsingIssue

log = get_logger(__name__)


def register(session: Session, filename: str, data: bytes, doc_set: DocSet) -> Document:
    """Store an upload as a pending document.

    Args:
        session: Database session.
        filename: Original file name.
        data: Raw file bytes.
        doc_set: Side of the comparison.

    Returns:
        The committed document.

    Raises:
        UnsupportedFormatError: If the file is not .docx, .pdf or .xlsx.
    """
    doc_format = detect_format(filename, data)
    document = Document(
        file_name=filename,
        source_format=doc_format.value,
        file_size_bytes=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(),
        doc_set=doc_set.value,
        parse_status=ParseStatus.PENDING.value,
    )
    session.add(document)
    session.flush()
    session.add(DocumentFile(document_id=document.id, content=data))
    session.commit()
    log.info("document_registered", document_id=document.id, filename=filename, doc_set=doc_set)
    return document


def _fail(session: Session, document: Document, message: str) -> None:
    session.rollback()
    document.parse_status = ParseStatus.NEEDS_REVIEW.value
    session.add(ParsingIssue(document_id=document.id, issue_type=IssueType.OTHER.value, message=message, is_blocking=1))
    session.commit()
    log.warning("document_parse_failed", document_id=document.id, reason=message)


def _save_card(document: Document, extraction: Extraction, result: AnalysisResult) -> None:
    document.original_text = extraction.original_text
    document.source_map = json.dumps([span.as_json() for span in extraction.source_map], ensure_ascii=False)
    document.file_metadata = json.dumps(extraction.file_metadata, ensure_ascii=False)
    document.parsing_profile = json.dumps(result.profile, ensure_ascii=False) if result.profile else None
    if result.metadata is not None:
        for name, value in result.metadata.card.items():
            setattr(document, name, value)
        document.metadata_evidence = json.dumps(result.metadata.evidence, ensure_ascii=False)
    document.parse_status = result.status.value


def _save_tree(session: Session, document_id: int, result: AnalysisResult) -> None:
    ids: list[int] = []
    for node in result.nodes:
        row = DocumentNode(
            document_id=document_id,
            parent_id=None if node.parent is None else ids[node.parent],
            position=node.position,
            node_type=node.node_type.value,
            marker=node.marker,
            text=node.text,
            source_start=node.range_start,
            source_end=node.range_end,
        )
        session.add(row)
        session.flush()
        ids.append(row.id)
    for issue in result.issues:
        session.add(
            ParsingIssue(
                document_id=document_id,
                node_id=None if issue.node is None else ids[issue.node],
                issue_type=issue.issue_type.value,
                message=issue.message,
                is_blocking=int(issue.is_blocking),
            ),
        )


def parse_document(session: Session, document_id: int, profiler: Profiler, max_chars: int, retries: int) -> None:
    """Extract, profile and store one registered document.

    Args:
        session: Database session.
        document_id: Document to parse.
        profiler: The model client.
        max_chars: Size limit of the text shown to the model.
        retries: Corrected answers to request after the first.
    """
    document = session.get(Document, document_id)
    stored = session.get(DocumentFile, document_id)
    if document is None or stored is None:
        log.warning("document_missing", document_id=document_id)
        return
    try:
        from_format = detect_format(document.file_name, stored.content)
        extraction = extract(from_format, stored.content)
        result = analyse(extraction, profiler, max_chars, retries)
    except (ExtractionError, ProfilerError) as exc:
        _fail(session, document, str(exc))
        return
    _save_card(document, extraction, result)
    _save_tree(session, document.id, result)
    session.commit()
    log.info("document_parsed", document_id=document_id, status=result.status, nodes=len(result.nodes))


class ParsingQueue:
    """Runs ``parse_document`` on worker threads, one session per job."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        profiler: Profiler,
        max_chars: int,
        retries: int,
        workers: int,
    ) -> None:
        """Start the worker pool."""
        self._session_factory = session_factory
        self._profiler = profiler
        self._max_chars = max_chars
        self._retries = retries
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="parser")

    def submit(self, document_id: int) -> Future[None]:
        """Queue a document for parsing."""
        return self._executor.submit(self._run, document_id)

    def _run(self, document_id: int) -> None:
        with self._session_factory() as session:
            try:
                parse_document(session, document_id, self._profiler, self._max_chars, self._retries)
            except Exception as exc:
                log.exception("document_parse_crashed", document_id=document_id, error=str(exc))
                document = session.get(Document, document_id)
                if document is not None:
                    _fail(session, document, f"Внутренняя ошибка разбора: {exc}")

    def requeue_pending(self) -> int:
        """Queue documents left pending by a previous run; return how many."""
        with self._session_factory() as session:
            pending = list(
                session.scalars(select(Document.id).where(Document.parse_status == ParseStatus.PENDING.value))
            )
        for document_id in pending:
            self.submit(document_id)
        return len(pending)

    def shutdown(self) -> None:
        """Stop accepting work and wait for running jobs."""
        self._executor.shutdown(wait=True, cancel_futures=True)
