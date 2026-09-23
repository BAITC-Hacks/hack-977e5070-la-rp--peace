"""Stage 3 as a post-parse pipeline stage: blocks → model → checks → one-transaction save.

The stage reads the document tree (stage 1) and the entity registry (stage 2) from the
database only. It runs when stage 2 finished (``done`` or ``needs_review``); otherwise the
document stays ``not_started`` and stale stage 3 rows are removed, because they would refer to
a registry that no longer holds. Blocks are processed sequentially; all results replace the
previous stage 3 rows of the document in one transaction.
"""

import json
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from la_rp_peace.activities.checks import (
    IssueDraft,
    binding_issues,
    block_issues,
    document_status,
    record_issues,
    review_status,
)
from la_rp_peace.activities.extract import BlockOutcome, extract_block
from la_rp_peace.activities.prompt import block_messages, entity_key, registry_view
from la_rp_peace.activities.verify import BlockScope, CheckedRecord, RegistryEntry
from la_rp_peace.entities.blocks import plan_blocks
from la_rp_peace.entities.verify import SourceVerifier, VerifiedSource
from la_rp_peace.enums import ActivitiesStatus, ActivityIssueType, EntitiesStatus
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
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
from la_rp_peace.navigation import describe

log = get_logger(__name__)

READY_ENTITIES = frozenset({EntitiesStatus.DONE.value, EntitiesStatus.NEEDS_REVIEW.value})


def clear_activities(session: Session, document_id: int) -> None:
    """Delete every stage 3 row of a document (not committed)."""
    session.execute(delete(ActivityIssue).where(ActivityIssue.document_id == document_id))
    session.execute(delete(ActivitySource).where(ActivitySource.document_id == document_id))
    session.execute(delete(ActivityBinding).where(ActivityBinding.document_id == document_id))
    session.execute(delete(ActivityRecord).where(ActivityRecord.document_id == document_id))
    session.execute(delete(ActivityBlock).where(ActivityBlock.document_id == document_id))


def _add_sources(
    session: Session,
    document_id: int,
    sources: Sequence[VerifiedSource],
    record_id: int | None = None,
    binding_id: int | None = None,
) -> None:
    session.add_all(
        ActivitySource(
            document_id=document_id,
            record_id=record_id,
            binding_id=binding_id,
            node_id=source.node_id,
            quote=source.quote,
            quote_start=source.start,
            quote_end=source.end,
            supports=json.dumps(list(source.supports), ensure_ascii=False),
        )
        for source in sources
    )


def _add_issues(
    session: Session,
    document_id: int,
    issues: Sequence[IssueDraft],
    record_id: int | None = None,
    binding_id: int | None = None,
) -> None:
    session.add_all(
        ActivityIssue(
            document_id=document_id,
            record_id=record_id,
            binding_id=binding_id,
            issue_type=issue.issue_type.value,
            message=issue.message,
            is_blocking=int(issue.is_blocking),
        )
        for issue in issues
    )


def _save_record(session: Session, document_id: int, record: CheckedRecord) -> None:
    row = ActivityRecord(
        document_id=document_id,
        record_type=record.record_type.value,
        formulation=record.formulation,
        condition=record.condition,
        deadline=record.deadline,
        periodicity=record.periodicity,
        review_status=review_status(record).value,
    )
    session.add(row)
    session.flush()
    _add_sources(session, document_id, record.sources, record_id=row.id)
    _add_issues(session, document_id, record_issues(record), record_id=row.id)
    for binding in record.bindings:
        bound = ActivityBinding(
            document_id=document_id,
            record_id=row.id,
            entity_id=binding.entity_id,
            designation=binding.designation,
            participation=binding.participation.value,
            condition=binding.condition,
            note=binding.note,
        )
        session.add(bound)
        session.flush()
        _add_sources(session, document_id, binding.sources, binding_id=bound.id)
        _add_issues(session, document_id, binding_issues(binding), record_id=row.id, binding_id=bound.id)


def save_outcomes(session: Session, document_id: int, outcomes: Sequence[BlockOutcome]) -> None:
    """Replace the document's stage 3 rows with the outcomes (not committed)."""
    clear_activities(session, document_id)
    for outcome in outcomes:
        session.add(
            ActivityBlock(
                document_id=document_id,
                node_id=outcome.root_id,
                status=outcome.status.value,
                message=outcome.message,
                attempts=outcome.attempts,
            ),
        )
        for record in outcome.records:
            _save_record(session, document_id, record)
        _add_issues(session, document_id, block_issues(outcome))


class ActivityStage:
    """Stage 3 of the pipeline: activities of the document's entities."""

    name = "activities"

    def __init__(self, model: ChatModel, max_chars: int, retries: int) -> None:
        """Configure the stage.

        Args:
            model: Chat model for the block requests.
            max_chars: Size limit of one block's rendered text.
            retries: Corrected answers to request per block after the first.
        """
        self._model = model
        self._max_chars = max_chars
        self._retries = retries

    def run(self, session: Session, document_id: int) -> None:
        """Extract, check and store the document's activities, committing status and results."""
        document = session.get(Document, document_id)
        if document is None:
            log.warning("activities_document_missing", document_id=document_id)
            return
        if document.entities_status not in READY_ENTITIES:
            clear_activities(session, document_id)
            document.activities_status = ActivitiesStatus.NOT_STARTED.value
            session.commit()
            log.info("activities_skipped", document_id=document_id, entities_status=document.entities_status)
            return
        document.activities_status = ActivitiesStatus.RUNNING.value
        session.commit()
        outcomes = self._extract(session, document)
        status = document_status(outcomes)
        save_outcomes(session, document_id, outcomes)
        document.activities_status = status.value
        session.commit()
        records = sum(len(outcome.records) for outcome in outcomes)
        log.info("activities_done", document_id=document_id, status=status, blocks=len(outcomes), records=records)

    def _extract(self, session: Session, document: Document) -> list[BlockOutcome]:
        nodes = session.scalars(
            select(DocumentNode).where(DocumentNode.document_id == document.id).order_by(DocumentNode.id),
        ).all()
        entities = session.scalars(select(Entity).where(Entity.document_id == document.id).order_by(Entity.id)).all()
        places = describe(nodes, json.loads(document.source_map))
        blocks = plan_blocks(nodes, places, self._max_chars)
        verifier = SourceVerifier({node.id: node.text for node in nodes})
        registry = {entity_key(entity.id): RegistryEntry(entity.id, entity.name) for entity in entities}
        registry_text = registry_view(entities)
        outcomes: list[BlockOutcome] = []
        for number, block in enumerate(blocks, start=1):
            own = frozenset(line.node_id for line in block.lines if not line.context)
            scope = BlockScope(verifier, registry, own)
            opening = block_messages(document, registry_text, block, number, len(blocks))
            path = places[block.root_id].path
            outcomes.append(extract_block(self._model, opening, block, path, scope, self._retries))
        return outcomes

    def fail(self, session: Session, document_id: int, message: str) -> None:
        """Mark the stage failed for the document with a blocking issue."""
        session.rollback()
        document = session.get(Document, document_id)
        if document is None:
            return
        document.activities_status = ActivitiesStatus.FAILED.value
        session.add(
            ActivityIssue(
                document_id=document_id,
                issue_type=ActivityIssueType.OTHER.value,
                message=message,
                is_blocking=1,
            ),
        )
        session.commit()
        log.warning("activities_failed", document_id=document_id, reason=message)
