"""Stage 3 as a post-parse pipeline stage: blocks → model → checks → one-transaction save.

The stage reads the document tree (stage 1) and the entity registry (stage 2) from the
database only. It runs when stage 2 finished (``done`` or ``needs_review``); otherwise the
document stays ``not_started`` and stale stage 3 rows are removed, because they would refer to
a registry that no longer holds. Blocks only read the fixed registry, so they are asked in
parallel (``parallel`` at a time) and collected in document order; the run is saved in one
transaction where each block's verified result replaces that block's previous records
(``store.save_outcomes``).
"""

import json
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.activities.checks import document_status
from la_rp_peace.activities.extract import BlockOutcome, extract_block
from la_rp_peace.activities.prompt import block_messages, entity_key, registry_view
from la_rp_peace.activities.store import clear_activities, save_outcomes
from la_rp_peace.activities.verify import BlockScope, RegistryEntry
from la_rp_peace.entities.blocks import Block, plan_blocks
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import ActivitiesStatus, ActivityIssueType, EntitiesStatus
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import ActivityIssue, Document, DocumentNode, Entity
from la_rp_peace.navigation import describe

log = get_logger(__name__)

READY_ENTITIES = frozenset({EntitiesStatus.DONE.value, EntitiesStatus.NEEDS_REVIEW.value})


class ActivityStage:
    """Stage 3 of the pipeline: activities of the document's entities."""

    name = "activities"

    def __init__(self, model: ChatModel, max_chars: int, retries: int, parallel: int = 1) -> None:
        """Configure the stage.

        Args:
            model: Chat model for the block requests.
            max_chars: Size limit of one block's rendered text.
            retries: Corrected answers to request per block after the first.
            parallel: Blocks asked at once (they are independent given the registry).
        """
        self._model = model
        self._max_chars = max_chars
        self._retries = retries
        self._parallel = max(1, parallel)

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
        statuses = save_outcomes(session, document_id, outcomes)
        status = document_status(outcomes, statuses)
        document.activities_status = status.value
        session.commit()
        log.info("activities_done", document_id=document_id, status=status, blocks=len(outcomes), records=len(statuses))

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

        def read(numbered: tuple[int, Block]) -> BlockOutcome:
            number, block = numbered
            own = frozenset(line.node_id for line in block.lines if not line.context)
            scope = BlockScope(verifier, registry, own)
            opening = block_messages(document, registry_text, block, number, len(blocks))
            return extract_block(self._model, opening, block, places[block.root_id].path, scope, self._retries)

        with ThreadPoolExecutor(max_workers=self._parallel, thread_name_prefix="activities") as pool:
            return list(pool.map(read, enumerate(blocks, start=1)))

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
