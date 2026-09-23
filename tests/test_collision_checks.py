"""Answer checks of stage 4.1: verdicts, explanation substance, verbatim sources of both sides."""

from typing import Any

import pytest

from la_rp_peace.collisions.checks import check_answer, explanation_problems
from la_rp_peace.collisions.pairs import Candidate, ScoredPair
from la_rp_peace.collisions.prompt import QuestionPlan
from la_rp_peace.collisions.sides import Side
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import CollisionSideKind, CollisionVerdict

NODES = {
    1: "3.1. Отдел А готовит квартальный отчёт о проверках для правления.",
    2: "3.2. Отдел Б готовит квартальный отчёт о проверках для правления.",
    3: "3.3. Отчёты по региону Север готовит Отдел А, по региону Юг — Отдел Б.",
}
EXPLANATION = (
    "Обе стороны независимо обязаны готовить один и тот же квартальный отчёт о проверках для правления, "
    "документ не распределяет между ними части этой работы."
)


def _side(key: str) -> Side:
    return Side(key, CollisionSideKind.RECORD, "0" * 16, (int(key[1:]),), (), "function", "готовит отчёт", "specific",
                "individual", "отдел", (), (), (), ())  # fmt: skip


def _plan() -> QuestionPlan:
    candidate = Candidate(_side("R1"), _side("R2"), ())
    return QuestionPlan("q1", ScoredPair(candidate, 0.9), frozenset({1}), frozenset({2}), "")


def _source(node: int, quote: str, *supports: str) -> dict[str, Any]:
    return {"node_id": node, "quote": quote, "supports": list(supports)}


def _check(**answer: Any) -> list[str]:
    raw = {"question_id": "q1", "verdict": "collision", "explanation": EXPLANATION, "sources": []} | answer
    return check_answer(raw, _plan(), SourceVerifier(NODES))


BOTH_SIDES = [
    _source(1, "Отдел А готовит квартальный отчёт", "side_a"),
    _source(2, "Отдел Б готовит квартальный отчёт", "side_b"),
]


def test_valid_collision_is_accepted() -> None:
    assert _check(sources=BOTH_SIDES) == []


def test_collision_needs_a_source_of_each_side_in_its_own_nodes() -> None:
    only_a = _check(sources=BOTH_SIDES[:1])
    wrong_node = _check(sources=[BOTH_SIDES[0], _source(3, "по региону Юг — Отдел Б", "side_b")])

    assert only_a == ["для collision нужен источник side_b из узлов стороны B [2]"]
    assert wrong_node == ["для collision нужен источник side_b из узлов стороны B [2]"]


def test_quotes_must_be_verbatim_in_this_document() -> None:
    errors = _check(sources=[*BOTH_SIDES, _source(1, "Отдел А пишет отчёт", "context"), _source(99, "x", "context")])

    assert any("не найдена дословно в узле 1" in error for error in errors)
    assert any("узел 99 не относится к текущему документу" in error for error in errors)


def test_structure_and_verdict_are_validated() -> None:
    assert any("verdict" in error for error in _check(verdict="maybe"))
    assert any("supports" in error for error in _check(sources=[_source(1, "Отдел А", "formulation")]))
    assert any("extra" in error.casefold() for error in _check(sources=BOTH_SIDES, comment="x"))


@pytest.mark.parametrize(
    "explanation",
    ["Тексты похожи.", "Тексты похожи, сходство 0.99, это коллизия.", "Формулировки практически совпадают (95%)."],
)
def test_similarity_is_not_an_explanation(explanation: str) -> None:
    assert explanation_problems(CollisionVerdict.COLLISION, explanation) != []
    assert _check(explanation=explanation, sources=BOTH_SIDES) != []


def test_no_collision_needs_a_source_of_the_distinction() -> None:
    explanation = "Отдел А готовит отчёт по региону Север, Отдел Б — по региону Юг: предмет работы разграничен."
    without = _check(verdict="no_collision", explanation=explanation)
    with_source = _check(
        verdict="no_collision",
        explanation=explanation,
        sources=[_source(3, "по региону Север готовит Отдел А", "side_a", "context")],
    )

    assert without == ["для no_collision нужен хотя бы один проверяемый источник разграничения"]
    assert with_source == []


def test_insufficient_data_must_name_what_is_missing() -> None:
    vague = "Стороны готовят отчёт для правления, но сделать однозначный вывод о пересечении ответственности сложно."
    specific = "В документе не указана область отчёта каждой стороны, поэтому нельзя определить пересечение работы."

    assert any("каких сведений не хватает" in e for e in _check(verdict="insufficient_data", explanation=vague))
    assert _check(verdict="insufficient_data", explanation=specific) == []
