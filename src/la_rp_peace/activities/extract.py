"""Ask the model for one block's records, check the answer, retry with feedback, keep the best.

One attempt = model answer → JSON and schema → code checks (``verify.check_answer``). Problems
go back to the model until the answer passes or ``retries`` corrected answers were requested.
A block whose model call fails, or whose answers never pass, is ``failed`` — never ``none`` —
and keeps only the records of its best attempt that passed their own checks.
"""

import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from la_rp_peace.activities.answers import BlockAnswer, UnclearIn
from la_rp_peace.activities.prompt import feedback_message
from la_rp_peace.activities.verify import BlockScope, CheckedRecord, check_answer
from la_rp_peace.entities.blocks import Block
from la_rp_peace.enums import BlockStatus
from la_rp_peace.llm import ChatModel, ChatModelError, Message
from la_rp_peace.logging_config import get_logger

log = get_logger(__name__)

_SUMMARY_ERRORS = 5


@dataclass(slots=True)
class Attempt:
    """Everything produced from one model answer; ``errors`` empty means it is accepted."""

    answer: BlockAnswer | None = None
    records: list[CheckedRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BlockOutcome:
    """Result of one block.

    Attributes:
        root_id: Node the block's processing mark is stored for.
        path: Human-readable place of that node.
        status: found, none, needs_clarification or failed.
        records: Verified records.
        unclear: Cases the model could not settle.
        errors: Check problems left in the kept answer (only for failed blocks).
        attempts: Model answers requested.
        message: Why the block failed or needs clarification.
    """

    root_id: int
    path: str
    status: BlockStatus
    records: tuple[CheckedRecord, ...]
    unclear: tuple[UnclearIn, ...]
    errors: tuple[str, ...]
    attempts: int
    message: str | None


def evaluate(content: str, scope: BlockScope) -> Attempt:
    """Parse and check one model answer.

    Args:
        content: The model's reply.
        scope: What the answer may refer to.

    Returns:
        The attempt; ``errors`` is empty when the answer is fully acceptable.
    """
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        return Attempt(errors=[f"Ответ не является JSON: {exc}"])
    try:
        answer = BlockAnswer.model_validate(raw)
    except ValidationError as exc:
        return Attempt(errors=[f"{'.'.join(map(str, err['loc'])) or 'ответ'}: {err['msg']}" for err in exc.errors()])
    records, errors = check_answer(answer, scope)
    return Attempt(answer, records, errors)


def _rank(attempt: Attempt) -> tuple[bool, int, int]:
    """Prefer a parsed answer, then fewer errors, then more verified records."""
    return attempt.answer is not None, -len(attempt.errors), len(attempt.records)


def _outcome(block: Block, path: str, attempt: Attempt, attempts: int, failure: str | None) -> BlockOutcome:
    unclear = tuple(attempt.answer.unclear) if attempt.answer is not None else ()
    message: str | None = failure
    status = BlockStatus.FAILED
    if failure is None and attempt.answer is not None:
        status = BlockStatus(attempt.answer.block_status)
        message = "; ".join(item.message for item in unclear) or None
    return BlockOutcome(
        root_id=block.root_id,
        path=path,
        status=status,
        records=tuple(attempt.records),
        unclear=unclear,
        errors=tuple(attempt.errors) if failure is not None else (),
        attempts=attempts,
        message=message,
    )


def extract_block(
    model: ChatModel, opening: list[Message], block: Block, path: str, scope: BlockScope, retries: int
) -> BlockOutcome:
    """Extract the records of one block.

    Args:
        model: The chat model.
        opening: System and user messages for the block.
        block: The block.
        path: Human-readable place of the block's root node.
        scope: What the answer may refer to.
        retries: Corrected answers to request after the first.

    Returns:
        The block's outcome.
    """
    messages = list(opening)
    best = Attempt(errors=["модель не ответила"])
    for number in range(1, retries + 2):
        try:
            content = model.complete(messages)
        except ChatModelError as exc:
            log.warning("activity_block_model_failed", node_id=block.root_id, attempt=number, error=str(exc))
            return _outcome(block, path, best, number, f"Ошибка обращения к модели: {exc}")
        attempt = evaluate(content, scope)
        log.info("activity_block_attempt", node_id=block.root_id, attempt=number, errors=len(attempt.errors))
        if number == 1 or _rank(attempt) >= _rank(best):
            best = attempt
        if not attempt.errors:
            return _outcome(block, path, attempt, number, None)
        messages += [Message("assistant", content), feedback_message(attempt.errors)]
    summary = "; ".join(best.errors[:_SUMMARY_ERRORS])
    return _outcome(block, path, best, retries + 1, f"Ответ не прошёл проверки за {retries + 1} попыток: {summary}")
