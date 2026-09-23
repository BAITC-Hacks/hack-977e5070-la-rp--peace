"""Code checks of stage 3 answers and the retry loop, on a small hand-made document."""

import json
from typing import Any

import pytest
from activity_script import binding, source

from la_rp_peace.activities.answers import BlockAnswer
from la_rp_peace.activities.checks import document_status, review_status
from la_rp_peace.activities.extract import extract_block
from la_rp_peace.activities.verify import BlockScope, RegistryEntry, check_answer
from la_rp_peace.entities.blocks import Block, BlockLine
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import ActivitiesStatus, BlockStatus
from la_rp_peace.llm import ChatModelError, Message

INTRO, CLAUSE, OTHER = 10, 11, 12
TEXTS = {
    INTRO: "5.7. Работники БВА имеют право:",
    CLAUSE: "5.7.1. запрашивать у должностных лиц Общества документы, необходимые для проверки;",
    OTHER: "9.4. Программа проверки утверждается Главным аудитором или уполномоченным им работником.",
}
SCOPE = BlockScope(
    SourceVerifier(TEXTS),
    {"E1": RegistryEntry(1, "Работники БВА"), "E2": RegistryEntry(2, "Главный аудитор")},
    frozenset({CLAUSE}),
)
BLOCK = Block(
    INTRO,
    (BlockLine(INTRO, "п. 5.7", TEXTS[INTRO], True), BlockLine(CLAUSE, "п. 5.7 › п. 5.7.1", TEXTS[CLAUSE], False)),
)


def _right(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "right",
        "formulation": "Работники БВА имеют право запрашивать у должностных лиц Общества документы",
        "bindings": [binding("E1", [source(INTRO, "Работники БВА имеют право", "binding")])],
        "sources": [
            source(INTRO, "имеют право", "type"),
            source(CLAUSE, "запрашивать у должностных лиц Общества документы", "formulation"),
        ],
    }
    return record | changes


def _check(*records: dict[str, Any], status: str = "found") -> tuple[int, list[str]]:
    answer = BlockAnswer.model_validate({"block_status": status, "records": list(records)})
    checked, errors = check_answer(answer, SCOPE)
    return len(checked), errors


def test_a_sourced_record_passes() -> None:
    assert _check(_right()) == (1, [])


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"sources": [source(CLAUSE, "запрашивать любые документы", "formulation", "type")]}, "не найдена в узле"),
        ({"sources": [source(999, "запрашивать", "formulation", "type")]}, "не относится к текущему документу"),
        (
            {"bindings": [binding("E7", [source(INTRO, "Работники БВА", "binding")])]},
            "E7 нет в реестре текущего документа",
        ),
        ({"condition": "при проведении проверки"}, "поле condition не подтверждено"),
        ({"periodicity": "ежемесячно"}, "поле periodicity не подтверждено"),
        ({"deadline": "  "}, "поле deadline пустое"),
        (
            {"sources": [source(INTRO, "Работники БВА имеют право", "formulation", "type")]},
            "строками «(контекст)»",
        ),
        ({"bindings": [binding("E1", [])]}, "не подтверждена источником (supports: binding)"),
        ({"bindings": [binding(None, [], designation="уполномоченный работник")]}, "нужно пояснение"),
        ({"bindings": [binding(None, [], note="не назван")]}, "нужно исходное обозначение"),
        (
            {"bindings": [binding("E1", [source(INTRO, "Работники БВА", "binding")], "alternative")]},
            "минимум двух привязок",
        ),
        (
            {"sources": [source(CLAUSE, "запрашивать", "formulation", "type", "executor")]},
            "недопустимые значения supports",
        ),
    ],
)
def test_problems_are_reported_and_the_record_dropped(changes: dict[str, Any], expected: str) -> None:
    kept, errors = _check(_right(**changes))

    assert kept == 0
    assert any(expected in error for error in errors), errors


