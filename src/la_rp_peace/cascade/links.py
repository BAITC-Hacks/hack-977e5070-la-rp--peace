"""Verification of the proposed links and the final decision per child function (methodology 4.2 §3–§5).

Only the single best candidate between 0.50 (exclusive) and 0.85 (inclusive) is asked about.
The model answers with a verdict and nothing else that could change the link: an answer with
another parent, extra functions or unknown fields is invalid and asked again. A question left
without a valid answer becomes an ``error`` link, one that was never asked a ``pending`` link —
never a rejection and never «no pair».
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from la_rp_peace.cascade.matching import Choice
from la_rp_peace.cascade.prompt import SYSTEM_PROMPT, Citation, question_id, render_question
from la_rp_peace.enums import CascadeDecision, CascadeLinkStatus, CascadeVerdict
from la_rp_peace.llm import ChatModel
from la_rp_peace.models import ActivityRecord, Entity
from la_rp_peace.verification import Answer, Outcome, Question, ask_in_batches

_ANSWER_FIELDS = frozenset({"question_id", "verdict", "explanation"})
_VERDICTS = frozenset(verdict.value for verdict in CascadeVerdict)


@dataclass(frozen=True, slots=True)
class LinkResult:
    """The decision for one child function.

    Attributes:
        choice: The child function and its best candidate.
        decision: ``auto`` above 0.85, ``llm`` when a question was asked, ``none`` otherwise.
        status: ``accepted`` gives the child function its parent; everything else leaves it without.
        verdict: The model's verdict when one was obtained.
        explanation: The model's short explanation, if given.
        error: Why the verification produced no verdict.
        attempts: Requests spent on the question.
    """

    choice: Choice
    decision: CascadeDecision
    status: CascadeLinkStatus
    verdict: CascadeVerdict | None = None
    explanation: str | None = None
    error: str | None = None
    attempts: int = 0


def check_answer(_question: Question, answer: Answer) -> list[str]:
    """Validate one answer: a known verdict, an optional short explanation, no other fields."""
    problems: list[str] = []
    extra = sorted(set(answer) - _ANSWER_FIELDS)
    if extra:
        problems.append(f"Недопустимые поля {extra}: нужен только вердикт по предложенной связи")
    if answer.get("verdict") not in _VERDICTS:
        problems.append(f"verdict должен быть confirmed или rejected, получено {answer.get('verdict')!r}")
    explanation = answer.get("explanation")
    if explanation is not None and not isinstance(explanation, str):
        problems.append("explanation должно быть строкой")
    return problems


def verify(
    model: ChatModel,
    choices: Sequence[Choice],
    records: Mapping[int, ActivityRecord],
    entities: Mapping[int, Entity],
    citations: Mapping[int, Sequence[Citation]],
    embedding_model: str,
    retries: int,
) -> dict[str, Outcome]:
    """Ask one question per choice that needs verification, in batches of 10.

    Args:
        model: The chat model.
        choices: All choices; only those with ``needs_question`` are asked about.
        records: Activity records by id (for the parent functions).
        entities: Entities by id.
        citations: Verbatim quotes by record id.
        embedding_model: Model of the similarity scores.
        retries: Corrected replies per batch after the first.

    Returns:
        Outcome by question id.
    """
    questions = [
        Question(
            question_id(choice.child.id),
            render_question(choice, records[choice.parent_record_id], entities, citations, embedding_model),
        )
        for choice in choices
        if choice.needs_question and choice.parent_record_id is not None
    ]
    if not questions:
        return {}
    return ask_in_batches(model, SYSTEM_PROMPT, questions, check_answer, retries)


def decide(choice: Choice, outcomes: Mapping[str, Outcome]) -> LinkResult:
    """Turn a choice (and its verification outcome, if asked) into the link decision."""
    if choice.tied:
        return LinkResult(choice, CascadeDecision.NONE, CascadeLinkStatus.AMBIGUOUS)
    if choice.auto_accepted:
        return LinkResult(choice, CascadeDecision.AUTO, CascadeLinkStatus.ACCEPTED)
    if not choice.needs_question:
        return LinkResult(choice, CascadeDecision.NONE, CascadeLinkStatus.NOT_FOUND)
    outcome = outcomes.get(question_id(choice.child.id))
    if outcome is None:
        return LinkResult(choice, CascadeDecision.LLM, CascadeLinkStatus.PENDING, error="Вопрос не был задан")
    if outcome.answer is None:
        return LinkResult(
            choice, CascadeDecision.LLM, CascadeLinkStatus.ERROR, error=outcome.error, attempts=outcome.attempts
        )
    verdict = CascadeVerdict(outcome.answer["verdict"])
    explanation = outcome.answer.get("explanation") or None
    status = CascadeLinkStatus.ACCEPTED if verdict is CascadeVerdict.CONFIRMED else CascadeLinkStatus.NOT_CONFIRMED
    return LinkResult(choice, CascadeDecision.LLM, status, verdict, explanation, None, outcome.attempts)
