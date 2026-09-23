"""Stage 2 as a post-parse pipeline stage: blocks → registry → review → checks → one save.

The document is read block by block in document order, so the registry — and with it the
context shown to the model — grows as the reading goes. A re-run replaces each block's
previous contribution with its new verified answer; a block that fails keeps what the
previous run stored for it (re-checked against the current node texts). After the review
and the final checks, one transaction writes the result: unchanged objects keep their ids
(rows are updated in place, so later-stage records referencing ``entities.id`` survive),
objects no longer found are removed, new ones are added. Only this document is read.
"""

import json
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from la_rp_peace.entities.blocks import plan_blocks
from la_rp_peace.entities.checks import StageReport, finish
from la_rp_peace.entities.consolidate import consolidate
from la_rp_peace.entities.extract import BlockMark, extract_block
from la_rp_peace.entities.previous import PreviousResult, load_previous
from la_rp_peace.entities.prompt import DocumentCard
from la_rp_peace.entities.registry import Evidence, RegisteredEntity, Registry
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import BlockStatus, EntitiesStatus, EntityIssueType, ParentStatus, ReviewStatus
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import (
    Document,
    DocumentNode,
    Entity,
    EntityBlock,
    EntityIssue,
    EntityRelation,
    EntitySource,
)
from la_rp_peace.navigation import describe

log = get_logger(__name__)

_KEY = re.compile(r"\bE\d+\b")


class _Writer:
    """Writes one registry as the database rows of one document, keeping unchanged ids."""

    def __init__(self, session: Session, document_id: int, registry: Registry) -> None:
        self.session = session
        self.document_id = document_id
        self.registry = registry
        self.entity_ids: dict[str, int] = {}
        self.relation_ids: list[int] = []

    def humanize(self, message: str) -> str:
        """Replace registry keys in a message by entity names and database ids."""

        def name(match: re.Match[str]) -> str:
            key = self.registry.canonical(match.group(0))
            entity = self.registry.entities.get(key)
            return match.group(0) if entity is None else f"«{entity.name}» (id {self.entity_ids[key]})"

        return _KEY.sub(name, message)

    def clear_dependents(self) -> None:
        """Remove sources, issues and block marks; they are written anew."""
        for model in (EntitySource, EntityIssue, EntityBlock):
            self.session.execute(delete(model).where(model.document_id == self.document_id))

    def source(self, evidence: Evidence, entity_id: int | None = None, relation_id: int | None = None) -> None:
        source = evidence.source
        self.session.add(
            EntitySource(
                document_id=self.document_id,
                entity_id=entity_id,
                relation_id=relation_id,
                node_id=source.node_id,
                quote=source.quote,
                quote_start=source.start,
                quote_end=source.end,
                supports=json.dumps(list(source.supports), ensure_ascii=False),
                block_node_id=evidence.block,
            ),
        )

    def _existing_entities(self) -> dict[int, Entity]:
        query = select(Entity).where(Entity.document_id == self.document_id).execution_options(populate_existing=True)
        rows = {row.id: row for row in self.session.scalars(query)}
        for row in rows.values():
            row.parent_id, row.parent_status, row.parent_candidates = None, ParentStatus.UNKNOWN.value, "[]"
        self.session.flush()
        kept = {entity.previous_id for entity in self.registry.entities.values()}
        for row_id in [row_id for row_id in rows if row_id not in kept]:
            self.session.delete(rows.pop(row_id))
        self.session.flush()
        return rows

    def _fill(self, row: Entity, entity: RegisteredEntity, review: ReviewStatus) -> None:
        row.name = entity.name
        row.aliases = json.dumps(entity.aliases, ensure_ascii=False)
        row.entity_type = entity.entity_type
        row.position_type = entity.position_type
        row.level = entity.level
        row.roles = json.dumps(entity.roles, ensure_ascii=False)
        row.review_status = review.value

    def entities(self, review: dict[str, ReviewStatus]) -> None:
        existing = self._existing_entities()
        rows: dict[str, Entity] = {}
        for key, entity in self.registry.entities.items():
            row = existing.get(entity.previous_id) if entity.previous_id is not None else None
            if row is None:
                row = Entity(document_id=self.document_id, parent_id=None, parent_status=ParentStatus.UNKNOWN.value)
                self.session.add(row)
            self._fill(row, entity, review[key])
            rows[key] = row
        self.session.flush()
        self.entity_ids = {key: row.id for key, row in rows.items()}
        for key, entity in self.registry.entities.items():
            rows[key].parent_id = None if entity.parent is None else self.entity_ids[entity.parent]
            rows[key].parent_status = entity.parent_status.value
            rows[key].parent_candidates = json.dumps([self.entity_ids[c] for c in entity.candidates])
            for evidence in dict.fromkeys(entity.evidence):
                self.source(evidence, entity_id=rows[key].id)
        self.session.flush()

    def relations(self) -> None:
        query = select(EntityRelation).where(EntityRelation.document_id == self.document_id)
        existing = {
            (row.from_entity_id, row.to_entity_id, row.relation_type): row
            for row in self.session.scalars(query.execution_options(populate_existing=True))
        }
        for relation in self.registry.relations:
            ends = (self.entity_ids[relation.from_key], self.entity_ids[relation.to_key])
            row = existing.pop((*ends, relation.relation_type.value), None)
            if row is None:
                row = EntityRelation(
                    document_id=self.document_id,
                    from_entity_id=ends[0],
                    to_entity_id=ends[1],
                    relation_type=relation.relation_type.value,
                )
                self.session.add(row)
            row.conditions = relation.conditions
            self.session.flush()
            self.relation_ids.append(row.id)
            for evidence in dict.fromkeys(relation.evidence):
                self.source(evidence, relation_id=row.id)
        for row in existing.values():
            self.session.delete(row)

    def issues(self) -> None:
        for issue in self.registry.issues:
            entity = None if issue.entity is None else self.registry.canonical(issue.entity)
            self.session.add(
                EntityIssue(
                    document_id=self.document_id,
                    entity_id=self.entity_ids.get(entity) if entity is not None else None,
                    relation_id=None if issue.relation is None else self.relation_ids[issue.relation],
                    issue_type=issue.issue_type.value,
                    message=self.humanize(issue.message),
                    is_blocking=int(issue.is_blocking),
                ),
            )

    def blocks(self, marks: list[BlockMark]) -> None:
        for mark in marks:
            self.session.add(
                EntityBlock(
                    document_id=self.document_id,
                    node_id=mark.node_id,
                    status=mark.status.value,
                    message=mark.message,
                    attempts=mark.attempts,
                ),
            )


