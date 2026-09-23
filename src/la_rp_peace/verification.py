"""Batched verification questions for the analysis stages (methodology 4.1 §5–§6, 4.2 §4).

Questions go to the model in batches of 10. The reply must be a JSON object with an
``answers`` array holding exactly one answer per question of the batch. Valid answers are kept
at once; missing, duplicated, foreign or invalid answers are sent back with feedback and only
the unanswered questions are asked again. Whatever is still unanswered after the retry budget
ends as an *error* — never as a negative verdict.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from la_rp_peace.llm import ChatModel, ChatModelError, Message
from la_rp_peace.logging_config import get_logger

log = get_logger(__name__)

BATCH_SIZE = 10

type Answer = dict[str, Any]
type AnswerCheck = Callable[["Question", Answer], list[str]]


@dataclass(frozen=True, slots=True)
class Question:
    """One question: an id unique within the run and its rendered text."""

    question_id: str
    text: str


@dataclass(frozen=True, slots=True)
class Outcome:
    """The result for one question: a validated answer, or the reason there is none."""

    question_id: str
    answer: Answer | None
    error: str | None
    attempts: int


def _render(questions: Sequence[Question]) -> str:
    ids = ", ".join(question.question_id for question in questions)
    parts = [f"Вопросов: {len(questions)} ({ids}). Ответьте ровно один раз на каждый question_id."]
    parts += [f"### question_id: {question.question_id}\n{question.text}" for question in questions]
    return "\n\n".join(parts)


def _answers(content: str) -> tuple[list[Any], list[str]]:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        return [], [f"Ответ не является JSON: {exc}"]
    if not isinstance(raw, dict) or not isinstance(raw.get("answers"), list):
        return [], ["Ответ должен быть объектом с массивом answers"]
    return list(raw["answers"]), []


class _Batch:
    """Asks one batch until every question has a valid answer or the budget is spent."""

    def __init__(self, questions: Sequence[Question], check: AnswerCheck) -> None:
        self.pending = {question.question_id: question for question in questions}
        self.done: dict[str, Outcome] = {}
        self.problems: dict[str, list[str]] = {}
        self._check = check

    def absorb(self, content: str, attempt: int) -> list[str]:
        """Take the valid answers of a reply; return the problems to send back."""
        answers, general = _answers(content)
        seen: dict[str, int] = {}
        valid: dict[str, Answer] = {}
        self.problems = {}
        for item in answers:
            question_id = item.get("question_id") if isinstance(item, dict) else None
            if not isinstance(question_id, str) or (question_id not in self.pending and question_id not in self.done):
                general.append(f"Посторонний или пустой question_id: {question_id!r}")
                continue
            seen[question_id] = seen.get(question_id, 0) + 1
            if question_id in self.pending and isinstance(item, dict):
                errors = self._check(self.pending[question_id], item)
                if errors:
                    self.problems[question_id] = errors
                else:
                    valid[question_id] = item
        for question_id in self.pending:
            if seen.get(question_id, 0) > 1:
                valid.pop(question_id, None)
                self.problems[question_id] = ["Несколько ответов на один вопрос"]
            elif question_id not in seen:
                self.problems[question_id] = ["Нет ответа"]
        for question_id, answer in valid.items():
            self.done[question_id] = Outcome(question_id, answer, None, attempt)
            del self.pending[question_id]
        return general + [f"{qid}: {'; '.join(errors)}" for qid, errors in self.problems.items()]

    def fail_pending(self, reason: str, attempts: int) -> None:
        for question_id in list(self.pending):
            detail = "; ".join(self.problems.get(question_id, []))
            self.done[question_id] = Outcome(question_id, None, f"{reason}: {detail}" if detail else reason, attempts)
            del self.pending[question_id]


def _ask_batch(model: ChatModel, system_prompt: str, batch: _Batch, retries: int) -> None:
    messages = [Message("system", system_prompt), Message("user", _render(list(batch.pending.values())))]
    for attempt in range(1, retries + 2):
        try:
            content = model.complete(messages)
        except ChatModelError as exc:
            batch.fail_pending(f"Ошибка вызова модели: {exc}", attempt)
            return
        feedback = batch.absorb(content, attempt)
        log.info("verification_attempt", attempt=attempt, answered=len(batch.done), pending=len(batch.pending))
        if not batch.pending:
            return
        remaining = list(batch.pending.values())
        retry = "Исправьте и ответьте повторно ТОЛЬКО на эти вопросы:\n" + _render(remaining)
        messages += [
            Message("assistant", content),
            Message("user", "Проблемы ответа:\n- " + "\n- ".join(feedback) + "\n\n" + retry),
        ]
    batch.fail_pending(f"Нет корректного ответа за {retries + 1} попыток", retries + 1)


def ask_in_batches(
    model: ChatModel,
    system_prompt: str,
    questions: Sequence[Question],
    check: AnswerCheck,
    retries: int,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Outcome]:
    """Ask verification questions in batches and collect one outcome per question.

    Args:
        model: The chat model (JSON mode).
        system_prompt: Instructions, including the answer format of the stage.
        questions: Questions with unique ids.
        check: Validates one answer object for its question; returns problems (empty = valid).
        retries: Corrected replies to request per batch after the first.
        batch_size: Questions per request (10 by the methodology).

    Returns:
        Outcome by question id, for every question.

    Raises:
        ValueError: If question ids are not unique.
    """
    ids = [question.question_id for question in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("question_id must be unique")
    outcomes: dict[str, Outcome] = {}
    for start in range(0, len(questions), batch_size):
        batch = _Batch(questions[start : start + batch_size], check)
        _ask_batch(model, system_prompt, batch, retries)
        outcomes.update(batch.done)
    return outcomes
