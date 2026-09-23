"""Save a stage 4.1 run: the new result replaces every previous 4.1 row of the document (§6).

One pair = one row whatever the number of search paths that found it. A question that ended
without a valid answer is stored as ``status = error`` with its reason and no verdict.
"""

import json
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from la_rp_peace.collisions.checks import parse_answer, verify_sources
from la_rp_peace.collisions.pairs import THRESHOLD, Selection
from la_rp_peace.collisions.prompt import QuestionPlan
from la_rp_peace.collisions.sides import Inputs, Side
from la_rp_peace.embeddings import METRIC, TEXT_FORMAT
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import CollisionPairStatus, CollisionSideKind
from la_rp_peace.models import (
    CollisionPair,
    CollisionRun,
    CollisionSource,
    CollisionView,
    CollisionViewRecord,
)
from la_rp_peace.verification import Answer, Outcome


@dataclass(frozen=True, slots=True)
class RunData:
    """Everything one run computed for a document."""

    document_id: int
    inputs: Inputs
    selection: Selection
    plans: list[QuestionPlan]
    outcomes: dict[str, Outcome]
    verifier: SourceVerifier
    embedding_model: str


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a run produced, for the final status and the log."""

    pairs: int
    verdicts: dict[str, int]
    errors: int


def clear_collisions(session: Session, document_id: int) -> None:
    """Delete every stage 4.1 row of a document (not committed)."""
    session.execute(delete(CollisionSource).where(CollisionSource.document_id == document_id))
    session.execute(delete(CollisionPair).where(CollisionPair.document_id == document_id))
    session.execute(delete(CollisionViewRecord).where(CollisionViewRecord.document_id == document_id))
    session.execute(delete(CollisionView).where(CollisionView.document_id == document_id))
    session.execute(delete(CollisionRun).where(CollisionRun.document_id == document_id))


def _save_views(session: Session, run: RunData) -> dict[str, int]:
    ids: dict[str, int] = {}
    for side in run.inputs.sides:
        if side.kind is not CollisionSideKind.VIEW:
            continue
        view = CollisionView(
            document_id=run.document_id,
            provision_key=side.provision_key,
            record_type=side.record_type,
            formulation=side.formulation,
            participant_entity_ids=json.dumps(sorted(side.entity_ids)),
            parent_entity_ids=json.dumps(list(side.parent_ids)),
            categories=json.dumps(list(side.categories)),
            embedded_text=side.text(),
        )
        session.add(view)
        session.flush()
        ids[side.key] = view.id
        session.add_all(
            CollisionViewRecord(document_id=run.document_id, view_id=view.id, record_id=record_id)
            for record_id in side.record_ids
        )
    return ids


def _side_columns(prefix: str, side: Side, view_ids: dict[str, int]) -> dict[str, object]:
    is_view = side.kind is CollisionSideKind.VIEW
    return {
        f"{prefix}_kind": side.kind.value,
        f"{prefix}_record_id": None if is_view else side.record_ids[0],
        f"{prefix}_view_id": view_ids[side.key] if is_view else None,
    }


def _save_sources(session: Session, run: RunData, pair_id: int, raw: Answer) -> None:
    errors: list[str] = []
    for source in verify_sources(parse_answer(raw), run.verifier, errors):
        session.add(
            CollisionSource(
                document_id=run.document_id,
                pair_id=pair_id,
                node_id=source.node_id,
                quote=source.quote,
                quote_start=source.start,
                quote_end=source.end,
                supports=json.dumps(list(source.supports)),
            ),
        )


def _save_pair(session: Session, run: RunData, plan: QuestionPlan, view_ids: dict[str, int]) -> None:
    outcome = run.outcomes[plan.question_id]
    candidate = plan.pair.candidate
    answer = parse_answer(outcome.answer) if outcome.answer is not None else None
    row = CollisionPair(
        document_id=run.document_id,
        pair_key=candidate.key,
        **_side_columns("side_a", candidate.a, view_ids),
        **_side_columns("side_b", candidate.b, view_ids),
        bases=json.dumps([basis.value for basis in candidate.bases]),
        basis_details=json.dumps([detail.as_json() for detail in candidate.details]),
        similarity=plan.pair.similarity,
        embedding_model=run.embedding_model,
        metric=METRIC,
        text_format=TEXT_FORMAT,
        question_id=plan.question_id,
        status=CollisionPairStatus.CHECKED.value if answer else CollisionPairStatus.ERROR.value,
        verdict=answer.verdict.value if answer else None,
        explanation=answer.explanation.strip() if answer else None,
        error=None if answer else (outcome.error or "Нет корректного ответа"),
        attempts=outcome.attempts,
    )
    session.add(row)
    session.flush()
    if outcome.answer is not None:
        _save_sources(session, run, row.id, outcome.answer)


def _run_row(run: RunData) -> CollisionRun:
    sides, selection = run.inputs.sides, run.selection
    return CollisionRun(
        document_id=run.document_id,
        threshold=THRESHOLD,
        embedding_model=run.embedding_model,
        metric=METRIC,
        text_format=TEXT_FORMAT,
        compared_records=sum(side.kind is CollisionSideKind.RECORD for side in sides),
        compared_views=sum(side.kind is CollisionSideKind.VIEW for side in sides),
        context_records=run.inputs.context_count,
        local_pairs=selection.local_pairs,
        local_above=selection.local_above,
        category_pairs=selection.category_pairs,
        category_above=selection.category_above,
    )


def save_run(session: Session, run: RunData) -> RunResult:
    """Replace the document's stage 4.1 rows with this run (not committed).

    Args:
        session: Database session.
        run: The computed run.

    Returns:
        Pair, verdict and error counts.
    """
    clear_collisions(session, run.document_id)
    session.add(_run_row(run))
    view_ids = _save_views(session, run)
    for plan in run.plans:
        _save_pair(session, run, plan, view_ids)
    answers = [outcome.answer for outcome in run.outcomes.values()]
    verdicts = Counter(parse_answer(answer).verdict.value for answer in answers if answer is not None)
    return RunResult(len(run.plans), dict(verdicts), sum(answer is None for answer in answers))
