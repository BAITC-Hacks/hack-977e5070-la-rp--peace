"""Save a stage 3 run: a block's verified result replaces that block's previous records.

Re-runs replace rather than add (methodology §6). For every block that produced a verified
answer, its new records are matched to the block's previous records by entity, type and
normalised formulation: a match keeps its id and gets the new fields, sources and issues;
previous records without a match (corrected or removed) are deleted. A block that failed keeps
its previous records untouched and is marked as a failed update; only a block without previous
records stores the verified records of its best failed attempt. Records of blocks that are no
longer planned are deleted. Block marks and block-level issues always describe the latest run.
"""

import json
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from la_rp_peace.activities.checks import IssueDraft, block_issues, record_issues, review_status
from la_rp_peace.activities.extract import BlockOutcome
from la_rp_peace.activities.verify import CheckedRecord
from la_rp_peace.enums import BlockStatus, ReviewStatus
from la_rp_peace.models import ActivityBlock, ActivityIssue, ActivityRecord, ActivitySource

RecordKey = tuple[int | None, str, str]


def clear_activities(session: Session, document_id: int) -> None:
    """Delete every stage 3 row of a document (not committed)."""
    session.execute(delete(ActivityIssue).where(ActivityIssue.document_id == document_id))
    session.execute(delete(ActivitySource).where(ActivitySource.document_id == document_id))
    session.execute(delete(ActivityRecord).where(ActivityRecord.document_id == document_id))
    session.execute(delete(ActivityBlock).where(ActivityBlock.document_id == document_id))


def _key(entity_id: int | None, record_type: str, formulation: str) -> RecordKey:
    return entity_id, record_type, " ".join(formulation.split()).casefold()


def _delete_records(session: Session, ids: Sequence[int]) -> None:
    if ids:
        session.execute(delete(ActivitySource).where(ActivitySource.record_id.in_(ids)))
        session.execute(delete(ActivityIssue).where(ActivityIssue.record_id.in_(ids)))
        session.execute(delete(ActivityRecord).where(ActivityRecord.id.in_(ids)))


def _add_issues(session: Session, document_id: int, issues: Sequence[IssueDraft], record_id: int | None) -> None:
    session.add_all(
        ActivityIssue(
            document_id=document_id,
            record_id=record_id,
            issue_type=issue.issue_type.value,
            message=issue.message,
            is_blocking=int(issue.is_blocking),
        )
        for issue in issues
    )


def _fill(row: ActivityRecord, record: CheckedRecord) -> None:
    row.entity_id = record.entity_id
    row.designation = record.designation
    row.record_type = record.record_type.value
    row.formulation = record.formulation
    row.specificity = record.specificity.value
    row.participation = record.participation.value
    row.participant_designation = record.participant_designation
    row.participant_entity_ids = json.dumps(list(record.participant_entity_ids))
    row.condition = record.condition
    row.deadline = record.deadline
    row.periodicity = record.periodicity
    row.note = record.note
    row.review_status = review_status(record).value


def _write_record(session: Session, document_id: int, row: ActivityRecord, record: CheckedRecord) -> None:
    _fill(row, record)
    session.add(row)
    session.flush()
    session.execute(delete(ActivitySource).where(ActivitySource.record_id == row.id))
    session.execute(delete(ActivityIssue).where(ActivityIssue.record_id == row.id))
    session.add_all(
        ActivitySource(
            document_id=document_id,
            record_id=row.id,
            node_id=source.node_id,
            quote=source.quote,
            quote_start=source.start,
            quote_end=source.end,
            supports=json.dumps(list(source.supports), ensure_ascii=False),
        )
        for source in record.sources
    )
    _add_issues(session, document_id, record_issues(record), row.id)


def _replace_block(
    session: Session, document_id: int, outcome: BlockOutcome, previous: Sequence[ActivityRecord]
) -> None:
    pool: dict[RecordKey, list[ActivityRecord]] = {}
    for row in previous:
        pool.setdefault(_key(row.entity_id, row.record_type, row.formulation), []).append(row)
    for record in outcome.records:
        matches = pool.get(_key(record.entity_id, record.record_type.value, record.formulation))
        row = matches.pop(0) if matches else ActivityRecord(document_id=document_id, block_node_id=outcome.root_id)
        _write_record(session, document_id, row, record)
    _delete_records(session, [row.id for rows in pool.values() for row in rows])


def save_outcomes(session: Session, document_id: int, outcomes: Sequence[BlockOutcome]) -> list[ReviewStatus]:
    """Apply a run's outcomes to the stored records (not committed).

    Args:
        session: Database session.
        document_id: The document.
        outcomes: Outcomes of all planned blocks, in order.

    Returns:
        Review status of every record the document has after the run.
    """
    existing = session.scalars(select(ActivityRecord).where(ActivityRecord.document_id == document_id)).all()
    planned = {outcome.root_id for outcome in outcomes}
    by_block: dict[int, list[ActivityRecord]] = {}
    for row in existing:
        by_block.setdefault(row.block_node_id, []).append(row)
    _delete_records(session, [row.id for row in existing if row.block_node_id not in planned])
    session.execute(delete(ActivityBlock).where(ActivityBlock.document_id == document_id))
    session.execute(
        delete(ActivityIssue).where(ActivityIssue.document_id == document_id, ActivityIssue.record_id.is_(None)),
    )
    for outcome in outcomes:
        previous = by_block.get(outcome.root_id, [])
        kept = outcome.status is BlockStatus.FAILED and bool(previous)
        if not kept:
            _replace_block(session, document_id, outcome, previous)
        session.add(
            ActivityBlock(
                document_id=document_id,
                node_id=outcome.root_id,
                status=outcome.status.value,
                message=outcome.message,
                attempts=outcome.attempts,
            ),
        )
        _add_issues(session, document_id, block_issues(outcome, kept_previous=kept), None)
    session.flush()
    statuses = session.scalars(select(ActivityRecord.review_status).where(ActivityRecord.document_id == document_id))
    return [ReviewStatus(value) for value in statuses]
