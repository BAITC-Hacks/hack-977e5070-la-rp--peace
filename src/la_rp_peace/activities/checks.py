"""Stage 3 completion checks (methodology §6): issues, record review status, document status.

A record that passed the code checks is ``checked``; an unresolved binding (executor outside
the registry, unclear participation), an unclear type or a note from the model makes it
``needs_review`` — technical success is never presented as confirmation by a person. The
document is ``done`` only when every block was processed without failures or open questions
and no record needs review.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from la_rp_peace.activities.extract import BlockOutcome
from la_rp_peace.activities.verify import CheckedBinding, CheckedRecord
from la_rp_peace.enums import ActivitiesStatus, ActivityIssueType, BlockStatus, Participation, ReviewStatus


@dataclass(frozen=True, slots=True)
class IssueDraft:
    """A stage 3 issue before it is stored."""

    issue_type: ActivityIssueType
    message: str
    is_blocking: bool = False


def binding_issues(binding: CheckedBinding) -> list[IssueDraft]:
    """Issues of one binding: executor outside the registry, unclear participation."""
    issues: list[IssueDraft] = []
    if binding.entity_id is None:
        issues.append(
            IssueDraft(
                ActivityIssueType.UNRESOLVED_ENTITY,
                f"Исполнитель «{binding.designation}» не найден в реестре объектов документа: {binding.note}",
            ),
        )
    if binding.participation is Participation.UNCLEAR:
        detail = f": {binding.note}" if binding.note else ""
        issues.append(
            IssueDraft(
                ActivityIssueType.UNCLEAR_PARTICIPATION,
                f"Неясен характер участия «{binding.designation}»{detail}",
            ),
        )
    return issues


def record_issues(record: CheckedRecord) -> list[IssueDraft]:
    """Issues of the record itself: unclear type and the model's notes."""
    issues = [IssueDraft(ActivityIssueType.UNCLEAR, note) for note in record.notes]
    if record.type_unclear:
        issues.insert(
            0, IssueDraft(ActivityIssueType.UNCLEAR_TYPE, f"Тип положения неясен (указан {record.record_type})")
        )
    return issues


def review_status(record: CheckedRecord) -> ReviewStatus:
    """``needs_review`` if the record or one of its bindings has an issue, else ``checked``."""
    if record_issues(record) or any(binding_issues(binding) for binding in record.bindings):
        return ReviewStatus.NEEDS_REVIEW
    return ReviewStatus.CHECKED


def block_issues(outcome: BlockOutcome) -> list[IssueDraft]:
    """Issues of a block: a failure is blocking, open questions are not."""
    if outcome.status is BlockStatus.FAILED:
        return [IssueDraft(ActivityIssueType.BLOCK_FAILED, f"{outcome.path}: {outcome.message}", is_blocking=True)]
    return [IssueDraft(ActivityIssueType.UNCLEAR, f"{outcome.path}: {item.message}") for item in outcome.unclear]


def document_status(outcomes: Sequence[BlockOutcome]) -> ActivitiesStatus:
    """``done`` only without failed or unclear blocks and without records that need review."""
    open_blocks = any(outcome.status in (BlockStatus.FAILED, BlockStatus.NEEDS_CLARIFICATION) for outcome in outcomes)
    blocking = any(issue.is_blocking for outcome in outcomes for issue in block_issues(outcome))
    unresolved = any(
        review_status(record) is ReviewStatus.NEEDS_REVIEW for outcome in outcomes for record in outcome.records
    )
    if open_blocks or blocking or unresolved:
        return ActivitiesStatus.NEEDS_REVIEW
    return ActivitiesStatus.DONE
