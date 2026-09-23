"""Stage 4.2 tables keep every reference inside one document and reject impossible decisions."""

from collections.abc import Iterator
from typing import Any

import pytest
from cascade_support import DocumentBuilder
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from la_rp_peace.db import make_engine
from la_rp_peace.models import CascadeFinding, CascadeGroup, CascadeLink, Document, create_schema


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    yield engine
    engine.dispose()


def _document(session: Session) -> dict[str, int]:
    builder = DocumentBuilder(session)
    department = builder.entity("Департамент аудита")
    division = builder.entity("Отдел проверок", department, category="division")
    task = builder.record(department, "Задача департамента", "task")
    function = builder.record(division, "Функция отдела")
    group = CascadeGroup(
        document_id=builder.id,
        entity_id=department.id,
        child_entity_ids=f"[{division.id}]",
        parent_record_ids=f"[{task.id}]",
        child_record_ids=f"[{function.id}]",
    )
    session.add(group)
    session.flush()
    return {
        "document": builder.id,
        "department": department.id,
        "division": division.id,
        "task": task.id,
        "function": function.id,
        "group": group.id,
    }


def _link(ids: dict[str, int], **overrides: Any) -> CascadeLink:
    values: dict[str, Any] = {
        "document_id": ids["document"],
        "group_id": ids["group"],
        "child_entity_id": ids["division"],
        "child_record_id": ids["function"],
        "parent_record_id": ids["task"],
        "best_similarity": 0.9,
        "decision": "auto",
        "status": "accepted",
        "embedding_model": "fake",
        "metric": "cosine",
        "text_format": "activity-v1",
    }
    return CascadeLink(**(values | overrides))


def _rejected(engine: Engine, row: object) -> None:
    with Session(engine) as session:
        session.add(row)
        with pytest.raises(IntegrityError):
            session.flush()


def test_a_consistent_cascade_is_accepted_and_deleted_with_its_document(engine: Engine) -> None:
    with Session(engine) as session:
        ids = _document(session)
        link = _link(ids)
        session.add(link)
        session.flush()
        session.add(
            CascadeFinding(
                document_id=ids["document"],
                kind="child_without_parent",
                reason="pending",
                final=0,
                record_id=ids["function"],
                entity_id=ids["division"],
                group_id=ids["group"],
                link_id=link.id,
                message="Верификация не выполнена",
            ),
        )
        session.commit()
        session.execute(delete(Document))
        session.commit()
        left = sum(
            session.scalar(select(func.count()).select_from(model)) or 0 for model in (CascadeGroup, CascadeLink)
        )
        assert left + (session.scalar(select(func.count()).select_from(CascadeFinding)) or 0) == 0


@pytest.mark.parametrize("field", ["child_record_id", "parent_record_id", "child_entity_id", "group_id"])
def test_link_references_to_another_document_are_rejected(engine: Engine, field: str) -> None:
    with Session(engine) as session:
        mine, foreign = _document(session), _document(session)
        session.commit()
    source = {
        "child_record_id": "function",
        "parent_record_id": "task",
        "child_entity_id": "division",
        "group_id": "group",
    }[field]

    _rejected(engine, _link(mine, **{field: foreign[source]}))


def test_group_and_finding_references_to_another_document_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        mine, foreign = _document(session), _document(session)
        session.commit()

    _rejected(
        engine,
        CascadeGroup(
            document_id=mine["document"],
            entity_id=foreign["division"],
            child_entity_ids="[]",
            parent_record_ids="[]",
            child_record_ids="[]",
        ),
    )
    _rejected(
        engine,
        CascadeFinding(
            document_id=mine["document"],
            kind="needs_clarification",
            reason="parent_unknown",
            final=0,
            record_id=foreign["function"],
            entity_id=mine["division"],
            message="Родитель не установлен",
        ),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"parent_record_id": None},
        {"decision": "llm", "verdict": "rejected"},
        {"decision": "none", "status": "not_found", "verdict": "confirmed"},
        {"status": "rejected"},
        {"parent_record_id": "function"},
    ],
)
def test_impossible_decisions_are_rejected(engine: Engine, overrides: dict[str, Any]) -> None:
    with Session(engine) as session:
        ids = _document(session)
        session.commit()
    if overrides.get("parent_record_id") == "function":
        overrides = {"parent_record_id": ids["function"]}

    _rejected(engine, _link(ids, **overrides))


def test_one_decision_per_child_function(engine: Engine) -> None:
    with Session(engine) as session:
        ids = _document(session)
        session.add(_link(ids, status="pending", decision="llm", error="Вопрос не был задан"))
        session.commit()

    _rejected(engine, _link(ids))
