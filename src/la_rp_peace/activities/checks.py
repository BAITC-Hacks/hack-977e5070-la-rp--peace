"""Stage 3 completion checks (methodology §6): issues, record review status, document status.

A record that passed the code checks is ``checked``; an unresolved participant (role or group
remainder outside the registry), unclear participation, an unclear type, a specificity that
needs clarification or a note from the model makes it ``needs_review`` — technical success is
never presented as confirmation by a person. The document is ``done`` only when every block was
processed without failures or open questions and no record needs review.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from la_rp_peace.activities.extract import BlockOutcome
from la_rp_peace.activities.verify import CheckedRecord
from la_rp_peace.enums import (
    ActivitiesStatus,
    ActivityIssueType,
    BlockStatus,
    Participation,
    ReviewStatus,
    Specificity,
)


@dataclass(frozen=True, slots=True)
class IssueDraft:
    """A stage 3 issue before it is stored."""

    issue_type: ActivityIssueType
    message: str
    is_blocking: bool = False


def record_issues(record: CheckedRecord) -> list[IssueDraft]:
    """Issues of one record: unresolved participant, unclear participation, type or specificity, notes."""
    issues: list[IssueDraft] = []
    if record.entity_id is None:
        message = f"Участник «{record.designation}» не найден в реестре объектов документа: {record.note}"
        issues.append(IssueDraft(ActivityIssueType.UNRESOLVED_ENTITY, message))
    if record.participation is Participation.UNCLEAR:
        message = f"Неясен характер участия: «{record.participant_designation}»"
        issues.append(IssueDraft(ActivityIssueType.UNCLEAR_PARTICIPATION, message))
    if record.type_unclear:
        issues.append(IssueDraft(ActivityIssueType.UNCLEAR_TYPE, f"Тип положения неясен (указан {record.record_type})"))
    if record.specificity is Specificity.NEEDS_CLARIFICATION:
        issues.append(IssueDraft(ActivityIssueType.UNCLEAR, "Неясно, раскрыто ли конкретное содержание положения"))
    issues += [IssueDraft(ActivityIssueType.UNCLEAR, note) for note in record.notes]
    return issues


def review_status(record: CheckedRecord) -> ReviewStatus:
    """``needs_review`` if the record has an issue, else ``checked``."""
    return ReviewStatus.NEEDS_REVIEW if record_issues(record) else ReviewStatus.CHECKED


def block_issues(outcome: BlockOutcome, kept_previous: bool = False) -> list[IssueDraft]:
    """Issues of a block: a failure is blocking, open questions are not.

    Args:
        outcome: The block's outcome.
        kept_previous: The block failed and its records from the previous run were kept.
    """
    if outcome.status is BlockStatus.FAILED:
        kept = " Обновление не выполнено: сохранены записи предыдущего разбора." if kept_previous else ""
        return [IssueDraft(ActivityIssueType.BLOCK_FAILED, f"{outcome.path}: {outcome.message}{kept}", True)]
    return [IssueDraft(ActivityIssueType.UNCLEAR, f"{outcome.path}: {item.message}") for item in outcome.unclear]


def document_status(outcomes: Sequence[BlockOutcome], statuses: Sequence[ReviewStatus]) -> ActivitiesStatus:
    """``done`` only without failed or unclear blocks and without stored records that need review.

    Args:
        outcomes: Outcomes of all planned blocks of the run.
        statuses: Review status of every record the document has after the run.
    """
    open_blocks = any(outcome.status in (BlockStatus.FAILED, BlockStatus.NEEDS_CLARIFICATION) for outcome in outcomes)
    if open_blocks or ReviewStatus.NEEDS_REVIEW in statuses:
        return ActivitiesStatus.NEEDS_REVIEW
    return ActivitiesStatus.DONE
