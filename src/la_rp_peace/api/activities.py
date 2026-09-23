"""Stage 3 results: activity records with participants and sources, the processing report, re-runs."""

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from la_rp_peace.activities.pipeline import ActivityStage
from la_rp_peace.api.deps import SessionDep
from la_rp_peace.enums import (
    ActivitiesStatus,
    ActivityIssueType,
    ActivityType,
    BlockStatus,
    Participation,
    ReviewStatus,
    Specificity,
)
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.models import (
    ActivityBlock,
    ActivityIssue,
    ActivityRecord,
    ActivitySource,
    Document,
    DocumentNode,
    Entity,
)
from la_rp_peace.navigation import NodePlace, describe

router = APIRouter(prefix="/api/documents", tags=["activities"])


class ActivitySourceOut(BaseModel):
    """A verbatim quote with where to find it; ``start``/``end`` index the node's own text."""

    node_id: int
    path: str
    location: dict[str, Any]
    quote: str
    start: int
    end: int
    supports: list[str]


class ParticipantOut(BaseModel):
    """Another known participant of the same provision."""

    entity_id: int
    entity_name: str | None


class ActivityRecordOut(BaseModel):
    """One provision for one entity; ``entity_id`` None is an unresolved role or group remainder."""

    id: int
    block_node_id: int
    entity_id: int | None
    entity_name: str | None
    designation: str
    record_type: ActivityType
    formulation: str
    specificity: Specificity
    participation: Participation
    participant_designation: str
    other_participants: list[ParticipantOut]
    condition: str | None
    deadline: str | None
    periodicity: str | None
    note: str | None
    review_status: ReviewStatus
    sources: list[ActivitySourceOut]


class ActivityBlockOut(BaseModel):
    """Processing mark of one block."""

    node_id: int
    path: str
    status: BlockStatus
    message: str | None
    attempts: int


class ActivityIssueOut(BaseModel):
    """A stage 3 issue."""

    id: int
    record_id: int | None
    issue_type: ActivityIssueType
    message: str
    is_blocking: bool
    resolved_at: str | None
    created_at: str


class ActivityReportOut(BaseModel):
    """How stage 3 went for a document."""

    document_id: int
    activities_status: ActivitiesStatus
    record_count: int
    blocks: list[ActivityBlockOut]
    issues: list[ActivityIssueOut]


class ActivityRunOut(BaseModel):
    """A queued stage 3 run."""

    document_id: int
    activities_status: ActivitiesStatus


def _document_or_404(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return document


def _places(session: Session, document: Document) -> dict[int, NodePlace]:
    nodes = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document.id)).all()
    return describe(nodes, json.loads(document.source_map))


def _source_out(source: ActivitySource, places: dict[int, NodePlace]) -> ActivitySourceOut:
    place = places[source.node_id]
    return ActivitySourceOut(
        node_id=source.node_id,
        path=place.path,
        location=place.location,
        quote=source.quote,
        start=source.quote_start,
        end=source.quote_end,
        supports=json.loads(source.supports),
    )


def _record_out(record: ActivityRecord, names: dict[int, str], sources: list[ActivitySourceOut]) -> ActivityRecordOut:
    others: list[int] = json.loads(record.participant_entity_ids)
    return ActivityRecordOut(
        id=record.id,
        block_node_id=record.block_node_id,
        entity_id=record.entity_id,
        entity_name=names.get(record.entity_id) if record.entity_id is not None else None,
        designation=record.designation,
        record_type=ActivityType(record.record_type),
        formulation=record.formulation,
        specificity=Specificity(record.specificity),
        participation=Participation(record.participation),
        participant_designation=record.participant_designation,
        other_participants=[ParticipantOut(entity_id=other, entity_name=names.get(other)) for other in others],
        condition=record.condition,
        deadline=record.deadline,
        periodicity=record.periodicity,
        note=record.note,
        review_status=ReviewStatus(record.review_status),
        sources=sources,
    )


@router.get("/{document_id}/activities", response_model=list[ActivityRecordOut])
def list_activities(session: SessionDep, document_id: int) -> list[ActivityRecordOut]:
    """Return the document's records (one per entity) with participants and resolved sources."""
    places = _places(session, _document_or_404(session, document_id))
    names = dict(
        session.execute(select(Entity.id, Entity.name).where(Entity.document_id == document_id)).tuples().all(),
    )
    sources: defaultdict[int, list[ActivitySourceOut]] = defaultdict(list)
    query = select(ActivitySource).where(ActivitySource.document_id == document_id).order_by(ActivitySource.id)
    for source in session.scalars(query):
        sources[source.record_id].append(_source_out(source, places))
    records = session.scalars(
        select(ActivityRecord)
        .where(ActivityRecord.document_id == document_id)
        .order_by(ActivityRecord.block_node_id, ActivityRecord.id),
    )
    return [_record_out(record, names, sources[record.id]) for record in records]


@router.get("/{document_id}/activity-report", response_model=ActivityReportOut)
def activity_report(session: SessionDep, document_id: int) -> ActivityReportOut:
    """Return the stage 3 status, the mark of every block and the issues."""
    document = _document_or_404(session, document_id)
    places = _places(session, document)
    blocks = session.scalars(
        select(ActivityBlock).where(ActivityBlock.document_id == document_id).order_by(ActivityBlock.id),
    )
    issues = session.scalars(
        select(ActivityIssue).where(ActivityIssue.document_id == document_id).order_by(ActivityIssue.id),
    )
    count = session.scalar(select(func.count()).where(ActivityRecord.document_id == document_id)) or 0
    return ActivityReportOut(
        document_id=document_id,
        activities_status=ActivitiesStatus(document.activities_status),
        record_count=count,
        blocks=[
            ActivityBlockOut(
                node_id=block.node_id,
                path=places[block.node_id].path,
                status=BlockStatus(block.status),
                message=block.message,
                attempts=block.attempts,
            )
            for block in blocks
        ],
        issues=[
            ActivityIssueOut(
                id=issue.id,
                record_id=issue.record_id,
                issue_type=ActivityIssueType(issue.issue_type),
                message=issue.message,
                is_blocking=bool(issue.is_blocking),
                resolved_at=issue.resolved_at,
                created_at=issue.created_at,
            )
            for issue in issues
        ],
    )


@router.post("/{document_id}/activities", status_code=status.HTTP_202_ACCEPTED, response_model=ActivityRunOut)
def run_activities(request: Request, session: SessionDep, document_id: int) -> ActivityRunOut:
    """Queue stage 3 (and any later stages) again; poll the report for ``activities_status``."""
    document = _document_or_404(session, document_id)
    queue: ParsingQueue | None = request.app.state.parsing_queue
    if queue is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Извлечение недоступно: не заданы OPENAI_API_KEY и OPENAI_MODEL",
        )
    queue.submit_from(document_id, ActivityStage.name)
    return ActivityRunOut(document_id=document_id, activities_status=ActivitiesStatus(document.activities_status))
