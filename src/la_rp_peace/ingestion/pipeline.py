"""Register uploads and run the document pipeline in the background.

Registration stores the file and a ``pending`` document in the request. A worker thread then
runs stage 1 (extraction, profiling analysis; text, card, tree, issues and final status in
one transaction) and, when stage 1 produced a tree, the later stages in order (entities,
activities, …). Any stage 1 failure leaves the document in ``needs_review`` with a blocking
issue — never silently ``pending``. Later stages own their status columns: a stage that
raises is marked failed through its ``fail`` hook and stops the chain, because later stages
build on its results.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.enums import DocSet, IssueType, ParseStatus
from la_rp_peace.ingestion.analysis import AnalysisResult, analyse
from la_rp_peace.ingestion.extract import ExtractionError, detect_format, extract
from la_rp_peace.ingestion.extract.types import Extraction
from la_rp_peace.llm import ChatModel, ChatModelError
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import Document, DocumentFile, DocumentNode, ParsingIssue

log = get_logger(__name__)

# Analysis stages that only read the results of earlier stages: run side by side.
CONCURRENT_STAGES = frozenset({"collisions", "cascade"})


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


def parse_document(session: Session, document_id: int, profiler: ChatModel, max_chars: int, retries: int) -> None:
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
    except (ExtractionError, ChatModelError) as exc:
        _fail(session, document, str(exc))
        return
    _save_card(document, extraction, result)
    _save_tree(session, document.id, result)
    session.commit()
    log.info("document_parsed", document_id=document_id, status=result.status, nodes=len(result.nodes))


class PostParseStage(Protocol):
    """A pipeline stage that runs on a document after stage 1 built its tree."""

    name: str

    def run(self, session: Session, document_id: int) -> None:
        """Process the document and commit the stage's results and status."""
        ...

    def fail(self, session: Session, document_id: int, message: str) -> None:
        """Record that the stage crashed for the document."""
        ...


def _has_tree(session: Session, document_id: int) -> bool:
    count = session.scalar(select(func.count()).where(DocumentNode.document_id == document_id))
    return bool(count)


class ParsingQueue:
    """Runs the pipeline on worker threads, one session per job."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        profiler: ChatModel,
        max_chars: int,
        retries: int,
        workers: int,
        stages: Sequence[PostParseStage] = (),
    ) -> None:
        """Start the worker pool.

        Args:
            session_factory: Sessions for the worker threads.
            profiler: Chat model for stage 1.
            max_chars: Size limit of the text shown to the model in stage 1.
            retries: Corrected stage 1 answers to request after the first.
            workers: Documents processed in parallel.
            stages: Stages run in order after stage 1, e.g. entities then activities.
        """
        self._session_factory = session_factory
        self._profiler = profiler
        self._max_chars = max_chars
        self._retries = retries
        self._stages = tuple(stages)
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="parser")

    def submit(self, document_id: int) -> Future[None]:
        """Queue a document for the whole pipeline."""
        return self._executor.submit(self._run, document_id)

    def submit_call(self, call: "Callable[[], None]") -> Future[None]:
        """Run any background job (e.g. a comparison) on the pipeline's workers."""
        return self._executor.submit(call)

    def submit_from(self, document_id: int, stage_name: str) -> Future[None]:
        """Queue a re-run of the pipeline from a post-parse stage onwards.

        Raises:
            KeyError: If no stage has that name.
        """
        names = [stage.name for stage in self._stages]
        start = names.index(stage_name) if stage_name in names else None
        if start is None:
            raise KeyError(stage_name)
        return self._executor.submit(self._run_stages, document_id, start)

    def _run(self, document_id: int) -> None:
        with self._session_factory() as session:
            try:
                parse_document(session, document_id, self._profiler, self._max_chars, self._retries)
            except Exception as exc:
                log.exception("document_parse_crashed", document_id=document_id, error=str(exc))
                document = session.get(Document, document_id)
                if document is not None:
                    _fail(session, document, f"Внутренняя ошибка разбора: {exc}")
                return
        self._run_stages(document_id, 0)

    def _run_stages(self, document_id: int, start: int) -> None:
        stages = self._stages[start:]
        concurrent = [stage for stage in stages if stage.name in CONCURRENT_STAGES]
        for stage in [stage for stage in stages if stage.name not in CONCURRENT_STAGES]:
            if not self._run_stage(stage, document_id):
                return
        with ThreadPoolExecutor(max_workers=max(1, len(concurrent)), thread_name_prefix="analysis") as pool:
            list(pool.map(lambda stage: self._run_stage(stage, document_id), concurrent))

    def _run_stage(self, stage: PostParseStage, document_id: int) -> bool:
        """Run one stage in its own session; False stops the chain."""
        with self._session_factory() as session:
            if not _has_tree(session, document_id):
                log.info("stage_skipped_without_tree", document_id=document_id, stage=stage.name)
                return False
            try:
                stage.run(session, document_id)
            except Exception as exc:
                log.exception("stage_crashed", document_id=document_id, stage=stage.name, error=str(exc))
                session.rollback()
                stage.fail(session, document_id, f"Внутренняя ошибка этапа {stage.name}: {exc}")
                return False
        return True

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
