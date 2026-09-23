"""Stage 2 as a post-parse pipeline stage: blocks → registry → review → checks → one save.

The document is read block by block in document order, so the registry — and with it the
context shown to the model — grows as the reading goes. After the whole-document review and
the final checks, one transaction replaces the document's previous stage 2 rows and sets
``documents.entities_status``. Only this document's tree is read; nothing crosses documents.
"""

import json
import re

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from la_rp_peace.entities.blocks import plan_blocks
from la_rp_peace.entities.checks import StageReport, finish
from la_rp_peace.entities.consolidate import consolidate
from la_rp_peace.entities.extract import BlockMark, extract_block
from la_rp_peace.entities.prompt import DocumentCard
from la_rp_peace.entities.registry import Registry
from la_rp_peace.entities.verify import SourceVerifier, VerifiedSource
from la_rp_peace.enums import EntitiesStatus, EntityIssueType, ParentStatus, ReviewStatus
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


def clear_entities(session: Session, document_id: int) -> None:
    """Delete the document's stage 2 rows (without committing)."""
    for model in (EntitySource, EntityIssue, EntityRelation, EntityBlock):
        session.execute(delete(model).where(model.document_id == document_id))
    session.execute(
        update(Entity)
        .where(Entity.document_id == document_id)
        .values(parent_id=None, parent_status=ParentStatus.UNKNOWN.value),
    )
    session.execute(delete(Entity).where(Entity.document_id == document_id))


class _Writer:
    """Writes one registry as database rows of one document."""

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

    def source(self, source: VerifiedSource, entity_id: int | None = None, relation_id: int | None = None) -> None:
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
            ),
        )

    def entities(self, review: dict[str, ReviewStatus]) -> None:
        rows: dict[str, Entity] = {}
        for key, entity in self.registry.entities.items():
            rows[key] = Entity(
                document_id=self.document_id,
                parent_id=None,
                parent_status=ParentStatus.UNKNOWN.value,
                name=entity.name,
                aliases=json.dumps(entity.aliases, ensure_ascii=False),
                entity_type=entity.entity_type,
                position_type=entity.position_type,
                level=entity.level,
                roles=json.dumps(entity.roles, ensure_ascii=False),
                review_status=review[key].value,
            )
            self.session.add(rows[key])
        self.session.flush()
        self.entity_ids = {key: row.id for key, row in rows.items()}
        for key, entity in self.registry.entities.items():
            rows[key].parent_id = None if entity.parent is None else self.entity_ids[entity.parent]
            rows[key].parent_status = entity.parent_status.value
            rows[key].parent_candidates = json.dumps([self.entity_ids[c] for c in entity.candidates])
            for source in dict.fromkeys(entity.sources):
                self.source(source, entity_id=rows[key].id)
        self.session.flush()

    def relations(self) -> None:
        for relation in self.registry.relations:
            row = EntityRelation(
                document_id=self.document_id,
                from_entity_id=self.entity_ids[relation.from_key],
                to_entity_id=self.entity_ids[relation.to_key],
                relation_type=relation.relation_type.value,
                conditions=relation.conditions,
            )
            self.session.add(row)
            self.session.flush()
            self.relation_ids.append(row.id)
            for source in dict.fromkeys(relation.sources):
                self.source(source, relation_id=row.id)

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
    """Replace the document's stage 2 results in one transaction and set its status.

    Args:
        session: Database session.
        document_id: The document.
        registry: The checked registry.
        marks: Marks of all planned blocks.
        report: Result of the final checks.
    """
    document = session.get(Document, document_id)
    if document is None:
        log.warning("entities_document_missing", document_id=document_id)
        return
    clear_entities(session, document_id)
    writer = _Writer(session, document_id, registry)
    writer.entities(report.review)
    writer.relations()
    writer.issues()
    writer.blocks(marks)
    document.entities_status = report.status.value
    session.commit()


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
        document.entities_status = EntitiesStatus.RUNNING.value
        session.commit()
        log.info("entities_started", document_id=document_id, blocks=len(blocks))
        registry = Registry(SourceVerifier(texts))
        marks = [extract_block(self._model, card, block, registry, self._retries) for block in blocks]
        consolidate(self._model, card, registry, places, texts, self._retries)
        report = finish(registry, blocks, marks)
        save_entities(session, document_id, registry, marks, report)
        log.info("entities_done", document_id=document_id, status=report.status, entities=len(registry.entities))

    def fail(self, session: Session, document_id: int, message: str) -> None:
        """Mark the stage failed with a blocking issue; stale results of an earlier run are removed."""
        document = session.get(Document, document_id)
        if document is None:
            return
        clear_entities(session, document_id)
        document.entities_status = EntitiesStatus.FAILED.value
        session.add(
            EntityIssue(document_id=document_id, issue_type=EntityIssueType.OTHER.value, message=message, is_blocking=1)
        )
        session.commit()
        log.warning("entities_failed", document_id=document_id, reason=message)