def test_another_clause_of_the_document_may_support_a_field() -> None:
    record = _right(
        condition="по согласованию с Главным аудитором",
        sources=[*_right()["sources"], source(OTHER, "утверждается Главным аудитором", "condition")],
    )

    assert _check(record) == (1, [])


def test_block_status_must_match_the_records() -> None:
    assert "block_status «none», но записи перечислены" in _check(_right(), status="none")[1]
    assert _check(status="found")[1] == ["block_status «found», но записей нет — используйте «none»"]
    assert _check(status="needs_clarification")[1][0].startswith("block_status «needs_clarification» без замечаний")


def test_blank_binding_texts_are_absent() -> None:
    blank = binding("E1", [source(INTRO, "Работники БВА", "binding")], condition=" ", note="", designation=" ")
    answer = BlockAnswer.model_validate({"block_status": "found", "records": [_right(bindings=[blank])]})
    (record,), errors = check_answer(answer, SCOPE)

    assert errors == []
    assert (record.bindings[0].condition, record.bindings[0].note) == (None, None)
    assert record.bindings[0].designation == "Работники БВА"


def test_unresolved_executor_needs_review() -> None:
    unresolved = binding(None, [], designation="уполномоченный работник", note="нет в реестре")
    answer = BlockAnswer.model_validate({"block_status": "found", "records": [_right(bindings=[unresolved])]})
    (record,), errors = check_answer(answer, SCOPE)

    assert errors == []
    assert (record.bindings[0].entity_id, record.bindings[0].designation) == (None, "уполномоченный работник")
    assert review_status(record) == "needs_review"


class _Replies:
    def __init__(self, *replies: dict[str, Any] | Exception) -> None:
        self.replies = list(replies)
        self.seen: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply, ensure_ascii=False)


OPENING = [Message("system", "rules"), Message("user", BLOCK.render())]


def test_errors_go_back_to_the_model_until_the_answer_passes() -> None:
    invented = _right(sources=[source(CLAUSE, "запрашивать всё", "formulation", "type")])
    model = _Replies({"block_status": "found", "records": [invented]}, {"block_status": "found", "records": [_right()]})

    outcome = extract_block(model, OPENING, BLOCK, "п. 5.7", SCOPE, retries=2)

    assert (outcome.status, outcome.attempts, len(outcome.records)) == (BlockStatus.FOUND, 2, 1)
    assert "цитата «запрашивать всё» не найдена" in model.seen[1][-1].content
    assert model.seen[1][-2].role == "assistant"


def test_exhausted_retries_fail_the_block_but_keep_verified_records() -> None:
    broken = _right(bindings=[binding("E9", [source(INTRO, "Работники БВА", "binding")])])
    answer = {"block_status": "found", "records": [_right(), broken]}
    model = _Replies(answer, answer)

    outcome = extract_block(model, OPENING, BLOCK, "п. 5.7", SCOPE, retries=1)

    assert (outcome.status, outcome.attempts, len(outcome.records)) == (BlockStatus.FAILED, 2, 1)
    assert outcome.message is not None
    assert "E9 нет в реестре" in outcome.message
    assert document_status([outcome]) is ActivitiesStatus.NEEDS_REVIEW


def test_model_error_fails_the_block_and_invalid_json_is_retried() -> None:
    model = _Replies({"records": "oops"}, ChatModelError("timeout"))

    outcome = extract_block(model, OPENING, BLOCK, "п. 5.7", SCOPE, retries=2)

    assert (outcome.status, outcome.attempts, outcome.records) == (BlockStatus.FAILED, 2, ())
    assert outcome.message == "Ошибка обращения к модели: timeout"
    assert "block_status" in model.seen[1][-1].content


def test_empty_block_is_done() -> None:
    outcome = extract_block(_Replies({"block_status": "none"}), OPENING, BLOCK, "п. 5.7", SCOPE, retries=0)

    assert (outcome.status, outcome.message) == (BlockStatus.NONE, None)
    assert document_status([outcome]) is ActivitiesStatus.DONE
