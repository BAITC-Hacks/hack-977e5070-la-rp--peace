"""Stage 4.1 results: verified pairs of assignments grouped by verdict, the run report, re-runs."""

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.api.deps import SessionDep
from la_rp_peace.collisions.pipeline import CollisionStage
from la_rp_peace.collisions.sides import Party, parties
from la_rp_peace.enums import (
    ActivityType,
    AnalysisStatus,
    CollisionPairStatus,
    CollisionSideKind,
    CollisionVerdict,
    Participation,
    SearchBasis,
)
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.models import (
    ActivityRecord,
    ActivitySource,
    CollisionPair,
    CollisionRun,
    CollisionSource,
    CollisionView,
    CollisionViewRecord,
    Document,
    DocumentNode,
    Entity,
)
from la_rp_peace.navigation import NodePlace, describe

router = APIRouter(prefix="/api/documents", tags=["collisions"])

_UNAVAILABLE = "Поиск коллизий недоступен: не заданы OPENAI_API_KEY и OPENAI_MODEL"


class CollisionSourceOut(BaseModel):
    """A verbatim quote with where to find it; ``start``/``end`` index the node's own text."""

    node_id: int
    path: str
    location: dict[str, Any]
    quote: str
    start: int
    end: int
    supports: list[str]


class PartyOut(BaseModel):
    """A participant of a side with its category and resolved parent."""

    entity_id: int
    name: str
    entity_type: str
    category: str
    parent_id: int | None
    parent_name: str | None


class CollisionSideOut(BaseModel):
    """One side: a stage 3 record, or a consolidated joint assignment (``view_id``)."""

    kind: CollisionSideKind
    record_id: int | None
    view_id: int | None
    record_ids: list[int]
    participants: list[PartyOut]
    record_type: ActivityType
    formulation: str
    specificity: list[str]
    participation: Participation
    participant_designation: str
    conditions: list[str]
    deadlines: list[str]
    periodicities: list[str]
    sources: list[CollisionSourceOut]


class CollisionPairOut(BaseModel):
    """A pair above the threshold: search bases, raw similarity, verdict or error, evidence."""

    id: int
    pair_key: str
    bases: list[SearchBasis]
    basis_details: list[dict[str, Any]]
    similarity: float
    embedding_model: str
    metric: str
    text_format: str
    status: CollisionPairStatus
    verdict: CollisionVerdict | None
    explanation: str | None
    error: str | None
    attempts: int
    side_a: CollisionSideOut
    side_b: CollisionSideOut
    sources: list[CollisionSourceOut]


class CollisionsOut(BaseModel):
    """Pairs of a document, kept apart: possible collisions, explained matches, missing data, errors."""

    document_id: int
    collisions_status: AnalysisStatus
    collision: list[CollisionPairOut]
    no_collision: list[CollisionPairOut]
    insufficient_data: list[CollisionPairOut]
    errors: list[CollisionPairOut]


class CollisionReportOut(BaseModel):
    """Coverage of the latest run; the run fields are None before the first finished run."""

    document_id: int
    collisions_status: AnalysisStatus
    threshold: float | None
    embedding_model: str | None
    metric: str | None
    text_format: str | None
    compared_records: int
    compared_views: int
    context_records: int
    local_pairs: int
    local_above: int
    category_pairs: int
    category_above: int
    pairs_sent: int
    verdicts: dict[CollisionVerdict, int]
    errors: int
    created_at: str | None


class CollisionRunOut(BaseModel):
    """A queued stage 4.1 run."""

    document_id: int
    collisions_status: AnalysisStatus


