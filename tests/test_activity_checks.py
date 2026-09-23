"""Code checks of stage 3 answers, expansion into records per entity, and the retry loop."""

import json
from typing import Any

import pytest
from activity_script import participant, provision, source

from la_rp_peace.activities.answers import BlockAnswer
from la_rp_peace.activities.checks import document_status, review_status
from la_rp_peace.activities.extract import extract_block
from la_rp_peace.activities.store import provision_key
from la_rp_peace.activities.verify import BlockScope, RegistryEntry, check_answer
from la_rp_peace.entities.blocks import Block, BlockLine
from la_rp_peace.entities.verify import SourceVerifier
from la_rp_peace.enums import ActivitiesStatus, BlockStatus, ReviewStatus
from la_rp_peace.llm import ChatModelError, Message

INTRO, CLAUSE, OTHER, JOINT = 10, 11, 12, 13
TEXTS = {
    INTRO: "5.7. Работники БВА имеют право:",
    CLAUSE: "5.7.1. запрашивать у должностных лиц Общества документы, необходимые для проверки;",
    OTHER: "9.4. Программа проверки утверждается Главным аудитором или уполномоченным им работником.",
    JOINT: "7.1. Специалисты А и Б совместно готовят отчёт.",
}
SCOPE = BlockScope(
    SourceVerifier(TEXTS),
    {
        "E1": RegistryEntry(1, "Директор ДИТААД"),
        "E2": RegistryEntry(2, "Главный аудитор"),
        "E3": RegistryEntry(3, "Специалист А"),
        "E4": RegistryEntry(4, "Специалист Б"),
    },
    frozenset({CLAUSE, JOINT}),
)
BLOCK = Block(
    INTRO,
    (BlockLine(INTRO, "п. 5.7", TEXTS[INTRO], True), BlockLine(CLAUSE, "п. 5.7 › п. 5.7.1", TEXTS[CLAUSE], False)),
)


def _right(**changes: Any) -> dict[str, Any]:
    director = participant("E1", [source(INTRO, "Работники БВА", "entity")])
    item = provision(
        "right",
        "Работники БВА имеют право запрашивать у должностных лиц Общества документы",
        [director],
        [
            source(INTRO, "имеют право", "type"),
            source(CLAUSE, "запрашивать у должностных лиц Общества документы", "formulation"),
        ],
        designation="Работники БВА",
    )
    return item | changes


def _check(*provisions: dict[str, Any], status: str = "found") -> tuple[int, list[str]]:
    answer = BlockAnswer.model_validate({"block_status": status, "provisions": list(provisions)})
    records, errors = check_answer(answer, SCOPE)
    return len(records), errors


def test_a_sourced_provision_passes() -> None:
    assert _check(_right()) == (1, [])


UNRESOLVED = participant(None, [], designation="уполномоченный работник", note="нет в реестре")


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"sources": [source(CLAUSE, "запрашивать любые документы", "formulation", "type")]}, "не найдена"),
        ({"sources": [source(999, "запрашивать", "formulation", "type")]}, "не относится к текущему документу"),
        (
            {"participants": [participant("E7", [source(INTRO, "Работники БВА", "entity")])]},
            "E7 нет в реестре текущего документа",
        ),
        ({"condition": "при проведении проверки"}, "поле condition не подтверждено"),
        ({"periodicity": "ежемесячно"}, "поле periodicity не подтверждено"),
        ({"deadline": "  "}, "поле deadline пустое"),
        ({"specificity": "generalized"}, "поле specificity не подтверждено"),
        (
            {"sources": [source(INTRO, "Работники БВА имеют право", "formulation", "type")]},
            "строками «(контекст)»",
        ),
        ({"participants": [participant("E1", [])]}, "не подтверждён источником (supports: entity)"),
        (
            {"participants": [participant("E1", [source(INTRO, "Работники БВА", "entity")], group="работники БВА")]},
            "не подтверждена (supports: membership)",
        ),
        ({"participants": [participant(None, [], designation="уполномоченный работник")]}, "пояснение (note)"),
        ({"participants": [participant(None, [], note="не назван")]}, "исходное обозначение (designation)"),
        ({"participation": "alternative"}, "минимум двух участников"),
        ({"participants": [*_right()["participants"], UNRESOLVED]}, "ровно один участник"),
        (
            {"participation": "each", "participants": [*_right()["participants"], UNRESOLVED]},
            "поле participation не подтверждено",
        ),
        ({"participation": "unclear"}, "нужно пояснение (notes)"),
        ({"participant_designation": " "}, "participant_designation пустое"),
        (
            {"sources": [source(CLAUSE, "запрашивать", "formulation", "type", "executor")]},
            "недопустимые значения supports",
        ),
    ],
)
def test_problems_are_reported_and_the_provision_dropped(changes: dict[str, Any], expected: str) -> None:
    kept, errors = _check(_right(**changes))

    assert kept == 0
    assert any(expected in error for error in errors), errors


def test_another_clause_of_the_document_may_support_a_field() -> None:
    item = _right(
        condition="по согласованию с Главным аудитором",
        sources=[*_right()["sources"], source(OTHER, "утверждается Главным аудитором", "condition")],
    )

    assert _check(item) == (1, [])


