"""Stage 3 tables keep every reference inside one document."""

from typing import Any

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from la_rp_peace.db import make_engine
from la_rp_peace.models import create_schema


@pytest.fixture
def engine() -> Engine:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return engine


def _insert(connection: Connection, sql: str, **values: Any) -> int:
    new_id: int = connection.execute(text(sql + " RETURNING id"), values).scalar_one()
    return new_id


def _document(connection: Connection) -> dict[str, int]:
    """A document with one node, one entity and one record; returns their ids."""
    document = _insert(
        connection,
        "INSERT INTO documents (file_name, source_format, file_size_bytes, content_sha256) "
        "VALUES ('a.docx', 'docx', 1, :sha)",
        sha="a" * 64,
    )
    node = _insert(
        connection,
        "INSERT INTO document_nodes (document_id, position, node_type, text, source_start, source_end) "
        "VALUES (:d, 0, 'clause', '1.1. Отдел проверяет.', 0, 21)",
        d=document,
    )
    entity = _insert(
        connection,
        "INSERT INTO entities (document_id, parent_status, name, entity_type) VALUES (:d, 'unknown', 'Отдел', 'отдел')",
        d=document,
    )
    record = _insert(
        connection,
        "INSERT INTO activity_records (document_id, record_type, formulation) "
        "VALUES (:d, 'function', 'Отдел проверяет')",
        d=document,
    )
    return {"document": document, "node": node, "entity": entity, "record": record}


BINDING = (
    "INSERT INTO activity_bindings (document_id, record_id, entity_id, designation, participation, note) "
    "VALUES (:d, :r, :e, 'Отдел', 'individual', :note)"
)
SOURCE = (
    "INSERT INTO activity_sources "
    "(document_id, record_id, binding_id, node_id, quote, quote_start, quote_end, supports) "
    "VALUES (:d, :r, :b, :n, 'проверяет', 11, 20, '[\"formulation\"]')"
)


def test_a_consistent_document_is_accepted_and_cascades(engine: Engine) -> None:
    with engine.begin() as connection:
        ids = _document(connection)
        bound = _insert(connection, BINDING, d=ids["document"], r=ids["record"], e=ids["entity"], note=None)
        _insert(connection, SOURCE, d=ids["document"], r=None, b=bound, n=ids["node"])
        connection.execute(text("DELETE FROM documents"))
        left = connection.execute(
            text("SELECT (SELECT count(*) FROM activity_records) + (SELECT count(*) FROM activity_sources)"),
        ).scalar_one()

    assert left == 0


@pytest.mark.parametrize(
    ("statement", "owner"),
    [
        (BINDING, "entity"),
        (BINDING, "record"),
        (SOURCE, "node"),
        (SOURCE, "record"),
    ],
)
def test_references_to_another_document_are_rejected(engine: Engine, statement: str, owner: str) -> None:
    with engine.begin() as connection:
        mine, foreign = _document(connection), _document(connection)
    values = {
        "d": mine["document"],
        "r": mine["record"],
        "e": mine["entity"],
        "note": None,
        "b": None,
        "n": mine["node"],
    }
    values[{"entity": "e", "record": "r", "node": "n"}[owner]] = foreign[owner]

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(statement), values)


def test_unresolved_binding_needs_a_note_and_a_source_one_owner(engine: Engine) -> None:
    with engine.begin() as connection:
        ids = _document(connection)
    base = {"d": ids["document"], "r": ids["record"]}

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(BINDING), base | {"e": None, "note": None})
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(SOURCE), base | {"b": None, "r": None, "n": ids["node"]})
    with engine.begin() as connection:
        connection.execute(text(BINDING), base | {"e": None, "note": "Исполнитель не в реестре"})


def test_activities_status_is_checked(engine: Engine) -> None:
    with engine.begin() as connection:
        ids = _document(connection)
    update = text("UPDATE documents SET activities_status = 'started' WHERE id = :d")

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(update, {"d": ids["document"]})
