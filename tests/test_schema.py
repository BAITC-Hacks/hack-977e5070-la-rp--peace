import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from la_rp_peace.db import make_engine
from la_rp_peace.models import create_schema


@pytest.fixture
def engine() -> Engine:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return engine


def _document(connection: Connection, name: str) -> int:
    result = connection.execute(
        text(
            "INSERT INTO documents (file_name, source_format, file_size_bytes, content_sha256, doc_set) "
            "VALUES (:name, 'docx', 1, :sha, 'before') RETURNING id",
        ),
        {"name": name, "sha": "a" * 64},
    )
    document_id: int = result.scalar_one()
    return document_id


def test_methodology_and_backend_tables_exist(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())

    assert {"documents", "document_nodes", "parsing_issues", "document_files"} <= tables
    assert "doc_set" in {column["name"] for column in inspect(engine).get_columns("documents")}


def test_schema_creation_is_idempotent(engine: Engine) -> None:
    create_schema(engine)

    assert "documents" in inspect(engine).get_table_names()


def test_deleting_a_document_cascades(engine: Engine) -> None:
    with engine.begin() as connection:
        document = _document(connection, "a.docx")
        connection.execute(
            text(
                "INSERT INTO document_nodes (document_id, position, node_type, text, source_start, source_end) "
                "VALUES (:d, 0, 'section', '1. Общие', 0, 8)",
            ),
            {"d": document},
        )
        connection.execute(
            text("INSERT INTO document_files (document_id, content) VALUES (:d, x'00')"), {"d": document}
        )
        connection.execute(text("DELETE FROM documents WHERE id = :d"), {"d": document})
        remaining = connection.execute(
            text("SELECT (SELECT count(*) FROM document_nodes) + (SELECT count(*) FROM document_files)"),
        ).scalar_one()

    assert remaining == 0


def test_parent_must_belong_to_the_same_document(engine: Engine) -> None:
    with engine.begin() as connection:
        first, second = _document(connection, "a.docx"), _document(connection, "b.docx")
        parent = connection.execute(
            text(
                "INSERT INTO document_nodes (document_id, position, node_type, text, source_start, source_end) "
                "VALUES (:d, 0, 'section', '1.', 0, 2) RETURNING id",
            ),
            {"d": first},
        ).scalar_one()
    foreign_child = text(
        "INSERT INTO document_nodes "
        "(document_id, parent_id, position, node_type, text, source_start, source_end) "
        "VALUES (:d, :p, 0, 'clause', '1.1.', 0, 4)",
    )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(foreign_child, {"d": second, "p": parent})


def test_invalid_doc_set_is_rejected(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO documents (file_name, source_format, file_size_bytes, content_sha256, doc_set) "
                "VALUES ('a.docx', 'docx', 1, :sha, 'during')",
            ),
            {"sha": "a" * 64},
        )
