"""Stage 3 results: activity records with bindings and sources, the processing report, re-runs."""

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
)
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.models import (
    ActivityBinding,
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


class ActivityBindingOut(BaseModel):
    """An entity a record is assigned to; ``entity_id`` None means not in the registry."""

    id: int
    entity_id: int | None
    entity_name: str | None
    designation: str
    participation: Participation
    condition: str | None
    note: str | None
    sources: list[ActivitySourceOut]


class ActivityRecordOut(BaseModel):
    """One provision: type, full formulation, condition, deadline, periodicity, bindings, sources."""

    id: int
    record_type: ActivityType
    formulation: str
    condition: str | None
    deadline: str | None
    periodicity: str | None
    review_status: ReviewStatus
    bindings: list[ActivityBindingOut]
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
    binding_id: int | None
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


def _binding_out(
    binding: ActivityBinding, names: dict[int, str], sources: list[ActivitySourceOut]
) -> ActivityBindingOut:
    return ActivityBindingOut(
        id=binding.id,
        entity_id=binding.entity_id,
        entity_name=names.get(binding.entity_id) if binding.entity_id is not None else None,
        designation=binding.designation,
        participation=Participation(binding.participation),
        condition=binding.condition,
        note=binding.note,
        sources=sources,
    )


@router.get("/{document_id}/activities", response_model=list[ActivityRecordOut])
def list_activities(session: SessionDep, document_id: int) -> list[ActivityRecordOut]:
    """Return the document's activity records in document order, with bindings and resolved sources."""
    places = _places(session, _document_or_404(session, document_id))
    names = dict(
        session.execute(select(Entity.id, Entity.name).where(Entity.document_id == document_id)).tuples().all()
    )
    by_record: defaultdict[int, list[ActivitySourceOut]] = defaultdict(list)
    by_binding: defaultdict[int, list[ActivitySourceOut]] = defaultdict(list)
    for source in session.scalars(select(ActivitySource).where(ActivitySource.document_id == document_id)):
        if source.record_id is not None:
            by_record[source.record_id].append(_source_out(source, places))
        elif source.binding_id is not None:
            by_binding[source.binding_id].append(_source_out(source, places))
    bindings: defaultdict[int, list[ActivityBindingOut]] = defaultdict(list)
    for binding in session.scalars(
        select(ActivityBinding).where(ActivityBinding.document_id == document_id).order_by(ActivityBinding.id),
    ):
        bindings[binding.record_id].append(_binding_out(binding, names, by_binding[binding.id]))
    records = session.scalars(
        select(ActivityRecord).where(ActivityRecord.document_id == document_id).order_by(ActivityRecord.id),
    )
    return [
        ActivityRecordOut(
            id=record.id,
            record_type=ActivityType(record.record_type),
            formulation=record.formulation,
            condition=record.condition,
            deadline=record.deadline,
            periodicity=record.periodicity,
            review_status=ReviewStatus(record.review_status),
            bindings=bindings[record.id],
            sources=by_record[record.id],
        )
        for record in records
    ]


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
                binding_id=issue.binding_id,
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