class _Lookup:
    """Rows of one document needed to describe pairs."""

    def __init__(self, session: Session, document: Document) -> None:
        document_id = document.id
        nodes = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document_id)).all()
        self.places: dict[int, NodePlace] = describe(nodes, json.loads(document.source_map))
        self.parties: dict[int, Party] = parties(
            session.scalars(select(Entity).where(Entity.document_id == document_id)).all(),
        )
        self.records = {
            row.id: row
            for row in session.scalars(select(ActivityRecord).where(ActivityRecord.document_id == document_id))
        }
        self.sources: defaultdict[int, list[ActivitySource]] = defaultdict(list)
        query = select(ActivitySource).where(ActivitySource.document_id == document_id).order_by(ActivitySource.id)
        for source in session.scalars(query):
            self.sources[source.record_id].append(source)
        self.views = {
            row.id: row
            for row in session.scalars(select(CollisionView).where(CollisionView.document_id == document_id))
        }
        self.members: defaultdict[int, list[int]] = defaultdict(list)
        for member in session.scalars(
            select(CollisionViewRecord)
            .where(CollisionViewRecord.document_id == document_id)
            .order_by(CollisionViewRecord.record_id),
        ):
            self.members[member.view_id].append(member.record_id)

    def source(self, node_id: int, quote: str, span: tuple[int, int], supports: str) -> CollisionSourceOut:
        place = self.places[node_id]
        return CollisionSourceOut(
            node_id=node_id,
            path=place.path,
            location=place.location,
            quote=quote,
            start=span[0],
            end=span[1],
            supports=json.loads(supports),
        )


