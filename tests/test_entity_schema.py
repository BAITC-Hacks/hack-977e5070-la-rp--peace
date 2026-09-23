from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from la_rp_peace.db import make_engine
from la_rp_peace.models import create_schema


@pytest.fixture
def connection() -> Iterator[Connection]:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    with engine.connect() as connection:
        yield connection


def _insert(connection: Connection, sql: str, **values: object) -> int:
    row_id: int = connection.execute(text(f"{sql} RETURNING id"), values).scalar_one()
    return row_id


def _document(connection: Connection) -> tuple[int, int, int]:
    """A document with one node and one entity; returns (document, node, entity)."""
    document = _insert(
        connection,
        "INSERT INTO documents (file_name, source_format, file_size_bytes, content_sha256) "
        "VALUES ('a.docx', 'docx', 1, :sha)",
        sha="a" * 64,
    )
    node = _insert(
        connection,
        "INSERT INTO document_nodes (document_id, position, node_type, text, source_start, source_end) "
        "VALUES (:d, 0, 'clause', '3.4. ДИТААД', 0, 11)",
        d=document,
    )
    entity = _insert(
        connection,
        "INSERT INTO entities (document_id, parent_status, name, entity_type) "
        "VALUES (:d, 'unknown', 'ДИТААД', 'департамент')",
        d=document,
    )
    return document, node, entity


def test_parent_must_be_in_the_same_document(connection: Connection) -> None:
    _, _, foreign = _document(connection)
    document, _, _ = _document(connection)

    with pytest.raises(IntegrityError):
        _insert(
            connection,
            "INSERT INTO entities (document_id, parent_id, parent_status, name, entity_type) "
            "VALUES (:d, :p, 'resolved', 'Аудитор', 'должность')",
            d=document,
            p=foreign,
        )


def test_sources_cannot_cite_another_documents_node(connection: Connection) -> None:
    _, foreign_node, _ = _document(connection)
    document, _, entity = _document(connection)

    with pytest.raises(IntegrityError):
        _insert(
            connection,
            "INSERT INTO entity_sources (document_id, entity_id, node_id, quote, quote_start, quote_end, supports) "
            "VALUES (:d, :e, :n, 'ДИТААД', 5, 11, '[\"name\"]')",
            d=document,
            e=entity,
            n=foreign_node,
        )


def test_relations_stay_inside_one_document(connection: Connection) -> None:
    _, _, foreign = _document(connection)
    document, _, entity = _document(connection)

    with pytest.raises(IntegrityError):
        _insert(
            connection,
            "INSERT INTO entity_relations (document_id, from_entity_id, to_entity_id, relation_type) "
            "VALUES (:d, :a, :b, 'reports_to')",
            d=document,
            a=entity,
            b=foreign,
        )


@pytest.mark.parametrize(
    ("own_parent", "status"),
    [(True, "resolved"), (False, "resolved"), (False, "unknown")],
    ids=["own-parent", "resolved-without-parent", "parent-with-unknown-status"],
)
def test_parent_and_status_are_coupled(connection: Connection, own_parent: bool, status: str) -> None:
    document, _, entity = _document(connection)
    company = _insert(
        connection,
        "INSERT INTO entities (document_id, parent_status, name, entity_type) "
        "VALUES (:d, 'root', 'Общество', 'компания')",
        d=document,
    )
    parent = entity if own_parent else (company if status == "unknown" else None)

    with pytest.raises(IntegrityError):
        connection.execute(
            text("UPDATE entities SET parent_id = :p, parent_status = :s WHERE id = :e"),
            {"p": parent, "s": status, "e": entity},
        )
