"""Run a stage 5.2 comparison in the background and store its report."""

import json
import time

from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.comparison.report import (
    Report,
    activity_findings,
    created_findings,
    duplication_findings,
    entity_findings,
    job_result,
)
from la_rp_peace.comparison.run import find_candidates, load_side, match_entities, verify
from la_rp_peace.embeddings import Embedder
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import Comparison, Document

log = get_logger(__name__)

# Stage statuses a document's chain ends in; the comparison reads their results only after them.
_FINISHED = frozenset({"done", "needs_review", "failed"})
_CHAIN = ("entities_status", "activities_status", "collisions_status", "cascade_status")
WAIT_SECONDS = 1800.0
POLL_SECONDS = 3.0


def _chain_finished(document: Document) -> bool:
    """Every stage has ended, or the chain stopped at a failed stage (later ones never start)."""
    if document.parse_status == "failed":
        return True
    statuses = [getattr(document, name) for name in _CHAIN]
    return "failed" in statuses or all(value in _FINISHED for value in statuses)


def wait_for_documents(factory: sessionmaker[Session], document_ids: list[int]) -> None:
    """Block until the stage chain of every document has finished; raise after WAIT_SECONDS."""
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        with factory() as session:
            waiting = [
                document_id
                for document_id in document_ids
                if (document := session.get(Document, document_id)) is not None and not _chain_finished(document)
            ]
        if not waiting:
            return
        if time.monotonic() > deadline:
            raise TimeoutError(f"Документы {waiting} не закончили обработку за {WAIT_SECONDS:.0f} с")
        time.sleep(POLL_SECONDS)


def run_comparison(session: Session, comparison_id: int, model: ChatModel, embedder: Embedder, retries: int) -> None:
    """Compute and store the report of one comparison (status running -> done/needs_review/failed)."""
    comparison = session.get(Comparison, comparison_id)
    if comparison is None:
        return
    comparison.status = "running"
    session.commit()
    before = load_side(session, "before", json.loads(comparison.before_ids))
    after = load_side(session, "after", json.loads(comparison.after_ids))
    report = Report()
    entity_findings(report, before, after, match_entities(session, embedder, before, after))
    items = find_candidates(session, embedder, before, after)
    session.commit()
    outcomes = verify(model, before, after, items, retries)
    matched_after = activity_findings(report, before, after, items, outcomes)
    created_findings(report, after, matched_after)
    duplication_findings(session, report, after)
    comparison.result = json.dumps(job_result(str(comparison_id), report, before, after), ensure_ascii=False)
    comparison.status = "needs_review" if report.errors else "done"
    session.commit()
    log.info("comparison_done", comparison_id=comparison_id, findings=len(report.findings), errors=report.errors)


def comparison_job(
    factory: sessionmaker[Session], comparison_id: int, model: ChatModel, embedder: Embedder, retries: int
) -> None:
    """Background entry point; any crash marks the comparison failed with the reason."""
    with factory() as session:
        try:
            comparison = session.get(Comparison, comparison_id)
            if comparison is None:
                return
            wait_for_documents(factory, [*json.loads(comparison.before_ids), *json.loads(comparison.after_ids)])
            session.expire_all()
            run_comparison(session, comparison_id, model, embedder, retries)
        except Exception as exc:
            log.exception("comparison_failed", comparison_id=comparison_id, error=str(exc))
            session.rollback()
            comparison = session.get(Comparison, comparison_id)
            if comparison is not None:
                comparison.status = "failed"
                comparison.error = str(exc)
                session.commit()