def _document_or_404(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return document


def _distinct(values: Sequence[str | None]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _party_out(party: Party) -> PartyOut:
    return PartyOut(
        entity_id=party.entity_id,
        name=party.name,
        entity_type=party.entity_type,
        category=party.category,
        parent_id=party.parent_id,
        parent_name=party.parent_name,
    )


def _side_out(lookup: _Lookup, kind: str, record_id: int | None, view_id: int | None) -> CollisionSideOut:
    record_ids = [record_id] if record_id is not None else lookup.members[view_id or 0]
    records = [lookup.records[rid] for rid in record_ids]
    first = records[0]
    entity_ids = [record.entity_id for record in records if record.entity_id is not None]
    return CollisionSideOut(
        kind=CollisionSideKind(kind),
        record_id=record_id,
        view_id=view_id,
        record_ids=record_ids,
        participants=[_party_out(lookup.parties[entity_id]) for entity_id in entity_ids],
        record_type=ActivityType(first.record_type),
        formulation=lookup.views[view_id].formulation if view_id is not None else first.formulation,
        specificity=_distinct([record.specificity for record in records]),
        participation=Participation(first.participation),
        participant_designation=first.participant_designation,
        conditions=_distinct([record.condition for record in records]),
        deadlines=_distinct([record.deadline for record in records]),
        periodicities=_distinct([record.periodicity for record in records]),
        sources=[
            lookup.source(source.node_id, source.quote, (source.quote_start, source.quote_end), source.supports)
            for rid in record_ids
            for source in lookup.sources[rid]
        ],
    )


def _pair_out(pair: CollisionPair, lookup: _Lookup, sources: list[CollisionSourceOut]) -> CollisionPairOut:
    return CollisionPairOut(
        id=pair.id,
        pair_key=pair.pair_key,
        bases=[SearchBasis(value) for value in json.loads(pair.bases)],
        basis_details=json.loads(pair.basis_details),
        similarity=pair.similarity,
        embedding_model=pair.embedding_model,
        metric=pair.metric,
        text_format=pair.text_format,
        status=CollisionPairStatus(pair.status),
        verdict=CollisionVerdict(pair.verdict) if pair.verdict else None,
        explanation=pair.explanation,
        error=pair.error,
        attempts=pair.attempts,
        side_a=_side_out(lookup, pair.side_a_kind, pair.side_a_record_id, pair.side_a_view_id),
        side_b=_side_out(lookup, pair.side_b_kind, pair.side_b_record_id, pair.side_b_view_id),
        sources=sources,
    )


@router.get("/{document_id}/collisions", response_model=CollisionsOut)
def list_collisions(session: SessionDep, document_id: int) -> CollisionsOut:
    """Return the document's verified pairs grouped by verdict, errors apart, most similar first."""
    document = _document_or_404(session, document_id)
    lookup = _Lookup(session, document)
    evidence: defaultdict[int, list[CollisionSourceOut]] = defaultdict(list)
    query = select(CollisionSource).where(CollisionSource.document_id == document_id).order_by(CollisionSource.id)
    for row in session.scalars(query):
        evidence[row.pair_id].append(
            lookup.source(row.node_id, row.quote, (row.quote_start, row.quote_end), row.supports)
        )
    groups: defaultdict[str, list[CollisionPairOut]] = defaultdict(list)
    pairs = session.scalars(
        select(CollisionPair)
        .where(CollisionPair.document_id == document_id)
        .order_by(CollisionPair.similarity.desc(), CollisionPair.id),
    )
    for pair in pairs:
        groups[pair.verdict or CollisionPairStatus.ERROR.value].append(_pair_out(pair, lookup, evidence[pair.id]))
    return CollisionsOut(
        document_id=document_id,
        collisions_status=AnalysisStatus(document.collisions_status),
        collision=groups[CollisionVerdict.COLLISION.value],
        no_collision=groups[CollisionVerdict.NO_COLLISION.value],
        insufficient_data=groups[CollisionVerdict.INSUFFICIENT_DATA.value],
        errors=groups[CollisionPairStatus.ERROR.value],
    )


@router.get("/{document_id}/collision-report", response_model=CollisionReportOut)
def collision_report(session: SessionDep, document_id: int) -> CollisionReportOut:
    """Return the stage 4.1 status, search coverage per path, verdict and error counts."""
    document = _document_or_404(session, document_id)
    run = session.get(CollisionRun, document_id)
    rows = session.execute(
        select(CollisionPair.status, CollisionPair.verdict).where(CollisionPair.document_id == document_id),
    ).all()
    verdicts = Counter(CollisionVerdict(verdict) for _status, verdict in rows if verdict is not None)
    return CollisionReportOut(
        document_id=document_id,
        collisions_status=AnalysisStatus(document.collisions_status),
        threshold=run.threshold if run else None,
        embedding_model=run.embedding_model if run else None,
        metric=run.metric if run else None,
        text_format=run.text_format if run else None,
        compared_records=run.compared_records if run else 0,
        compared_views=run.compared_views if run else 0,
        context_records=run.context_records if run else 0,
        local_pairs=run.local_pairs if run else 0,
        local_above=run.local_above if run else 0,
        category_pairs=run.category_pairs if run else 0,
        category_above=run.category_above if run else 0,
        pairs_sent=len(rows),
        verdicts={verdict: verdicts.get(verdict, 0) for verdict in CollisionVerdict},
        errors=sum(pair_status == CollisionPairStatus.ERROR.value for pair_status, _verdict in rows),
        created_at=run.created_at if run else None,
    )


@router.post("/{document_id}/collisions", status_code=status.HTTP_202_ACCEPTED, response_model=CollisionRunOut)
def run_collisions(request: Request, session: SessionDep, document_id: int) -> CollisionRunOut:
    """Queue stage 4.1 (and any later stages) again; poll the report for ``collisions_status``."""
    document = _document_or_404(session, document_id)
    queue: ParsingQueue | None = request.app.state.parsing_queue
    if queue is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNAVAILABLE)
    # Mark the run before queueing it, so a client polling right away never sees the previous outcome.
    previous = document.collisions_status
    document.collisions_status = AnalysisStatus.RUNNING.value
    session.commit()
    try:
        queue.submit_from(document_id, CollisionStage.name)
    except KeyError:
        # The stage is chained only when embeddings are configured (OPENAI_API_KEY).
        document.collisions_status = previous
        session.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNAVAILABLE) from None
    return CollisionRunOut(document_id=document_id, collisions_status=AnalysisStatus.RUNNING)
