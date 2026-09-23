"""Stage 3 on the parsed control editions with scripted model answers (methodology §7)."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from activity_script import (
    ED9_ENTITIES,
    BlockView,
    Handler,
    ScriptedModel,
    add_entities,
    node_texts,
    parse_edition,
    participant,
    provision,
    source,
)
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from la_rp_peace.activities.pipeline import ActivityStage
from la_rp_peace.db import make_engine
from la_rp_peace.enums import EntitiesStatus
from la_rp_peace.llm import ChatModelError, Message
from la_rp_peace.models import (
    ActivityBlock,
    ActivityIssue,
    ActivityRecord,
    ActivitySource,
    Document,
    DocumentNode,
    create_schema,
)

WORKERS = "работники БВА"
REMAINDER_NOTE = "Состав работников БВА раскрыт не полностью: штатное расписание в документе не приведено"


def _workers(view: BlockView) -> list[dict[str, Any]]:
    """Registry members of «работники БВА» confirmed by п. 3.5, plus the undisclosed remainder."""
    intro = source(view.node("3.5. "), "Главному аудитору подчиняются работники БВА", "membership")
    members = [
        participant(
            view.key(name),
            [intro, source(view.node(f"{letter}. {name}"), name, "entity", "membership")],
            group=WORKERS,
        )
        for letter, name in (("а", "Директор ДИТААД"), ("б", "Директор ДОА"))
    ]
    return [*members, participant(None, [], designation=WORKERS, note=REMAINDER_NOTE)]


def _report_5_1_6(view: BlockView) -> list[dict[str, Any]]:
    clause, heading = view.node("5.1.6."), view.node("Главный аудитор:")
    chief = participant(view.key("Главный аудитор"), [source(heading, "Главный аудитор", "entity")])
    return [
        provision(
            "duty",
            "Главный аудитор представляет отчеты об итогах выполнения плана работы БВА "
            "на ежеквартальной основе и по итогам года",
            [chief],
            [
                source(clause, "представляет отчеты об итогах выполнения плана работы БВА", "formulation", "type"),
                source(clause, "на ежеквартальной основе и по итогам года", "periodicity"),
            ],
            periodicity="на ежеквартальной основе и по итогам года",
        ),
    ]


def _other_powers_5_1_11(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("5.1.11.")
    chief = participant(
        view.key("Главный аудитор"), [source(view.node("Главный аудитор:"), "Главный аудитор", "entity")]
    )
    condition = "в соответствии с решениями Комитета по аудиту и/или Совета директоров Общества"
    return [
        provision(
            "function",
            f"Главный аудитор осуществляет другие полномочия {condition}",
            [chief],
            [
                source(clause, "осуществляет другие полномочия", "formulation", "type", "specificity"),
                source(clause, condition, "condition"),
            ],
            specificity="generalized",
            condition=condition,
        ),
    ]


def _right_and_duty_5_7_9(view: BlockView) -> list[dict[str, Any]]:
    intro, clause = view.node("5.7. "), view.node("5.7.9.")
    duty_quote = "Работники БВА обязаны согласовывать с Куратором проверки изменение круга проверяемых вопросов"
    condition = "если выявляется необходимость в таком расширении при выполнении программы проверки"
    return [
        provision(
            "right",
            f"Работники БВА имеют право расширять круг вопросов (участков) проверки, {condition}",
            _workers(view),
            [
                source(intro, "Работники БВА имеют право", "type", "participation"),
                source(clause, "расширять круг вопросов (участков) проверки", "formulation"),
                source(clause, condition, "condition"),
            ],
            participation="each",
            designation="Работники БВА",
            condition=condition,
        ),
        provision(
            "duty",
            duty_quote,
            _workers(view),
            [source(clause, duty_quote, "formulation", "type", "participation")],
            participation="each",
            designation="Работники БВА",
        ),
    ]


def _conditional_2_4_17_b(view: BlockView) -> list[dict[str, Any]]:
    # 5.3.3 «б» starts with the same words; only 2.4.17 «б» has the chief auditor's assessment.
    items = [node for node, text in view.own.items() if "Главный аудитор предварительно оценивает" in text]
    if not items:
        return []
    (item,) = items
    condition = (
        "В случае если внутренний аудит полагается на результаты работы других субъектов СВК "
        "и иных заинтересованных сторон"
    )
    return [
        provision(
            "function",
            "Главный аудитор предварительно оценивает качество и надежность результатов работ других "
            "субъектов СВК и иных заинтересованных сторон, если внутренний аудит полагается на эти результаты",
            [participant(view.key("Главный аудитор"), [source(item, "Главный аудитор", "entity")])],
            [
                source(item, "Главный аудитор предварительно оценивает качество и надежность", "formulation", "type"),
                source(item, condition, "condition"),
                source(item, "предварительно оценивает", "deadline"),
            ],
            condition=condition,
            deadline="предварительно",
        ),
    ]


def _alternative_9_4(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("9.4.")
    circle = "Главным аудитором или уполномоченным им работником"
    return [
        provision(
            "function",
            f"Программа проверки утверждается {circle}",
            [
                participant(view.key("Главный аудитор"), [source(clause, "утверждается Главным аудитором", "entity")]),
                participant(
                    None,
                    [source(clause, "уполномоченным им работником", "condition")],
                    designation="уполномоченный им работник",
                    condition="при наличии полномочий от Главного аудитора",
                    note="Носитель роли не назван; в реестре документа такого объекта нет",
                ),
            ],
            [
                source(clause, "Программа проверки утверждается", "formulation", "type"),
                source(clause, circle, "participation"),
            ],
            participation="alternative",
            designation="Главный аудитор или уполномоченный им работник",
        ),
    ]


def _prohibition_5_8_2(view: BlockView) -> list[dict[str, Any]]:
    intro, clause = view.node("5.8. "), view.node("5.8.2.")
    exception = (
        "за исключением случаев, когда эти работники специально назначены для совместной работы с/для БВА на проекте"
    )
    chief = participant(view.key("Главный аудитор"), [source(intro, "Главный аудитор", "entity")])
    return [
        provision(
            "prohibition",
            "Главный аудитор и работники БВА не имеют права руководить действиями работников других "
            f"подразделений, {exception}",
            [chief, *_workers(view)],
            [
                source(intro, "Главный аудитор и работники БВА не имеют права", "type", "participation"),
                source(clause, "руководить действиями работников других подразделений", "formulation"),
                source(clause, exception, "condition"),
            ],
            participation="each",
            designation="Главный аудитор и работники БВА",
            condition=exception,
        ),
    ]


def _evidence_9_25(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("9.25.")
    return [
        provision(
            "function",
            "Рабочая группа собирает достаточное количество надежных аудиторских доказательств для "
            "подтверждения текущего состояния объекта аудита в части процедур внутреннего контроля и мероприятий "
            "по управлению рисками",
            [participant(view.key("Рабочая группа"), [source(clause, "Рабочая группа собирает", "entity")])],
            [
                source(
                    clause,
                    "Рабочая группа собирает достаточное количество надежных аудиторских доказательств",
                    "formulation",
                    "type",
                ),
            ],
            designation="Рабочая группа",
        ),
    ]


def _curator_9_44(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("9.44.")
    return [
        provision(
            "duty",
            "Куратор проверки по завершению проверки формирует Итоговое мнение в соответствии "
            "с внутренними процедурами БВА",
            [participant(view.key("Куратор проверки"), [source(clause, "Куратор проверки", "entity")])],
            [
                source(clause, "Куратор проверки формирует Итоговое мнение", "formulation", "type"),
                source(clause, "По завершению проверки", "deadline"),
            ],
            designation="Куратор проверки",
            deadline="по завершению проверки",
        ),
    ]


ED9_HANDLERS: dict[str, Handler] = {
    "5.1.6.": _report_5_1_6,
    "5.1.11.": _other_powers_5_1_11,
    "5.7.9.": _right_and_duty_5_7_9,
    "б. выявления рисков": _conditional_2_4_17_b,
    "9.4.": _alternative_9_4,
    "5.8.2.": _prohibition_5_8_2,
    "9.25.": _evidence_9_25,
    "9.44.": _curator_9_44,
}
ED9_RECORDS = 17  # 1 + 1 + 2×3 + 1 + 2 + 4 + 1 + 1


def ed9_model(session: Session, document_id: int, handlers: dict[str, Handler] | None = None) -> ScriptedModel:
    """The scripted model for edition 9, with the document's nodes for membership sources."""
    return ScriptedModel(ED9_HANDLERS if handlers is None else handlers, node_texts(session, document_id))