def test_joint_provision_becomes_one_record_per_specialist() -> None:
    shared = [source(JOINT, "Специалисты А и Б совместно готовят отчёт", "formulation", "type", "participation")]
    item = provision(
        "function",
        "Специалисты А и Б совместно готовят отчёт",
        [
            participant("E3", [source(JOINT, "Специалисты А", "entity")]),
            participant("E4", [source(JOINT, "Б", "entity")]),
        ],
        shared,
        participation="joint",
        designation="Специалисты А и Б",
    )
    answer = BlockAnswer.model_validate({"block_status": "found", "provisions": [item]})
    (first, second), errors = check_answer(answer, SCOPE)

    assert errors == []
    assert (first.entity_id, first.participant_entity_ids) == (3, (4,))
    assert (second.entity_id, second.participant_entity_ids) == (4, (3,))
    assert {first.participation, second.participation} == {"joint"}
    assert first.formulation == second.formulation
    assert first.sources[0] == second.sources[0]
    assert first.sources[0].quote == "Специалисты А и Б совместно готовят отчёт"
    # Stages 4.1/4.2 consolidate joint functions by the provision the records were split from.
    assert provision_key(7, first) == provision_key(7, second)
    assert provision_key(7, first) != provision_key(8, first)


def test_participant_condition_joins_the_provision_condition() -> None:
    authorised = participant(
        None,
        [source(OTHER, "уполномоченным им работником", "condition")],
        designation="уполномоченный им работник",
        condition="при наличии полномочий от Главного аудитора",
        note="носитель роли не назван",
    )
    item = _right(
        participation="alternative",
        participants=[*_right()["participants"], authorised],
        condition="по согласованию с Главным аудитором",
        sources=[
            *_right()["sources"],
            source(OTHER, "утверждается Главным аудитором", "condition", "participation"),
        ],
    )
    answer = BlockAnswer.model_validate({"block_status": "found", "provisions": [item]})
    (director, unresolved), errors = check_answer(answer, SCOPE)

    assert errors == []
    assert director.condition == "по согласованию с Главным аудитором"
    assert unresolved.condition == "по согласованию с Главным аудитором; при наличии полномочий от Главного аудитора"
    assert (unresolved.entity_id, unresolved.participant_entity_ids) == (None, (1,))
    assert review_status(director) is ReviewStatus.CHECKED
    assert review_status(unresolved) is ReviewStatus.NEEDS_REVIEW


def test_block_status_must_match_the_provisions() -> None:
    assert "block_status «none», но положения перечислены" in _check(_right(), status="none")[1]
    assert _check(status="found")[1] == ["block_status «found», но положений нет — используйте «none»"]
    assert _check(status="needs_clarification")[1][0].startswith("block_status «needs_clarification» без замечаний")


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
    model = _Replies(
        {"block_status": "found", "provisions": [invented]},
        {"block_status": "found", "provisions": [_right()]},
    )

    outcome = extract_block(model, OPENING, BLOCK, "п. 5.7", SCOPE, retries=2)

    assert (outcome.status, outcome.attempts, len(outcome.records)) == (BlockStatus.FOUND, 2, 1)
    assert "цитата «запрашивать всё» не найдена" in model.seen[1][-1].content
    assert model.seen[1][-2].role == "assistant"


def test_exhausted_retries_fail_the_block_but_keep_verified_records() -> None:
    broken = _right(participants=[participant("E9", [source(INTRO, "Работники БВА", "entity")])])
    answer = {"block_status": "found", "provisions": [_right(), broken]}
    model = _Replies(answer, answer)

    outcome = extract_block(model, OPENING, BLOCK, "п. 5.7", SCOPE, retries=1)

    assert (outcome.status, outcome.attempts, len(outcome.records)) == (BlockStatus.FAILED, 2, 1)
    assert outcome.message is not None
    assert "E9 нет в реестре" in outcome.message
    assert document_status([outcome], [ReviewStatus.CHECKED]) is ActivitiesStatus.NEEDS_REVIEW


def test_model_error_fails_the_block_and_invalid_json_is_retried() -> None:
    model = _Replies({"provisions": "oops"}, ChatModelError("timeout"))

    outcome = extract_block(model, OPENING, BLOCK, "п. 5.7", SCOPE, retries=2)

    assert (outcome.status, outcome.attempts, outcome.records) == (BlockStatus.FAILED, 2, ())
    assert outcome.message == "Ошибка обращения к модели: timeout"
    assert "block_status" in model.seen[1][-1].content


def test_empty_block_is_done() -> None:
    outcome = extract_block(_Replies({"block_status": "none"}), OPENING, BLOCK, "п. 5.7", SCOPE, retries=0)

    assert (outcome.status, outcome.message) == (BlockStatus.NONE, None)
    assert document_status([outcome], []) is ActivitiesStatus.DONE
    assert document_status([outcome], [ReviewStatus.NEEDS_REVIEW]) is ActivitiesStatus.NEEDS_REVIEW
