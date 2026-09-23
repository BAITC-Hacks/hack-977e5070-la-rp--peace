"""Stage 4.2 results: groups with links, chains, findings with resolved sources, the report, re-runs."""

import json
from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.api.deps import SessionDep
from la_rp_peace.cascade.chains import build_chains
from la_rp_peace.cascade.findings import LABELS
from la_rp_peace.cascade.groups import FUNCTION_TYPES
from la_rp_peace.cascade.matching import AUTO_ABOVE, VERIFY_ABOVE
from la_rp_peace.cascade.pipeline import CascadeStage
from la_rp_peace.enums import (
    ActivityType,
    AnalysisStatus,
    CascadeDecision,
    CascadeFindingKind,
    CascadeFindingReason,
    CascadeLinkStatus,
    CascadeVerdict,
    EntityCategory,
)
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.models import (
    ActivityRecord,
    ActivitySource,
    CascadeFinding,
    CascadeGroup,
    CascadeLink,
    Document,
    DocumentNode,
    Entity,
)
from la_rp_peace.navigation import describe

router = APIRouter(prefix="/api/documents", tags=["cascade"])


class CascadeSourceOut(BaseModel):
    """A verbatim stage 3 quote with where to find it; ``start``/``end`` index the node's own text."""

    node_id: int
    path: str
    location: dict[str, Any]
    quote: str
    start: int
    end: int
    supports: list[str]


class CascadeEntityOut(BaseModel):
    """An organisational object."""

    id: int
    name: str
    category: EntityCategory


class CascadeRecordOut(BaseModel):
    """A task, function or duty with its sources."""

    id: int
    entity_id: int | None
    entity_name: str | None
    record_type: ActivityType
    formulation: str
    condition: str | None
    deadline: str | None
    periodicity: str | None
    sources: list[CascadeSourceOut]


class CascadeLinkOut(BaseModel):
    """The decision for one child function; ``best_similarity`` is the raw cosine."""

    id: int
    child_record_id: int
    child_entity_id: int
    parent_record_id: int | None
    best_similarity: float | None
    decision: CascadeDecision
    verdict: CascadeVerdict | None
    explanation: str | None
    status: CascadeLinkStatus
    error: str | None
    attempts: int
    tied_record_ids: list[int]
    embedding_model: str
    metric: str
    text_format: str


class CascadeGroupOut(BaseModel):
    """Object N, its direct executors and the links between their functions."""

    id: int
    entity: CascadeEntityOut
    children: list[CascadeEntityOut]
    uncertain_entity_ids: list[int]
    parent_functions: list[CascadeRecordOut]
    child_functions: list[CascadeRecordOut]
    links: list[CascadeLinkOut]


class CascadeFindingOut(BaseModel):
    """A sign for review: «Исполнитель не найден», «Основание не найдено» or «Требует уточнения»."""

    id: int
    kind: CascadeFindingKind
    label: str
    reason: CascadeFindingReason
    final: bool
    message: str
    group_id: int | None
    link_id: int | None
    entity: CascadeEntityOut
    record: CascadeRecordOut


class CascadeOut(BaseModel):
    """The cascade of a document."""

    document_id: int
    cascade_status: AnalysisStatus
    auto_accept_above: float
    verify_above: float
    groups: list[CascadeGroupOut]
    chains: list[list[CascadeRecordOut]]
    findings: list[CascadeFindingOut]


class CascadeReportOut(BaseModel):
    """Counts of a document's cascade run."""

    document_id: int
    cascade_status: AnalysisStatus
    groups: int
    links: int
    links_by_decision: dict[str, int]
    links_by_verdict: dict[str, int]
    links_by_status: dict[str, int]
    findings_by_kind: dict[str, int]
    findings_by_reason: dict[str, int]
    final_anomalies: int
    excluded_record_ids: list[int]


class CascadeRunOut(BaseModel):
    """A queued stage 4.2 run."""

    document_id: int
    cascade_status: AnalysisStatus


class _View:
    """Entities and function records of one document, rendered for the responses."""

    def __init__(self, session: Session, document: Document) -> None:
        document_id = document.id
        self.entities = {e.id: e for e in session.scalars(select(Entity).where(Entity.document_id == document_id))}
        self.records = {
            record.id: record
            for record in session.scalars(select(ActivityRecord).where(ActivityRecord.document_id == document_id))
        }
        nodes = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document_id)).all()
        places = describe(nodes, json.loads(document.source_map))
        self.sources: defaultdict[int, list[CascadeSourceOut]] = defaultdict(list)
        query = select(ActivitySource).where(ActivitySource.document_id == document_id).order_by(ActivitySource.id)
        for source in session.scalars(query):
            place = places[source.node_id]
            self.sources[source.record_id].append(
                CascadeSourceOut(
                    node_id=source.node_id,
                    path=place.path,
                    location=place.location,
                    quote=source.quote,
                    start=source.quote_start,
                    end=source.quote_end,
                    supports=json.loads(source.supports),
                ),
            )

    def entity(self, entity_id: int) -> CascadeEntityOut:
        entity = self.entities[entity_id]
        return CascadeEntityOut(id=entity.id, name=entity.name, category=EntityCategory(entity.category))

    def record(self, record_id: int) -> CascadeRecordOut:
        record = self.records[record_id]
        entity = self.entities.get(record.entity_id) if record.entity_id is not None else None
        return CascadeRecordOut(
            id=record.id,
            entity_id=record.entity_id,
            entity_name=entity.name if entity is not None else None,
            record_type=ActivityType(record.record_type),
            formulation=record.formulation,
            condition=record.condition,
            deadline=record.deadline,
            periodicity=record.periodicity,
            sources=self.sources[record.id],
        )


