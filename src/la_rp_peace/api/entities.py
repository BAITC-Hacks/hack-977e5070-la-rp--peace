"""Stage 2 results of a document: entities, relations, processing report, and re-runs.

Every source is returned ready for a person: node id, section path and file location from
``navigation.describe``, the verbatim quote with its offsets in the node text, and what the
quote supports.
"""

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from la_rp_peace.api.deps import SessionDep
from la_rp_peace.enums import (
    BlockStatus,
    EntitiesStatus,
    EntityCategory,
    EntityIssueType,
    ParentStatus,
    RelationType,
    ReviewStatus,
)
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.models import (
    Document,
    DocumentNode,
    Entity,
    EntityBlock,
    EntityIssue,
    EntityRelation,
    EntitySource,
)
from la_rp_peace.navigation import NodePlace, describe

router = APIRouter(prefix="/api/documents", tags=["entities"])

STAGE_NAME = "entities"


class EntitySourceOut(BaseModel):
    """A verbatim quote backing an entity or relation claim."""

    node_id: int
    path: str
    location: dict[str, Any]
    quote: str
    start: int
    end: int
    supports: list[str]


class RoleOut(BaseModel):
    """A confirmed functional role with its scope or condition."""

    role: str
    scope: str | None


class EntityOut(BaseModel):
    """An organisational object of the document."""

    id: int
    parent_id: int | None
    parent_status: ParentStatus
    parent_candidates: list[int]
    name: str
    aliases: list[str]
    entity_type: str
    category: EntityCategory
    position_type: str | None
    level: str | None
    roles: list[RoleOut]
    review_status: ReviewStatus
    sources: list[EntitySourceOut]


class RelationOut(BaseModel):
    """A relation other than organisational membership; ``from`` is the subordinate side."""

    id: int
    from_entity_id: int
    to_entity_id: int
    relation_type: RelationType
    conditions: str | None
    sources: list[EntitySourceOut]


class BlockMarkOut(BaseModel):
    """Processing mark of one block sent to the model."""

    node_id: int
    path: str
    status: BlockStatus
    message: str | None
    attempts: int


class EntityIssueOut(BaseModel):
    """A stage 2 problem, optionally tied to an entity or relation."""

    id: int
    entity_id: int | None
    relation_id: int | None
    issue_type: EntityIssueType
    message: str
    is_blocking: bool
    resolved_at: str | None
    created_at: str


class EntityReportOut(BaseModel):
    """How stage 2 went for a document."""

    document_id: int
    entities_status: EntitiesStatus
    blocks: list[BlockMarkOut]
    issues: list[EntityIssueOut]


class EntitiesRunOut(BaseModel):
    """Acknowledgement of a queued stage 2 re-run."""

    document_id: int
    entities_status: EntitiesStatus


def _document(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return document


def _places(session: Session, document: Document) -> dict[int, NodePlace]:
    nodes = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document.id)).all()
    return describe(nodes, json.loads(document.source_map))


def _sources(
    session: Session, document_id: int, places: dict[int, NodePlace], of_relations: bool
) -> dict[int, list[EntitySourceOut]]:
    """Sources of the document's entities (or relations), grouped by owner id."""
    owner = EntitySource.relation_id if of_relations else EntitySource.entity_id
    query = select(owner, EntitySource).where(EntitySource.document_id == document_id, owner.is_not(None))
    grouped: dict[int, list[EntitySourceOut]] = defaultdict(list)
    for owner_id, row in session.execute(query.order_by(EntitySource.id)).tuples():
        place = places[row.node_id]
        grouped[owner_id or 0].append(
            EntitySourceOut(
                node_id=row.node_id,
                path=place.path,
                location=place.location,
                quote=row.quote,
                start=row.quote_start,
                end=row.quote_end,
                supports=json.loads(row.supports),
            ),
        )
    return grouped