@pytest.fixture
def engine() -> Engine:
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    return engine


@dataclass
class Ed9Run:
    session: Session
    document_id: int
    entities: dict[str, int]
    model: ScriptedModel


@pytest.fixture(scope="module")
def ed9() -> Iterator[Ed9Run]:
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        entities = add_entities(session, document_id, ED9_ENTITIES)
        model = ed9_model(session, document_id)
        ActivityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        yield Ed9Run(session, document_id, entities, model)


def _records(session: Session, prefix: str) -> list[ActivityRecord]:
    query = select(ActivityRecord).where(ActivityRecord.formulation.startswith(prefix)).order_by(ActivityRecord.id)
    return list(session.scalars(query))


def _sources(session: Session, record: ActivityRecord) -> list[tuple[str, list[str]]]:
    rows = session.scalars(select(ActivitySource).where(ActivitySource.record_id == record.id))
    return [(row.quote, json.loads(row.supports)) for row in rows]


def _count(session: Session, model: type[ActivityRecord] | type[ActivitySource]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# -- control cases, edition 9 ------------------------------------------------------------


def test_report_duty_keeps_periodicity_without_deadline(ed9: Ed9Run) -> None:
    (record,) = _records(ed9.session, "Главный аудитор представляет отчеты")

    assert (record.record_type, record.deadline, record.specificity) == ("duty", None, "specific")
    assert record.periodicity == "на ежеквартальной основе и по итогам года"
    assert (record.entity_id, record.participation, record.participant_entity_ids) == (
        ed9.entities["Главный аудитор"],
        "individual",
        "[]",
    )
    assert record.review_status == "checked"
    # The executor comes from the heading, the action from the clause: both are sources.
    assert ("Главный аудитор", ["entity"]) in _sources(ed9.session, record)
    assert ("на ежеквартальной основе и по итогам года", ["periodicity"]) in _sources(ed9.session, record)


def test_other_powers_are_a_generalized_function(ed9: Ed9Run) -> None:
    (record,) = _records(ed9.session, "Главный аудитор осуществляет другие полномочия")

    assert (record.record_type, record.specificity, record.review_status) == ("function", "generalized", "checked")
    assert ("осуществляет другие полномочия", ["formulation", "type", "specificity"]) in _sources(ed9.session, record)


def test_group_provision_becomes_a_record_per_member_and_a_remainder(ed9: Ed9Run) -> None:
    rights = _records(ed9.session, "Работники БВА имеют право расширять")
    duties = _records(ed9.session, "Работники БВА обязаны согласовывать")
    members = [ed9.entities["Директор ДИТААД"], ed9.entities["Директор ДОА"]]

    for records, record_type in ((rights, "right"), (duties, "duty")):
        assert [record.entity_id for record in records] == [*members, None]
        assert {(record.record_type, record.participation) for record in records} == {(record_type, "each")}
        assert json.loads(records[0].participant_entity_ids) == [members[1]]
        assert json.loads(records[2].participant_entity_ids) == members
        assert (records[2].designation, records[2].note) == (WORKERS, REMAINDER_NOTE)
        assert [record.review_status for record in records] == ["checked", "checked", "needs_review"]
    membership = [supports for _, supports in _sources(ed9.session, rights[0]) if "membership" in supports]
    assert membership == [["membership"], ["entity", "membership"]]
    # The curator is who the change is agreed with, not a participant.
    assert ed9.entities["Куратор проверки"] not in {record.entity_id for record in duties}


def test_conditional_assessment_keeps_its_condition(ed9: Ed9Run) -> None:
    (record,) = _records(ed9.session, "Главный аудитор предварительно оценивает")

    assert record.condition is not None
    assert record.condition.startswith("В случае если внутренний аудит полагается")
    assert record.deadline == "предварительно"


def test_chief_or_authorised_worker_are_two_alternative_records(ed9: Ed9Run) -> None:
    chief, authorised = _records(ed9.session, "Программа проверки утверждается")

    assert (chief.entity_id, chief.participation, chief.condition) == (
        ed9.entities["Главный аудитор"],
        "alternative",
        None,
    )
    assert (authorised.entity_id, authorised.participation) == (None, "alternative")
    assert authorised.designation == "уполномоченный им работник"
    assert authorised.condition == "при наличии полномочий от Главного аудитора"
    assert chief.participant_designation == authorised.participant_designation
    assert json.loads(authorised.participant_entity_ids) == [ed9.entities["Главный аудитор"]]
    assert (chief.review_status, authorised.review_status) == ("checked", "needs_review")
    issues = ed9.session.scalars(select(ActivityIssue).where(ActivityIssue.record_id == authorised.id)).all()
    assert [(issue.issue_type, issue.is_blocking) for issue in issues] == [("unresolved_entity", 0)]


def test_prohibition_keeps_the_exception_for_each_participant(ed9: Ed9Run) -> None:
    records = _records(ed9.session, "Главный аудитор и работники БВА не имеют права")

    assert len(records) == 4
    assert {record.record_type for record in records} == {"prohibition"}
    assert all(record.condition and record.condition.startswith("за исключением случаев") for record in records)
    assert records[0].entity_id == ed9.entities["Главный аудитор"]


def test_evidence_list_is_one_function(ed9: Ed9Run) -> None:
    (record,) = _records(ed9.session, "Рабочая группа собирает")
    cited = {row.node_id for row in ed9.session.scalars(select(ActivitySource))}
    item = ed9.session.scalars(
        select(DocumentNode).where(
            DocumentNode.document_id == ed9.document_id,
            DocumentNode.text.startswith("б. выгрузки"),
        ),
    ).one()

    assert record.record_type == "function"
    assert item.id not in cited


def test_temporary_role_duty_stays_with_the_curator(ed9: Ed9Run) -> None:
    (record,) = _records(ed9.session, "Куратор проверки по завершению")

    assert record.entity_id == ed9.entities["Куратор проверки"]
    assert record.deadline == "по завершению проверки"


def test_every_block_is_marked_and_status_reflects_open_participants(ed9: Ed9Run) -> None:
    blocks = ed9.session.scalars(select(ActivityBlock).where(ActivityBlock.document_id == ed9.document_id)).all()
    document = ed9.session.get(Document, ed9.document_id)
    records = ed9.session.scalars(select(ActivityRecord)).all()

    assert len(blocks) == len(ed9.model.conversations)
    assert {block.status for block in blocks} == {"found", "none"}
    assert len(records) == ED9_RECORDS
    assert {record.block_node_id for record in records} <= {block.node_id for block in blocks}
    assert document is not None
    assert document.activities_status == "needs_review"


def test_registry_and_context_are_shown_to_the_model(ed9: Ed9Run) -> None:
    user = ed9.model.conversations[0][1].content

    assert f"E{ed9.entities['Главный аудитор']} | Главный аудитор | тип: должность" in user
    assert "Карточка документа:" in user
    assert any("(контекст)" in conversation[1].content for conversation in ed9.model.conversations)


# -- edition 8: an empty clause produces nothing -----------------------------------------


def test_empty_clause_is_rejected_then_produces_no_record(engine: Engine) -> None:
    def invent_from_semicolon(view: BlockView) -> list[dict[str, Any]]:
        if view.attempt > 1:
            return []
        clause = view.node("5.5.3.")
        director = participant(view.key("Директор ДККМ"), [source(clause, ";", "entity")])
        return [provision("function", "Директор ДККМ ;", [director], [source(clause, ";", "formulation", "type")])]

    with Session(engine) as session:
        document_id = parse_edition(session, 8)
        add_entities(session, document_id, [("Директор ДККМ", "должность", None, [])])
        model = ScriptedModel({"5.5.3.": invent_from_semicolon})
        ActivityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        document = session.get(Document, document_id)

        rejected = [conversation for conversation in model.conversations if len(conversation) > 2]
        assert len(rejected) == 1
        assert "не содержит слов" in rejected[0][-1].content
        assert _count(session, ActivityRecord) == 0
        assert document is not None
        assert document.activities_status == "done"


# -- stage behaviour and re-runs ---------------------------------------------------------


def test_stage_waits_for_entities(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES, status=EntitiesStatus.RUNNING)
        model = ed9_model(session, document_id)
        ActivityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        document = session.get(Document, document_id)

        assert model.conversations == []
        assert document is not None
        assert document.activities_status == "not_started"


class _Unreachable:
    def complete(self, messages: list[Message]) -> str:
        raise ChatModelError(f"нет связи ({len(messages)} сообщений)")


def _ids(session: Session) -> dict[tuple[int | None, str], int]:
    return {(row.entity_id, row.formulation): row.id for row in session.scalars(select(ActivityRecord))}


def test_first_run_failures_are_not_empty_results(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES)
        ActivityStage(_Unreachable(), max_chars=12_000, retries=2).run(session, document_id)
        document = session.get(Document, document_id)
        blocks = session.scalars(select(ActivityBlock)).all()
        issues = session.scalars(select(ActivityIssue)).all()

        assert {(block.status, block.attempts) for block in blocks} == {("failed", 1)}
        assert {(issue.issue_type, issue.is_blocking) for issue in issues} == {("block_failed", 1)}
        assert len(issues) == len(blocks)
        assert document is not None
        assert document.activities_status == "needs_review"


def test_rerun_keeps_ids_and_does_not_duplicate(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES)
        stage = ActivityStage(ed9_model(session, document_id), max_chars=12_000, retries=2)
        stage.run(session, document_id)
        first, sources = _ids(session), _count(session, ActivitySource)
        stage.run(session, document_id)

        assert _ids(session) == first
        assert len(first) == ED9_RECORDS
        assert _count(session, ActivitySource) == sources


def test_corrected_rerun_replaces_only_the_changed_record(engine: Engine) -> None:
    corrected = "Куратор проверки формирует Итоговое мнение по завершению проверки"

    def corrected_curator(view: BlockView) -> list[dict[str, Any]]:
        return [{**_curator_9_44(view)[0], "formulation": corrected}]

    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        entities = add_entities(session, document_id, ED9_ENTITIES)
        ActivityStage(ed9_model(session, document_id), max_chars=12_000, retries=2).run(session, document_id)
        first = _ids(session)
        # 9.44 is reworded and 9.25 is withdrawn; both are in the same block as unchanged records.
        handlers = {**ED9_HANDLERS, "9.44.": corrected_curator, "9.25.": lambda _view: []}
        ActivityStage(ed9_model(session, document_id, handlers), max_chars=12_000, retries=2).run(session, document_id)
        second = _ids(session)

        curator, group = entities["Куратор проверки"], entities["Рабочая группа"]
        assert set(second) - set(first) == {(curator, corrected)}
        assert {(entity, text[:14]) for entity, text in set(first) - set(second)} == {
            (curator, "Куратор провер"),
            (group, "Рабочая группа"),
        }
        assert all(first[key] == second[key] for key in set(first) & set(second))
        assert second[(curator, corrected)] not in first.values()


def test_failed_rerun_keeps_previous_records(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES)
        ActivityStage(ed9_model(session, document_id), max_chars=12_000, retries=2).run(session, document_id)
        first = _ids(session)
        ActivityStage(_Unreachable(), max_chars=12_000, retries=0).run(session, document_id)
        issues = session.scalars(select(ActivityIssue).where(ActivityIssue.issue_type == "block_failed")).all()

        assert _ids(session) == first
        assert {block.status for block in session.scalars(select(ActivityBlock))} == {"failed"}
        kept = [issue for issue in issues if "сохранены записи предыдущего разбора" in issue.message]
        assert len(kept) == len({block for block, _ in _block_keys(session)})


def _block_keys(session: Session) -> set[tuple[int, int]]:
    return {(row.block_node_id, row.id) for row in session.scalars(select(ActivityRecord))}


def test_fail_marks_the_stage(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES)
        ActivityStage(ed9_model(session, document_id), max_chars=12_000, retries=2).fail(
            session, document_id, "Внутренняя ошибка этапа activities: boom"
        )
        document = session.get(Document, document_id)
        issue = session.scalars(select(ActivityIssue)).one()

        assert document is not None
        assert document.activities_status == "failed"
        assert (issue.issue_type, issue.is_blocking) == ("other", 1)