def _document_or_404(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return document


def _link_out(link: CascadeLink) -> CascadeLinkOut:
    return CascadeLinkOut(
        id=link.id,
        child_record_id=link.child_record_id,
        child_entity_id=link.child_entity_id,
        parent_record_id=link.parent_record_id,
        best_similarity=link.best_similarity,
        decision=CascadeDecision(link.decision),
        verdict=CascadeVerdict(link.verdict) if link.verdict is not None else None,
        explanation=link.explanation,
        status=CascadeLinkStatus(link.status),
        error=link.error,
        attempts=link.attempts,
        tied_record_ids=json.loads(link.tied_record_ids),
        embedding_model=link.embedding_model,
        metric=link.metric,
        text_format=link.text_format,
    )


def _group_out(group: CascadeGroup, links: list[CascadeLink], view: _View) -> CascadeGroupOut:
    return CascadeGroupOut(
        id=group.id,
        entity=view.entity(group.entity_id),
        children=[view.entity(child) for child in json.loads(group.child_entity_ids)],
        uncertain_entity_ids=json.loads(group.uncertain_entity_ids),
        parent_functions=[view.record(record) for record in json.loads(group.parent_record_ids)],
        child_functions=[view.record(record) for record in json.loads(group.child_record_ids)],
        links=[_link_out(link) for link in links],
    )


def _finding_out(finding: CascadeFinding, view: _View) -> CascadeFindingOut:
    kind = CascadeFindingKind(finding.kind)
    return CascadeFindingOut(
        id=finding.id,
        kind=kind,
        label=LABELS[kind],
        reason=CascadeFindingReason(finding.reason),
        final=bool(finding.final),
        message=finding.message,
        group_id=finding.group_id,
        link_id=finding.link_id,
        entity=view.entity(finding.entity_id),
        record=view.record(finding.record_id),
    )


def _rows[T: (CascadeGroup, CascadeLink, CascadeFinding)](
    session: Session, model: type[T], document_id: int
) -> list[T]:
    return list(session.scalars(select(model).where(model.document_id == document_id).order_by(model.id)))


@router.get("/{document_id}/cascade", response_model=CascadeOut)
def get_cascade(session: SessionDep, document_id: int) -> CascadeOut:
    """Return the groups with their links, the chains of accepted links and the findings."""
    document = _document_or_404(session, document_id)
    view = _View(session, document)
    links = _rows(session, CascadeLink, document_id)
    by_group: defaultdict[int, list[CascadeLink]] = defaultdict(list)
    for link in links:
        by_group[link.group_id].append(link)
    accepted = [
        (link.parent_record_id, link.child_record_id)
        for link in links
        if link.status == CascadeLinkStatus.ACCEPTED.value and link.parent_record_id is not None
    ]
    return CascadeOut(
        document_id=document_id,
        cascade_status=AnalysisStatus(document.cascade_status),
        auto_accept_above=AUTO_ABOVE,
        verify_above=VERIFY_ABOVE,
        groups=[_group_out(group, by_group[group.id], view) for group in _rows(session, CascadeGroup, document_id)],
        chains=[[view.record(record) for record in chain] for chain in build_chains(accepted)],
        findings=[_finding_out(finding, view) for finding in _rows(session, CascadeFinding, document_id)],
    )


@router.get("/{document_id}/cascade-report", response_model=CascadeReportOut)
def cascade_report(session: SessionDep, document_id: int) -> CascadeReportOut:
    """Return the counts of the latest cascade run and the function records it had to leave out."""
    document = _document_or_404(session, document_id)
    links = _rows(session, CascadeLink, document_id)
    findings = _rows(session, CascadeFinding, document_id)
    excluded = session.scalars(
        select(ActivityRecord.id)
        .where(
            ActivityRecord.document_id == document_id,
            ActivityRecord.entity_id.is_(None),
            ActivityRecord.record_type.in_(FUNCTION_TYPES),
        )
        .order_by(ActivityRecord.id),
    )
    return CascadeReportOut(
        document_id=document_id,
        cascade_status=AnalysisStatus(document.cascade_status),
        groups=len(_rows(session, CascadeGroup, document_id)),
        links=len(links),
        links_by_decision=dict(Counter(link.decision for link in links)),
        links_by_verdict=dict(Counter(link.verdict for link in links if link.verdict is not None)),
        links_by_status=dict(Counter(link.status for link in links)),
        findings_by_kind=dict(Counter(finding.kind for finding in findings)),
        findings_by_reason=dict(Counter(finding.reason for finding in findings)),
        final_anomalies=sum(finding.final for finding in findings),
        excluded_record_ids=list(excluded),
    )


@router.post("/{document_id}/cascade", status_code=status.HTTP_202_ACCEPTED, response_model=CascadeRunOut)
def run_cascade(request: Request, session: SessionDep, document_id: int) -> CascadeRunOut:
    """Queue stage 4.2 again; poll the report for ``cascade_status``."""
    document = _document_or_404(session, document_id)
    queue: ParsingQueue | None = request.app.state.parsing_queue
    if queue is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Каскад недоступен: не заданы OPENAI_API_KEY и OPENAI_MODEL",
        )
    previous = document.cascade_status
    # Mark the run before queueing it, so a client polling right away never sees the previous outcome.
    document.cascade_status = AnalysisStatus.RUNNING.value
    session.commit()
    try:
        queue.submit_from(document_id, CascadeStage.name)
    except KeyError:
        document.cascade_status = previous
        session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Каскад недоступен: не настроена модель эмбеддингов (нужен OPENAI_API_KEY)",
        ) from None
    return CascadeRunOut(document_id=document_id, cascade_status=AnalysisStatus.RUNNING)