@router.get("/{document_id}/entities", response_model=list[EntityOut])
def list_entities(session: SessionDep, document_id: int) -> list[EntityOut]:
    """Return the document's organisational objects with their sources."""
    document = _document(session, document_id)
    sources = _sources(session, document_id, _places(session, document), of_relations=False)
    rows = session.scalars(select(Entity).where(Entity.document_id == document_id).order_by(Entity.id))
    return [
        EntityOut(
            id=row.id,
            parent_id=row.parent_id,
            parent_status=ParentStatus(row.parent_status),
            parent_candidates=json.loads(row.parent_candidates),
            name=row.name,
            aliases=json.loads(row.aliases),
            entity_type=row.entity_type,
            category=EntityCategory(row.category),
            position_type=row.position_type,
            level=row.level,
            roles=[RoleOut.model_validate(role) for role in json.loads(row.roles)],
            review_status=ReviewStatus(row.review_status),
            sources=sources.get(row.id, []),
        )
        for row in rows
    ]


@router.get("/{document_id}/entity-relations", response_model=list[RelationOut])
def list_entity_relations(session: SessionDep, document_id: int) -> list[RelationOut]:
    """Return relations other than organisational membership, with their sources."""
    document = _document(session, document_id)
    sources = _sources(session, document_id, _places(session, document), of_relations=True)
    query = select(EntityRelation).where(EntityRelation.document_id == document_id).order_by(EntityRelation.id)
    return [
        RelationOut(
            id=row.id,
            from_entity_id=row.from_entity_id,
            to_entity_id=row.to_entity_id,
            relation_type=RelationType(row.relation_type),
            conditions=row.conditions,
            sources=sources.get(row.id, []),
        )
        for row in session.scalars(query)
    ]


@router.get("/{document_id}/entity-report", response_model=EntityReportOut)
def get_entity_report(session: SessionDep, document_id: int) -> EntityReportOut:
    """Return the block marks, the issues and the stage 2 status of a document."""
    document = _document(session, document_id)
    places = _places(session, document)
    blocks = session.scalars(select(EntityBlock).where(EntityBlock.document_id == document_id).order_by(EntityBlock.id))
    issues = session.scalars(select(EntityIssue).where(EntityIssue.document_id == document_id).order_by(EntityIssue.id))
    return EntityReportOut(
        document_id=document_id,
        entities_status=EntitiesStatus(document.entities_status),
        blocks=[
            BlockMarkOut(
                node_id=block.node_id,
                path=places[block.node_id].path,
                status=BlockStatus(block.status),
                message=block.message,
                attempts=block.attempts,
            )
            for block in blocks
        ],
        issues=[
            EntityIssueOut(
                id=issue.id,
                entity_id=issue.entity_id,
                relation_id=issue.relation_id,
                issue_type=EntityIssueType(issue.issue_type),
                message=issue.message,
                is_blocking=bool(issue.is_blocking),
                resolved_at=issue.resolved_at,
                created_at=issue.created_at,
            )
            for issue in issues
        ],
    )


@router.post("/{document_id}/entities", status_code=status.HTTP_202_ACCEPTED, response_model=EntitiesRunOut)
def rerun_entities(request: Request, session: SessionDep, document_id: int) -> EntitiesRunOut:
    """Queue stage 2 (and the stages after it) again; poll GET /{id} for ``entities_status``."""
    queue: ParsingQueue | None = request.app.state.parsing_queue
    if queue is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Извлечение недоступно: не заданы OPENAI_API_KEY и OPENAI_MODEL",
        )
    document = _document(session, document_id)
    nodes = session.scalar(select(func.count()).where(DocumentNode.document_id == document_id))
    if not nodes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Документ ещё не разобран: нет дерева текста")
    document.entities_status = EntitiesStatus.RUNNING.value
    session.commit()
    queue.submit_from(document_id, STAGE_NAME)
    return EntitiesRunOut(document_id=document_id, entities_status=EntitiesStatus.RUNNING)
