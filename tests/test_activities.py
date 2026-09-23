"""Stage 3 on the parsed control editions with scripted model answers (methodology §7)."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from activity_script import (
    ED9_ENTITIES,
    BlockView,
    ScriptedModel,
    add_entities,
    binding,
    parse_edition,
    source,
)
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from la_rp_peace.activities.pipeline import ActivityStage
from la_rp_peace.db import make_engine
from la_rp_peace.enums import EntitiesStatus
from la_rp_peace.llm import ChatModelError, Message
from la_rp_peace.models import (
    ActivityBinding,
    ActivityBlock,
    ActivityIssue,
    ActivityRecord,
    ActivitySource,
    Document,
    DocumentNode,
    create_schema,
)


def _report_5_1_6(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("5.1.6.")
    return [
        {
            "type": "duty",
            "formulation": "Главный аудитор представляет отчеты об итогах выполнения плана работы БВА "
            "на ежеквартальной основе и по итогам года",
            "condition": None,
            "deadline": None,
            "periodicity": "на ежеквартальной основе и по итогам года",
            "bindings": [
                binding(
                    view.key("Главный аудитор"), [source(view.node("Главный аудитор:"), "Главный аудитор", "binding")]
                )
            ],
            "sources": [
                source(clause, "представляет отчеты об итогах выполнения плана работы БВА", "formulation", "type"),
                source(clause, "на ежеквартальной основе и по итогам года", "periodicity"),
            ],
        },
    ]


def _right_and_duty_5_7_9(view: BlockView) -> list[dict[str, Any]]:
    intro, clause = view.node("5.7. "), view.node("5.7.9.")
    workers = view.key("Работники БВА")
    duty_quote = "Работники БВА обязаны согласовывать с Куратором проверки изменение круга проверяемых вопросов"
    condition = "если выявляется необходимость в таком расширении при выполнении программы проверки"
    return [
        {
            "type": "right",
            "formulation": f"Работники БВА имеют право расширять круг вопросов (участков) проверки, {condition}",
            "condition": condition,
            "bindings": [binding(workers, [source(intro, "Работники БВА имеют право", "binding")])],
            "sources": [
                source(intro, "Работники БВА имеют право", "type"),
                source(clause, "расширять круг вопросов (участков) проверки", "formulation"),
                source(clause, condition, "condition"),
            ],
        },
        {
            "type": "duty",
            "formulation": duty_quote,
            "bindings": [binding(workers, [source(clause, duty_quote, "binding")])],
            "sources": [source(clause, duty_quote, "formulation", "type")],
        },
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
        {
            "type": "function",
            "formulation": "Главный аудитор предварительно оценивает качество и надежность результатов работ других "
            "субъектов СВК и иных заинтересованных сторон, если внутренний аудит полагается на эти результаты",
            "condition": condition,
            "deadline": "предварительно",
            "bindings": [binding(view.key("Главный аудитор"), [source(item, "Главный аудитор", "binding")])],
            "sources": [
                source(item, "Главный аудитор предварительно оценивает качество и надежность", "formulation", "type"),
                source(item, condition, "condition"),
                source(item, "предварительно оценивает", "deadline"),
            ],
        },
    ]


def _alternative_9_4(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("9.4.")
    return [
        {
            "type": "function",
            "formulation": "Программа проверки утверждается Главным аудитором или уполномоченным им работником",
            "bindings": [
                binding(
                    view.key("Главный аудитор"),
                    [source(clause, "утверждается Главным аудитором", "binding")],
                    "alternative",
                ),
                binding(
                    None,
                    [source(clause, "уполномоченным им работником", "binding", "condition")],
                    "alternative",
                    designation="уполномоченный им работник",
                    condition="при наличии полномочий от Главного аудитора",
                    note="Уполномоченный работник не назван; в реестре документа такого объекта нет",
                ),
            ],
            "sources": [
                source(clause, "Программа проверки утверждается Главным аудитором", "formulation", "type"),
            ],
        },
    ]


def _prohibition_5_8_2(view: BlockView) -> list[dict[str, Any]]:
    intro, clause = view.node("5.8. "), view.node("5.8.2.")
    exception = (
        "за исключением случаев, когда эти работники специально назначены для совместной работы с/для БВА на проекте"
    )
    group = [source(intro, "Главный аудитор и работники БВА не имеют права", "binding")]
    return [
        {
            "type": "prohibition",
            "formulation": "Главный аудитор и работники БВА не имеют права руководить действиями работников других "
            f"подразделений, {exception}",
            "condition": exception,
            "bindings": [binding(view.key("Главный аудитор"), group), binding(view.key("Работники БВА"), group)],
            "sources": [
                source(intro, "не имеют права", "type"),
                source(clause, "руководить действиями работников других подразделений", "formulation"),
                source(clause, exception, "condition"),
            ],
        },
    ]


def _evidence_9_25(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("9.25.")
    return [
        {
            "type": "function",
            "formulation": "Рабочая группа собирает достаточное количество надежных аудиторских доказательств для "
            "подтверждения текущего состояния объекта аудита в части процедур внутреннего контроля и мероприятий "
            "по управлению рисками",
            "bindings": [binding(view.key("Рабочая группа"), [source(clause, "Рабочая группа собирает", "binding")])],
            "sources": [
                source(
                    clause,
                    "Рабочая группа собирает достаточное количество надежных аудиторских доказательств",
                    "formulation",
                    "type",
                ),
            ],
        },
    ]


def _curator_9_44(view: BlockView) -> list[dict[str, Any]]:
    clause = view.node("9.44.")
    return [
        {
            "type": "duty",
            "formulation": "Куратор проверки по завершению проверки формирует Итоговое мнение в соответствии "
            "с внутренними процедурами БВА",
            "deadline": "по завершению проверки",
            "bindings": [binding(view.key("Куратор проверки"), [source(clause, "Куратор проверки", "binding")])],
            "sources": [
                source(clause, "Куратор проверки формирует Итоговое мнение", "formulation", "type"),
                source(clause, "По завершению проверки", "deadline"),
            ],
        },
    ]


ED9_HANDLERS = {
    "5.1.6.": _report_5_1_6,
    "5.7.9.": _right_and_duty_5_7_9,
    "б. выявления рисков": _conditional_2_4_17_b,
    "9.4.": _alternative_9_4,
    "5.8.2.": _prohibition_5_8_2,
    "9.25.": _evidence_9_25,
    "9.44.": _curator_9_44,
}


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
        model = ScriptedModel(ED9_HANDLERS)
        ActivityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        yield Ed9Run(session, document_id, entities, model)


def _record(run: Ed9Run, prefix: str) -> ActivityRecord:
    return run.session.scalars(select(ActivityRecord).where(ActivityRecord.formulation.startswith(prefix))).one()


def _bindings(session: Session, record: ActivityRecord) -> list[ActivityBinding]:
    return list(session.scalars(select(ActivityBinding).where(ActivityBinding.record_id == record.id)))


def _record_sources(session: Session, record: ActivityRecord) -> list[tuple[str, list[str]]]:
    rows = session.scalars(select(ActivitySource).where(ActivitySource.record_id == record.id))
    return [(row.quote, json.loads(row.supports)) for row in rows]


def _binding_sources(session: Session, bound: ActivityBinding) -> list[ActivitySource]:
    return list(session.scalars(select(ActivitySource).where(ActivitySource.binding_id == bound.id)))


def _node_text(session: Session, node_id: int) -> str:
    node = session.get(DocumentNode, node_id)
    assert node is not None
    return node.text


# -- control cases, edition 9 ------------------------------------------------------------


def test_report_duty_keeps_periodicity_without_deadline(ed9: Ed9Run) -> None:
    record = _record(ed9, "Главный аудитор представляет отчеты")
    (bound,) = _bindings(ed9.session, record)

    assert (record.record_type, record.deadline) == ("duty", None)
    assert record.periodicity == "на ежеквартальной основе и по итогам года"
    assert record.review_status == "checked"
    assert (bound.entity_id, bound.participation) == (ed9.entities["Главный аудитор"], "individual")
    assert ("на ежеквартальной основе и по итогам года", ["periodicity"]) in _record_sources(ed9.session, record)
    # The executor comes from the heading, the action from the clause: both are sources.
    (heading,) = _binding_sources(ed9.session, bound)
    assert _node_text(ed9.session, heading.node_id) == "Главный аудитор:"


def test_right_and_duty_in_one_clause_are_two_records(ed9: Ed9Run) -> None:
    right = _record(ed9, "Работники БВА имеют право расширять")
    duty = _record(ed9, "Работники БВА обязаны согласовывать")

    assert (right.record_type, duty.record_type) == ("right", "duty")
    assert right.condition == "если выявляется необходимость в таком расширении при выполнении программы проверки"
    workers = ed9.entities["Работники БВА"]
    assert [b.entity_id for b in _bindings(ed9.session, right) + _bindings(ed9.session, duty)] == [workers, workers]
    # The curator is who the change is agreed with, not an executor.
    assert ed9.entities["Куратор проверки"] not in {b.entity_id for b in _bindings(ed9.session, duty)}


def test_conditional_assessment_keeps_its_condition(ed9: Ed9Run) -> None:
    record = _record(ed9, "Главный аудитор предварительно оценивает")

    assert record.condition is not None
    assert record.condition.startswith("В случае если внутренний аудит полагается")
    assert record.deadline == "предварительно"
    assert {tuple(supports) for _, supports in _record_sources(ed9.session, record)} == {
        ("formulation", "type"),
        ("condition",),
        ("deadline",),
    }


def test_approval_by_chief_or_authorised_worker_is_alternative(ed9: Ed9Run) -> None:
    record = _record(ed9, "Программа проверки утверждается")
    chief, authorised = _bindings(ed9.session, record)

    assert (chief.entity_id, chief.participation, chief.condition) == (
        ed9.entities["Главный аудитор"],
        "alternative",
        None,
    )
    assert (authorised.entity_id, authorised.participation) == (None, "alternative")
    assert authorised.designation == "уполномоченный им работник"
    assert authorised.condition == "при наличии полномочий от Главного аудитора"
    assert record.review_status == "needs_review"
    issues = ed9.session.scalars(select(ActivityIssue).where(ActivityIssue.binding_id == authorised.id)).all()
    assert [(issue.issue_type, issue.is_blocking) for issue in issues] == [("unresolved_entity", 0)]


def test_prohibition_keeps_the_exception(ed9: Ed9Run) -> None:
    record = _record(ed9, "Главный аудитор и работники БВА не имеют права")

    assert record.record_type == "prohibition"
    assert record.condition is not None
    assert record.condition.startswith("за исключением случаев")
    assert {b.entity_id for b in _bindings(ed9.session, record)} == {
        ed9.entities["Главный аудитор"],
        ed9.entities["Работники БВА"],
    }
    assert record.review_status == "checked"


def test_evidence_list_is_one_function(ed9: Ed9Run) -> None:
    record = _record(ed9, "Рабочая группа собирает")
    cited = {source.node_id for source in ed9.session.scalars(select(ActivitySource))}

    items = ed9.session.scalars(
        select(DocumentNode).where(
            DocumentNode.document_id == ed9.document_id, DocumentNode.text.startswith("б. выгрузки")
        ),
    ).one()
    assert record.record_type == "function"
    assert items.id not in cited


def test_temporary_role_duty_stays_with_the_curator(ed9: Ed9Run) -> None:
    record = _record(ed9, "Куратор проверки по завершению")
    (bound,) = _bindings(ed9.session, record)

    assert bound.entity_id == ed9.entities["Куратор проверки"]
    assert record.deadline == "по завершению проверки"


def test_every_block_is_marked_and_status_reflects_open_bindings(ed9: Ed9Run) -> None:
    blocks = ed9.session.scalars(select(ActivityBlock).where(ActivityBlock.document_id == ed9.document_id)).all()
    document = ed9.session.get(Document, ed9.document_id)
    records = ed9.session.scalar(select(func.count()).select_from(ActivityRecord)) or 0

    assert len(blocks) == len(ed9.model.conversations)
    assert {block.status for block in blocks} == {"found", "none"}
    assert records == 8
    assert document is not None
    # The authorised worker of 9.4 is not in the registry, so the result needs review.
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
        director = view.key("Директор ДККМ")
        return [
            {
                "type": "function",
                "formulation": "Директор ДККМ ;",
                "bindings": [binding(director, [source(clause, ";", "binding")])],
                "sources": [source(clause, ";", "formulation", "type")],
            },
        ]

    with Session(engine) as session:
        document_id = parse_edition(session, 8)
        add_entities(session, document_id, [("Директор ДККМ", "должность", None, [])])
        model = ScriptedModel({"5.5.3.": invent_from_semicolon})
        ActivityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        document = session.get(Document, document_id)

        rejected = [c for c in model.conversations if len(c) > 2]
        assert len(rejected) == 1
        assert "не содержит слов" in rejected[0][-1].content
        assert session.scalar(select(func.count()).select_from(ActivityRecord)) == 0
        assert document is not None
        assert document.activities_status == "done"


# -- stage behaviour ---------------------------------------------------------------------


def test_stage_waits_for_entities(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES, status=EntitiesStatus.RUNNING)
        model = ScriptedModel(ED9_HANDLERS)
        ActivityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        document = session.get(Document, document_id)

        assert model.conversations == []
        assert document is not None
        assert document.activities_status == "not_started"


class _Unreachable:
    def complete(self, messages: list[Message]) -> str:
        raise ChatModelError(f"нет связи ({len(messages)} сообщений)")


def test_failed_blocks_are_not_empty_results(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES)
        ActivityStage(_Unreachable(), max_chars=12_000, retries=2).run(session, document_id)
        document = session.get(Document, document_id)
        blocks = session.scalars(select(ActivityBlock)).all()
        issues = session.scalars(select(ActivityIssue)).all()

        assert {block.status for block in blocks} == {"failed"}
        assert all(block.attempts == 1 for block in blocks)
        assert len(issues) == len(blocks)
        assert {(issue.issue_type, issue.is_blocking) for issue in issues} == {("block_failed", 1)}
        assert document is not None
        assert document.activities_status == "needs_review"


def test_rerun_replaces_results_and_fail_marks_the_stage(engine: Engine) -> None:
    with Session(engine) as session:
        document_id = parse_edition(session, 9)
        add_entities(session, document_id, ED9_ENTITIES)
        stage = ActivityStage(ScriptedModel(ED9_HANDLERS), max_chars=12_000, retries=2)
        stage.run(session, document_id)
        first = session.scalar(select(func.count()).select_from(ActivitySource))
        stage.run(session, document_id)

        assert session.scalar(select(func.count()).select_from(ActivitySource)) == first
        assert session.scalar(select(func.count()).select_from(ActivityRecord)) == 8
        stage.fail(session, document_id, "Внутренняя ошибка этапа activities: boom")
        document = session.get(Document, document_id)
        assert document is not None
        assert document.activities_status == "failed"
        last = session.scalars(select(ActivityIssue).order_by(ActivityIssue.id.desc())).first()
        assert last is not None
        assert (last.issue_type, last.is_blocking) == ("other", 1)
