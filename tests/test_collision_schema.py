"""Stage 4.1 tables keep every reference inside one document and never store an error as a verdict."""

import json
from typing import Any

import pytest
from collision_support import CollisionDoc
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.db import make_engine
from la_rp_peace.models import create_schema


@pytest.fixture
def engine() -> Engine:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return engine


def _document(session: Session, name: str) -> dict[str, int]:
    doc = CollisionDoc(session, name)
    first = doc.entity("А", "position")
    second = doc.entity("Б", "position")
    ids = {"document": doc.id, "a": doc.record(first, "ведёт учёт"), "b": doc.record(second, "ведёт реестр")}
    ids["node"] = doc.node("Прочее.")
    session.commit()
    return ids


PAIR = (
    "INSERT INTO collision_pairs (document_id, pair_key, side_a_kind, side_a_record_id, side_a_view_id, side_b_kind, "
    "side_b_record_id, side_b_view_id, bases, basis_details, similarity, embedding_model, metric, text_format, "
    "question_id, status, verdict, explanation, error, attempts) "
    "VALUES (:d, :key, 'record', :a, NULL, 'record', :b, NULL, '[\"category\"]', '[]', :sim, 'm', 'cosine', "
    "'activity-v1', 'q1', :status, :verdict, :explanation, :error, 1)"
)
SOURCE = (
    "INSERT INTO collision_sources (document_id, pair_id, node_id, quote, quote_start, quote_end, supports) "
    "VALUES (:d, :pair, :node, 'Прочее', 0, 6, '[\"context\"]')"
)
CHECKED = {"status": "checked", "verdict": "collision", "explanation": "обоснование", "error": None, "sim": 0.9}


def _pair(session: Session, ids: dict[str, int], **overrides: Any) -> int:
    values = {"d": ids["document"], "key": f"R{ids['a']}|R{ids['b']}", "a": ids["a"], "b": ids["b"]} | CHECKED
    new_id: int = session.execute(text(PAIR + " RETURNING id"), values | overrides).scalar_one()
    return new_id


def test_consistent_rows_are_accepted_and_cascade(engine: Engine) -> None:
    session = sessionmaker(engine)()
    ids = _document(session, "a.docx")
    pair = _pair(session, ids)
    session.execute(text(SOURCE), {"d": ids["document"], "pair": pair, "node": ids["node"]})
    session.execute(text("DELETE FROM documents"))
    left = session.execute(
        text("SELECT (SELECT count(*) FROM collision_pairs) + (SELECT count(*) FROM collision_sources)")
    )

    assert left.scalar_one() == 0


@pytest.mark.parametrize("field", ["a", "b"])
def test_pair_sides_from_another_document_are_rejected(engine: Engine, field: str) -> None:
    session = sessionmaker(engine)()
    mine, foreign = _document(session, "a.docx"), _document(session, "b.docx")

    with pytest.raises(IntegrityError):
        _pair(session, mine, **{field: foreign[field], "key": "other"})


def test_source_nodes_and_view_records_from_another_document_are_rejected(engine: Engine) -> None:
    session = sessionmaker(engine)()
    mine, foreign = _document(session, "a.docx"), _document(session, "b.docx")
    pair = _pair(session, mine)
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(text(SOURCE), {"d": mine["document"], "pair": pair, "node": foreign["node"]})
    session.rollback()
    view = session.execute(
        text(
            "INSERT INTO collision_views (document_id, provision_key, record_type, formulation, "
            "participant_entity_ids, embedded_text) VALUES (:d, '0000000000000001', 'function', 'ф', :p, 'т') "
            "RETURNING id"
        ),
        {"d": mine["document"], "p": json.dumps([1])},
    ).scalar_one()
    with pytest.raises(IntegrityError):
        session.execute(
            text("INSERT INTO collision_view_records (document_id, view_id, record_id) VALUES (:d, :v, :r)"),
            {"d": mine["document"], "v": view, "r": foreign["a"]},
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "error", "verdict": "collision", "explanation": None, "error": "нет ответа"},
        {"status": "error", "verdict": None, "explanation": None, "error": None},
        {"status": "checked", "verdict": None},
        {"status": "checked", "explanation": " "},
        {"sim": 0.75},
    ],
)
def test_outcome_and_threshold_constraints(engine: Engine, overrides: dict[str, Any]) -> None:
    session = sessionmaker(engine)()
    ids = _document(session, "a.docx")

    with pytest.raises(IntegrityError):
        _pair(session, ids, **overrides)


def test_a_pair_is_stored_once_and_never_with_itself(engine: Engine) -> None:
    session = sessionmaker(engine)()
    ids = _document(session, "a.docx")
    _pair(session, ids)
    session.commit()

    with pytest.raises(IntegrityError):
        _pair(session, ids)
    session.rollback()
    with pytest.raises(IntegrityError):
        _pair(session, ids, b=ids["a"], key="self")
