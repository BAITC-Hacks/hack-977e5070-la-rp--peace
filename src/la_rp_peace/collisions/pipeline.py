"""Stage 4.1 as a post-parse pipeline stage: sides → pairs → embeddings → verification → save.

The stage reads stages 1–3 from the database only and runs when both stage 2 and stage 3 are
``done`` or ``needs_review``; otherwise ``collisions_status`` stays ``not_started`` and stale 4.1
rows are removed. The status goes ``running`` (committed) while the pairs are embedded and
verified; the result replaces the previous 4.1 rows in one transaction. The document is
``needs_review`` when any question ended in an error or any pair is a possible collision or lacks
data (a verdict for a person to check), else ``done``. A crash marks it ``failed`` and keeps the
previous result.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.collisions.checks import answer_check
from la_rp_peace.collisions.pairs import Candidate, Selection, candidate_pairs, select_pairs
from la_rp_peace.collisions.prompt import SYSTEM_PROMPT, render_question
from la_rp_peace.collisions.sides import Inputs, build_inputs
from la_rp_peace.collisions.store import RunData, RunResult, clear_collisions, save_run
from la_rp_peace.embeddings import Embedder, cosine_matrix, embed_texts
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import ActivitiesStatus, AnalysisStatus, CollisionVerdict, EntitiesStatus
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
from la_rp_peace.models import ActivityRecord, ActivitySource, Document, DocumentNode, Entity
from la_rp_peace.navigation import describe
from la_rp_peace.verification import Question, ask_in_batches

log = get_logger(__name__)

READY_ENTITIES = frozenset({EntitiesStatus.DONE.value, EntitiesStatus.NEEDS_REVIEW.value})
READY_ACTIVITIES = frozenset({ActivitiesStatus.DONE.value, ActivitiesStatus.NEEDS_REVIEW.value})
FOR_REVIEW = frozenset({CollisionVerdict.COLLISION.value, CollisionVerdict.INSUFFICIENT_DATA.value})


def load_inputs(session: Session, document_id: int) -> Inputs:
    """Read the stage 2 entities and stage 3 records and sources of a document."""
    records = session.scalars(select(ActivityRecord).where(ActivityRecord.document_id == document_id)).all()
    entities = session.scalars(select(Entity).where(Entity.document_id == document_id)).all()
    sources = session.scalars(
        select(ActivitySource).where(ActivitySource.document_id == document_id).order_by(ActivitySource.id),
    ).all()
    return build_inputs(records, entities, sources)


def final_status(result: RunResult) -> AnalysisStatus:
    """``needs_review`` with errors or verdicts a person must check, else ``done``."""
    if result.errors or any(result.verdicts.get(verdict) for verdict in FOR_REVIEW):
        return AnalysisStatus.NEEDS_REVIEW
    return AnalysisStatus.DONE


class CollisionStage:
    """Stage 4.1 of the pipeline: function collisions inside the document."""

    name = "collisions"

    def __init__(self, model: ChatModel, embedder: Embedder, retries: int) -> None:
        """Configure the stage.

        Args:
            model: Chat model answering the verification batches.
            embedder: Embedding model used to select pairs.
            retries: Corrected replies to request per batch after the first.
        """
        self._model = model
        self._embedder = embedder
        self._retries = retries

    def run(self, session: Session, document_id: int) -> None:
        """Find, verify and store the document's function collisions, committing status and results."""
        document = session.get(Document, document_id)
        if document is None:
            log.warning("collisions_document_missing", document_id=document_id)
            return
        if document.entities_status not in READY_ENTITIES or document.activities_status not in READY_ACTIVITIES:
            clear_collisions(session, document_id)
            document.collisions_status = AnalysisStatus.NOT_STARTED.value
            session.commit()
            log.info("collisions_skipped", document_id=document_id, activities_status=document.activities_status)
            return
        document.collisions_status = AnalysisStatus.RUNNING.value
        session.commit()
        run = self._compute(session, document)
        result = save_run(session, run)
        status = final_status(result)
        document.collisions_status = status.value
        session.commit()
        log.info(
            "collisions_done",
            document_id=document_id,
            status=status,
            sides=len(run.inputs.sides),
            local_above=run.selection.local_above,
            category_above=run.selection.category_above,
            pairs=result.pairs,
            verdicts=result.verdicts,
            errors=result.errors,
        )

    def _select(self, session: Session, candidates: list[Candidate]) -> Selection:
        sides = {side.key: side for candidate in candidates for side in (candidate.a, candidate.b)}
        keys = sorted(sides)
        vectors = embed_texts(session, self._embedder, [sides[key].text() for key in keys])
        # The cache is shared by all documents and stages; keep it even if verification fails.
        session.commit()
        scores = cosine_matrix(vectors, vectors)
        return select_pairs(candidates, scores, {key: row for row, key in enumerate(keys)})

    def _compute(self, session: Session, document: Document) -> RunData:
        inputs = load_inputs(session, document.id)
        nodes = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document.id)).all()
        places = describe(nodes, json.loads(document.source_map))
        texts = {node.id: node.text for node in nodes}
        verifier = SourceVerifier(texts)
        selection = self._select(session, candidate_pairs(inputs.sides))
        plans = [
            render_question(f"q{number}", pair, inputs, places, texts)
            for number, pair in enumerate(selection.pairs, start=1)
        ]
        questions = [Question(plan.question_id, plan.text) for plan in plans]
        check = answer_check({plan.question_id: plan for plan in plans}, verifier)
        outcomes = ask_in_batches(self._model, SYSTEM_PROMPT, questions, check, self._retries)
        return RunData(document.id, inputs, selection, plans, outcomes, verifier, self._embedder.model)

    def fail(self, session: Session, document_id: int, message: str) -> None:
        """Mark the stage failed for the document; the previous result stays as it was."""
        session.rollback()
        document = session.get(Document, document_id)
        if document is None:
            return
        document.collisions_status = AnalysisStatus.FAILED.value
        session.commit()
        log.warning("collisions_failed", document_id=document_id, reason=message)
