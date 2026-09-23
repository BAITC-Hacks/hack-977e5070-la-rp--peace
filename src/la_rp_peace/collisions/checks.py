"""Checks of one verification answer (methodology 4.1 §5–§6).

Structure: ``question_id``, ``verdict`` (collision | no_collision | insufficient_data),
``explanation`` and ``sources`` ``{node_id, quote, supports}`` with ``supports`` from
side_a / side_b / context. Every source must be a node of the current document containing the
quote verbatim (``SourceVerifier``).

Explanation rule: similarity statements («тексты похожи», «формулировки совпадают», «высокое
сходство», percentages) are removed first; what remains must hold at least
``MIN_EXPLANATION_WORDS`` words of three or more letters. So «Тексты похожи, это коллизия» is
refused while a sentence that names the work, the area and why it overlaps (or does not) passes.
``insufficient_data`` must also say what is missing (a phrase like «не указан», «отсутствует»,
«неизвестно»).

Source rule: a ``collision`` needs, for EACH side, a verified source marked ``side_a`` (resp.
``side_b``) whose node is one of that side's own stage 3 source nodes, so the overlap rests on the
words that assign the work to both sides. A ``no_collision`` needs at least one verified source
(the ground of the distinction); ``insufficient_data`` may cite nothing.
"""

from typing import Literal

import regex
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from la_rp_peace.collisions.prompt import SUPPORT_SIDE_A, SUPPORT_SIDE_B, QuestionPlan
from la_rp_peace.entities.answers import SourceIn
from la_rp_peace.entities.verify import SourceVerifier, VerifiedSource
from la_rp_peace.enums import CollisionVerdict
from la_rp_peace.verification import Answer, AnswerCheck, Question

MIN_EXPLANATION_WORDS = 8

_SIMILARITY = regex.compile(
    r"(?:(?:тексты|текст|формулировки|формулировка|функции|функция|обязанности|записи|назначения|описания)\s+)?"
    r"(?:(?:очень|почти|практически|полностью|во\s+многом)\s+)?"
    r"(?:похожи|похож[аеи]?|схожи|схож[аеи]?|совпадают|совпадает|идентичны|одинаковы|аналогичны)"
    r"|(?:высок\w*|значительн\w*|большо\w*)\s+(?:сходств\w*|оценк\w*|схож\w*|степен\w*\s+сходств\w*)"
    r"|сходств\w*(?:\s+(?:эмбеддинг\w*|текст\w*|формулировок))?"
    r"|\d+(?:[.,]\d+)?\s*%?",
    regex.IGNORECASE,
)
_WORD = regex.compile(r"\p{L}{3,}")
_MISSING = regex.compile(
    r"не\s+(?:указан\w*|установлен\w*|определ\w*|раскрыт\w*|ясн\w*|известн\w*|уточн\w*|следует|приведен\w*)"
    r"|отсутств\w*|неизвестн\w*|неясн\w*|не\s+хватает|недостаточн\w*|без\s+указани\w*"
    r"|нет\s+(?:сведений|данных|информации|указани\w*)",
    regex.IGNORECASE,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollisionSourceIn(_Strict):
    """A cited fragment of the current document."""

    node_id: int
    quote: str = Field(min_length=1)
    supports: list[Literal["side_a", "side_b", "context"]] = Field(min_length=1)


class CollisionAnswer(_Strict):
    """The model's answer to one question."""

    question_id: str
    verdict: CollisionVerdict
    explanation: str
    sources: list[CollisionSourceIn] = Field(default_factory=list)


def explanation_problems(verdict: CollisionVerdict, explanation: str) -> list[str]:
    """Problems of the explanation's content (see the module docstring for the rule)."""
    substance = _WORD.findall(_SIMILARITY.sub(" ", explanation))
    problems: list[str] = []
    if len(substance) < MIN_EXPLANATION_WORDS:
        problems.append(
            "объяснение не обосновывает вывод: сходство текстов или оценка эмбеддингов не доказательство; "
            "укажите, за какую работу отвечает каждая сторона и где ответственность пересекается или разграничена",
        )
    if verdict is CollisionVerdict.INSUFFICIENT_DATA and not _MISSING.search(explanation):
        problems.append("для insufficient_data укажите, каких сведений не хватает (например, «не указана область»)")
    return problems


def verify_sources(answer: CollisionAnswer, verifier: SourceVerifier, errors: list[str]) -> list[VerifiedSource]:
    """Verify every source of an answer against the document; failures go to ``errors``."""
    cited = [SourceIn(node_id=s.node_id, quote=s.quote, supports=list(s.supports)) for s in answer.sources]
    return verifier.verify_all(cited, "источник", errors)


def _covers(sources: list[VerifiedSource], support: str, nodes: frozenset[int]) -> bool:
    return any(support in source.supports and source.node_id in nodes for source in sources)


def _source_problems(answer: CollisionAnswer, plan: QuestionPlan, verified: list[VerifiedSource]) -> list[str]:
    if answer.verdict is CollisionVerdict.COLLISION:
        problems = []
        if not _covers(verified, SUPPORT_SIDE_A, plan.a_nodes):
            problems.append(f"для collision нужен источник side_a из узлов стороны A {sorted(plan.a_nodes)}")
        if not _covers(verified, SUPPORT_SIDE_B, plan.b_nodes):
            problems.append(f"для collision нужен источник side_b из узлов стороны B {sorted(plan.b_nodes)}")
        return problems
    if answer.verdict is CollisionVerdict.NO_COLLISION and not verified:
        return ["для no_collision нужен хотя бы один проверяемый источник разграничения"]
    return []


def parse_answer(raw: Answer) -> CollisionAnswer:
    """Parse an answer object.

    Raises:
        ValidationError: If the structure or the verdict is invalid.
    """
    return CollisionAnswer.model_validate(raw)


def check_answer(raw: Answer, plan: QuestionPlan, verifier: SourceVerifier) -> list[str]:
    """Validate one answer for its question.

    Args:
        raw: The answer object from the reply.
        plan: The question with its sides' nodes.
        verifier: Quote resolver of the current document.

    Returns:
        Problems for the model; empty if the answer is accepted.
    """
    try:
        answer = parse_answer(raw)
    except ValidationError as exc:
        return [f"{'.'.join(map(str, error['loc'])) or 'ответ'}: {error['msg']}" for error in exc.errors()]
    errors = explanation_problems(answer.verdict, answer.explanation)
    verified = verify_sources(answer, verifier, errors)
    return errors + _source_problems(answer, plan, verified)


def answer_check(plans: dict[str, QuestionPlan], verifier: SourceVerifier) -> AnswerCheck:
    """The ``ask_in_batches`` callback for the run's questions."""

    def check(question: Question, raw: Answer) -> list[str]:
        return check_answer(raw, plans[question.question_id], verifier)

    return check