def save_entities(
    session: Session, document_id: int, registry: Registry, marks: list[BlockMark], report: StageReport
) -> None:
    """Write the document's stage 2 result in one transaction and set its status.

    Entities whose ``previous_id`` names a stored row update that row; stored rows no longer
    matched are deleted (with their relations); relations are matched by ends and type.

    Args:
        session: Database session.
        document_id: The document.
        registry: The checked registry, with previous ids adopted.
        marks: Marks of all planned blocks.
        report: Result of the final checks.
    """
    document = session.get(Document, document_id)
    if document is None:
        log.warning("entities_document_missing", document_id=document_id)
        return
    writer = _Writer(session, document_id, registry)
    writer.clear_dependents()
    writer.entities(report.review)
    writer.relations()
    writer.issues()
    writer.blocks(marks)
    document.entities_status = report.status.value
    session.commit()


def keep_failed_blocks(registry: Registry, previous: PreviousResult, marks: list[BlockMark]) -> list[BlockMark]:
    """Carry the previous contribution of every block that failed in this run into the registry.

    Runs after all blocks were read, so parents and relation ends found by any block of this
    run are known; objects of this run first adopt their previous ids.

    Args:
        registry: The registry after all blocks.
        previous: The document's stored stage 2 result.
        marks: Marks of this run.

    Returns:
        The marks, with failed blocks noting that their previous result was kept.
    """
    failed = [mark for mark in marks if mark.status is BlockStatus.FAILED and previous.entities_of_block(mark.node_id)]
    if not failed:
        return marks
    registry.adopt_previous_ids(previous)
    kept: dict[int, BlockMark] = {}
    for mark in failed:
        carried = registry.restore(previous, mark.node_id)
        log.info("entity_block_previous_kept", node_id=mark.node_id, entities=carried)
        note = f"{mark.message}; сохранён прежний результат блока ({carried} объектов)"
        kept[mark.node_id] = BlockMark(mark.node_id, mark.status, note, mark.attempts)
    return [kept.get(mark.node_id, mark) for mark in marks]


class EntityStage:
    """Post-parse stage 2: organisational entities of one document."""

    name = "entities"

    def __init__(self, model: ChatModel, max_chars: int, retries: int) -> None:
        """Configure the stage.

        Args:
            model: The chat model.
            max_chars: Size limit of one block's rendered text.
            retries: Corrected answers to request after the first, per call.
        """
        self._model = model
        self._max_chars = max_chars
        self._retries = retries

    def run(self, session: Session, document_id: int) -> None:
        """Extract, review, check and save the document's entities."""
        document = session.get(Document, document_id)
        if document is None:
            log.warning("entities_document_missing", document_id=document_id)
            return
        nodes = list(session.scalars(select(DocumentNode).where(DocumentNode.document_id == document_id)))
        places = describe(nodes, json.loads(document.source_map))
        texts = {node.id: node.text for node in nodes}
        blocks = plan_blocks(nodes, places, self._max_chars)
        card = DocumentCard(document.id, document.title, document.organization, document.document_type)
        previous = load_previous(session, document_id)
        document.entities_status = EntitiesStatus.RUNNING.value
        session.commit()
        log.info("entities_started", document_id=document_id, blocks=len(blocks), previous=len(previous.entities))
        registry = Registry(SourceVerifier(texts))
        marks = [extract_block(self._model, card, block, registry, self._retries) for block in blocks]
        marks = keep_failed_blocks(registry, previous, marks)
        consolidate(self._model, card, registry, places, texts, self._retries)
        report = finish(registry, blocks, marks)
        registry.adopt_previous_ids(previous)
        save_entities(session, document_id, registry, marks, report)
        log.info("entities_done", document_id=document_id, status=report.status, entities=len(registry.entities))

    def fail(self, session: Session, document_id: int, message: str) -> None:
        """Mark the stage failed with a blocking issue; the previously stored result is kept."""
        document = session.get(Document, document_id)
        if document is None:
            return
        document.entities_status = EntitiesStatus.FAILED.value
        session.add(
            EntityIssue(document_id=document_id, issue_type=EntityIssueType.OTHER.value, message=message, is_blocking=1)
        )
        session.commit()
        log.warning("entities_failed", document_id=document_id, reason=message)
