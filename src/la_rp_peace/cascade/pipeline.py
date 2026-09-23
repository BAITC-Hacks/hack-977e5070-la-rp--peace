"""Stage 4.2 as a post-parse pipeline stage: groups → embeddings → best candidate → LLM → checks → save.

The stage reads the entities (stage 2) and activity records (stage 3) from the database only.
It runs when both stages finished (``done`` or ``needs_review``); otherwise the document stays
``not_started`` and stale 4.2 rows are removed. The result replaces the previous run in one
transaction; the document is ``needs_review`` whenever any finding (anomaly, unresolved link or
link to clarify) is present, else ``done``.
"""

import json
from collections import defaultdict
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.cascade.findings import find
from la_rp_peace.cascade.groups import Structure, entity_of, load_structure
from la_rp_peace.cascade.links import LinkResult, decide, verify
from la_rp_peace.cascade.matching import Choice, choose
from la_rp_peace.cascade.prompt import Citation
from la_rp_peace.cascade.store import clear_cascade, save_cascade
from la_rp_peace.embeddings import ActivityText, Embedder, activity_text, cosine_matrix, embed_texts
from la_rp_peace.enums import ActivitiesStatus, AnalysisStatus, EntitiesStatus
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import ActivityRecord, ActivitySource, Document, DocumentNode, Entity
from la_rp_peace.navigation import describe

log = get_logger(__name__)

READY_ENTITIES = frozenset({EntitiesStatus.DONE.value, EntitiesStatus.NEEDS_REVIEW.value})
READY_ACTIVITIES = frozenset({ActivitiesStatus.DONE.value, ActivitiesStatus.NEEDS_REVIEW.value})


def embedding_text(record: ActivityRecord, entity: Entity) -> str:
    """Render the embedded text of a function record (``TEXT_FORMAT``), with its object and conditions."""
    return activity_text(
        ActivityText(
            entity=entity.name,
            category=entity.category,
            record_type=record.record_type,
            formulation=record.formulation,
            participation=record.participation,
            participants=record.participant_designation,
            condition=record.condition,
            deadline=record.deadline,
            periodicity=record.periodicity,
        ),
    )


def load_citations(session: Session, document: Document, record_ids: Collection[int]) -> dict[int, list[Citation]]:
    """Verbatim stage 3 quotes of the given records with the path of their nodes."""
    if not record_ids:
        return {}
    nodes = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document.id)).all()
    places = describe(nodes, json.loads(document.source_map))
    sources = session.scalars(
        select(ActivitySource)
        .where(ActivitySource.document_id == document.id, ActivitySource.record_id.in_(record_ids))
        .order_by(ActivitySource.id),
    )
    citations: defaultdict[int, list[Citation]] = defaultdict(list)
    for source in sources:
        citations[source.record_id].append(Citation(source.node_id, places[source.node_id].path, source.quote))
    return dict(citations)


class CascadeStage:
    """Stage 4.2 of the pipeline: links between parent and child functions, and their anomalies."""

    name = "cascade"

    def __init__(self, model: ChatModel, embedder: Embedder, retries: int) -> None:
        """Configure the stage.

        Args:
            model: Chat model for the verification questions.
            embedder: Embedding model; the thresholds assume the configured one.
            retries: Corrected answers to request per verification batch after the first.
        """
        self._model = model
        self._embedder = embedder
        self._retries = retries

    def run(self, session: Session, document_id: int) -> None:
        """Build, verify, check and store the document's cascade, committing status and results."""
        document = session.get(Document, document_id)
        if document is None:
            log.warning("cascade_document_missing", document_id=document_id)
            return
        if document.entities_status not in READY_ENTITIES or document.activities_status not in READY_ACTIVITIES:
            clear_cascade(session, document_id)
            document.cascade_status = AnalysisStatus.NOT_STARTED.value
            session.commit()
            log.info(
                "cascade_skipped",
                document_id=document_id,
                entities_status=document.entities_status,
                activities_status=document.activities_status,
            )
            return
        document.cascade_status = AnalysisStatus.RUNNING.value
        session.commit()
        structure = load_structure(session, document_id)
        links = self._links(session, document, structure)
        findings = find(structure, links)
        save_cascade(session, document_id, structure, links, findings, self._embedder.model)
        status = AnalysisStatus.NEEDS_REVIEW if findings else AnalysisStatus.DONE
        document.cascade_status = status.value
        session.commit()
        log.info(
            "cascade_done",
            document_id=document_id,
            status=status,
            groups=len(structure.groups),
            links=len(links),
            findings=len(findings),
            excluded=len(structure.excluded),
        )

    def _choices(self, session: Session, structure: Structure) -> list[Choice]:
        compared = [group for group in structure.groups if group.parent_records and group.child_records]
        records = {record.id: record for group in compared for record in group.parent_records + group.child_records}
        order = list(records)
        texts = [embedding_text(records[rid], structure.entities[entity_of(records[rid])]) for rid in order]
        vectors = embed_texts(session, self._embedder, texts)
        rows = {record_id: row for row, record_id in enumerate(order)}
        choices: list[Choice] = []
        for group in structure.groups:
            if not group.parent_records or not group.child_records:
                # Without parent functions a child function has no candidate: no pair, nothing to embed.
                choices += [Choice(group, child, None, None) for child in group.child_records]
                continue
            left = vectors[[rows[record.id] for record in group.child_records]]
            right = vectors[[rows[record.id] for record in group.parent_records]]
            choices += choose(group, cosine_matrix(left, right))
        return choices

    def _links(self, session: Session, document: Document, structure: Structure) -> list[LinkResult]:
        choices = self._choices(session, structure)
        asked = [choice for choice in choices if choice.needs_question]
        parents = {record.id: record for group in structure.groups for record in group.parent_records}
        cited = {choice.child.id for choice in asked} | {c.parent_record_id for c in asked if c.parent_record_id}
        citations = load_citations(session, document, cited)
        outcomes = verify(
            self._model, asked, parents, structure.entities, citations, self._embedder.model, self._retries
        )
        return [decide(choice, outcomes) for choice in choices]

    def fail(self, session: Session, document_id: int, message: str) -> None:
        """Mark the stage failed for the document; the previous cascade rows are kept."""
        session.rollback()
        document = session.get(Document, document_id)
        if document is None:
            return
        document.cascade_status = AnalysisStatus.FAILED.value
        session.commit()
        log.warning("cascade_failed", document_id=document_id, reason=message)
