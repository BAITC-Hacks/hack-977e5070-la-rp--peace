"""Ask the model, check the answer, feed problems back, retry (methodology §8).

Same loop as stage 1 (``ingestion.analysis``): answer → JSON shape → code checks → feedback
message listing every problem → corrected answer, up to ``retries`` times. Only an answer
without problems is returned for applying; otherwise the problems of the best attempt are.
A failed request is reported as such, never as an empty answer.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from la_rp_peace.entities.prompt import feedback_message
from la_rp_peace.llm import ChatModel, ChatModelError, Message
from la_rp_peace.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Outcome[T: BaseModel]:
    """Result of a conversation: an accepted answer, or why there is none."""

    answer: T | None
    attempts: int
    errors: list[str] = field(default_factory=list)
    request_error: str | None = None


def parse_answer[T: BaseModel](content: str, shape: type[T]) -> tuple[T | None, list[str]]:
    """Decode a JSON reply into ``shape``.

    Returns:
        The answer, or None with the problems found.
    """
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, [f"Ответ не является JSON: {exc}"]
    try:
        return shape.model_validate(raw), []
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, err['loc'])) or 'ответ'}: {err['msg']}" for err in exc.errors()]


def converse[T: BaseModel](
    model: ChatModel,
    messages: list[Message],
    shape: type[T],
    check: Callable[[T], list[str]],
    retries: int,
) -> Outcome[T]:
    """Get an answer that passes ``check``.

    Args:
        model: The chat model.
        messages: The opening conversation.
        shape: Expected answer model.
        check: Code checks of a parsed answer; returns problems for the model.
        retries: Corrected answers to request after the first.

    Returns:
        The outcome; ``answer`` is set only when an attempt had no problems.
    """
    best: list[str] | None = None
    conversation = list(messages)
    for number in range(1, retries + 2):
        try:
            content = model.complete(conversation)
        except ChatModelError as exc:
            log.warning("entity_request_failed", attempt=number, error=str(exc))
            return Outcome(None, number, best or [], str(exc))
        answer, errors = parse_answer(content, shape)
        if answer is not None:
            errors = check(answer)
        log.info("entity_attempt", shape=shape.__name__, attempt=number, errors=len(errors))
        if answer is not None and not errors:
            return Outcome(answer, number)
        if best is None or len(errors) <= len(best):
            best = errors
        conversation += [Message("assistant", content), feedback_message(errors)]
    return Outcome(None, retries + 1, best or [])
