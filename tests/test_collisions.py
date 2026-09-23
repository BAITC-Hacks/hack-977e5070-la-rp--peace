"""Stage 4.1 end to end on small documents built through the ORM (offline, scripted vectors and model)."""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from collision_support import (
    EXACT_075,
    GOOD_EXPLANATION,
    CollisionDoc,
    ScriptedEmbedder,
    ScriptedVerifier,
    collision_answer,
    sides_of,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.collisions.pipeline import CollisionStage
from la_rp_peace.collisions.prompt import REQUIRED_INSTRUCTION, SYSTEM_PROMPT
from la_rp_peace.db import make_engine
from la_rp_peace.models import (
    CollisionPair,
    CollisionRun,
    CollisionSource,
    CollisionView,
    CollisionViewRecord,
    Document,
    create_schema,
)

METHODOLOGY = Path(__file__).resolve().parent.parent / "methodology" / "04_1_function_collisions.md"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def _angle(degrees: float) -> list[float]:
    return [math.cos(math.radians(degrees)), math.sin(math.radians(degrees))]


def _run(session: Session, doc: CollisionDoc, embedder: ScriptedEmbedder, model: ScriptedVerifier) -> Document:
    session.commit()
    CollisionStage(model, embedder, retries=1).run(session, doc.id)
    document = session.get(Document, doc.id)
    assert document is not None
    return document


def _pairs(session: Session, document_id: int) -> list[CollisionPair]:
    return list(
        session.scalars(
            select(CollisionPair).where(CollisionPair.document_id == document_id).order_by(CollisionPair.id)
        )
    )


def _siblings(doc: CollisionDoc, *names: str, category: str = "position") -> dict[str, int]:
    parent = doc.entity("Отдел аудита", "department")
    return {name: doc.entity(name, category, parent) for name in names}


def test_system_prompt_carries_the_required_instruction_verbatim() -> None:
    text = METHODOLOGY.read_text(encoding="utf-8")
    block = text.split("Обязательное требование к ИИ:", 1)[1].split("\n\n", 2)[1]
    quoted = " ".join(line.removeprefix(">").strip() for line in block.splitlines())
    assert " ".join(REQUIRED_INSTRUCTION.split()) == " ".join(quoted.split())
    assert REQUIRED_INSTRUCTION in SYSTEM_PROMPT
    assert all(f"\n{number}. " in SYSTEM_PROMPT for number in range(1, 7))


def test_exactly_threshold_is_not_sent(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "Аудитор 1", "Аудитор 2")
    doc.record(ids["Аудитор 1"], "готовит отчёт о проверках")
    doc.record(ids["Аудитор 2"], "составляет отчёт о проверках")
    embedder = ScriptedEmbedder({"готовит отчёт о проверках": [1.0, 0.0], "составляет отчёт о проверках": EXACT_075})
    model = ScriptedVerifier()

    document = _run(session, doc, embedder, model)

    assert model.requests == []
    assert _pairs(session, doc.id) == []
    run = session.get(CollisionRun, doc.id)
    assert run is not None
    assert (run.local_pairs, run.local_above, run.category_pairs, run.category_above) == (1, 0, 1, 0)
    assert (run.compared_records, run.compared_views, run.threshold) == (2, 0, 0.75)
    assert document.collisions_status == "done"


def test_just_above_threshold_is_sent(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "Аудитор 1", "Аудитор 2")
    doc.record(ids["Аудитор 1"], "готовит отчёт о проверках")
    doc.record(ids["Аудитор 2"], "составляет отчёт о проверках")
    above = 0.7500001
    embedder = ScriptedEmbedder(
        {"готовит отчёт о проверках": [1.0, 0.0], "составляет отчёт о проверках": [above, math.sqrt(1 - above**2)]},
    )
    model = ScriptedVerifier()

    document = _run(session, doc, embedder, model)

    [pair] = _pairs(session, doc.id)
    assert pair.similarity > 0.75
    assert (pair.status, pair.verdict, pair.explanation) == ("checked", "collision", GOOD_EXPLANATION)
    assert (pair.embedding_model, pair.metric, pair.text_format) == ("fake-embedding", "cosine", "activity-v1")
    assert json.loads(pair.bases) == ["local", "category"]
    sources = session.scalars(select(CollisionSource).where(CollisionSource.pair_id == pair.id)).all()
    assert sorted(json.loads(source.supports)[0] for source in sources) == ["side_a", "side_b"]
    assert document.collisions_status == "needs_review"


def test_pair_found_by_both_paths_is_one_question_with_two_bases(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "Отдел А", "Отдел Б", category="division")
    doc.record(ids["Отдел А"], "ведёт реестр рисков")
    doc.record(ids["Отдел Б"], "формирует реестр рисков")
    embedder = ScriptedEmbedder({"ведёт реестр рисков": _angle(0), "формирует реестр рисков": _angle(10)})
    model = ScriptedVerifier()

    _run(session, doc, embedder, model)

    [pair] = _pairs(session, doc.id)
    assert json.loads(pair.bases) == ["local", "category"]
    assert {detail["basis"] for detail in json.loads(pair.basis_details)} == {"local", "category"}
    assert list(model.questions) == ["q1"]
    question = model.questions["q1"]
    assert "Основания поиска: local, category" in question
    assert "дети одного родителя «Отдел аудита»" in question
    assert "одна категория division" in question


def test_collisions_are_not_transitive(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б", "В")
    doc.record(ids["А"], "функция альфа")
    doc.record(ids["Б"], "функция бета")
    doc.record(ids["В"], "функция гамма")
    embedder = ScriptedEmbedder({"функция альфа": _angle(0), "функция бета": _angle(35), "функция гамма": _angle(70)})

    _run(session, doc, embedder, ScriptedVerifier())

    pairs = _pairs(session, doc.id)
    assert len(pairs) == 2
    assert all(pair.verdict == "collision" for pair in pairs)
    formulation_pairs = {pair.pair_key for pair in pairs}
    assert len(formulation_pairs) == 2
    run = session.get(CollisionRun, doc.id)
    assert run is not None
    assert (run.local_pairs, run.local_above) == (3, 2)


def test_joint_assignment_is_one_view(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "Специалист А", "Специалист Б", "Специалист В")
    node = doc.node("Специалист А и Специалист Б совместно готовят годовой отчёт о рисках.")
    key = doc.provision_key()
    joint = {"participation": "joint", "provision_key": key, "node": node, "participant_designation": "А и Б"}
    first = doc.record(ids["Специалист А"], "готовят годовой отчёт о рисках", **joint)
    second = doc.record(ids["Специалист Б"], "готовят годовой отчёт о рисках", **joint)
    duplicate = doc.record(ids["Специалист В"], "готовит годовой отчёт о рисках")
    own = doc.record(ids["Специалист А"], "составляет годовой отчёт о рисках")
    same = [1.0, 0.0]
    embedder = ScriptedEmbedder(
        {
            "готовят годовой отчёт о рисках": same,
            "готовит годовой отчёт о рисках": same,
            "составляет годовой отчёт о рисках": same,
        },
    )
    model = ScriptedVerifier()

    _run(session, doc, embedder, model)

    [view] = session.scalars(select(CollisionView)).all()
    members = session.scalars(select(CollisionViewRecord.record_id).where(CollisionViewRecord.view_id == view.id))
    assert sorted(members) == [first, second]
    assert json.loads(view.participant_entity_ids) == sorted([ids["Специалист А"], ids["Специалист Б"]])
    assert json.loads(view.categories) == ["position"]
    sides = {
        frozenset(
            (pair.side_a_record_id or f"V{pair.side_a_view_id}", pair.side_b_record_id or f"V{pair.side_b_view_id}")
        )
        for pair in _pairs(session, doc.id)
    }
    view_key = f"V{view.id}"
    # The view meets the individual duplicate and A's other function; A's and B's joint records never
    # appear on their own, and the view is never paired with its own participants' joint records.
    assert sides == {frozenset({view_key, duplicate}), frozenset({view_key, own}), frozenset({own, duplicate})}
    view_question = next(text for text in model.questions.values() if "совместное назначение" in text)
    assert "Специалист А" in view_question
    assert "Специалист Б" in view_question
    assert embedder.embedded_formulations().count("готовят годовой отчёт о рисках") == 1


@pytest.mark.parametrize("participation", ["each", "alternative"])
def test_each_and_alternative_are_not_consolidated(session: Session, participation: str) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    node = doc.node("А и Б проверяют сметы.")
    shared = {"participation": participation, "provision_key": doc.provision_key(), "node": node}
    first = doc.record(ids["А"], "проверяют сметы", **shared)
    second = doc.record(ids["Б"], "проверяют сметы", **shared)
    embedder = ScriptedEmbedder({"проверяют сметы": [1.0, 0.0]})

    _run(session, doc, embedder, ScriptedVerifier())

    assert session.scalars(select(CollisionView)).all() == []
    [pair] = _pairs(session, doc.id)
    assert {pair.side_a_record_id, pair.side_b_record_id} == {first, second}


def test_rights_are_context_only_and_generalized_flag_is_passed(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    doc.record(ids["А"], "запрашивает документы", record_type="right")
    doc.record(ids["Б"], "запрашивает документы у подразделений", record_type="right")
    doc.record(ids["А"], "выполняет иные поручения", specificity="generalized")
    doc.record(ids["Б"], "выполняет прочие поручения")
    embedder = ScriptedEmbedder(
        {"выполняет иные поручения": [1.0, 0.0], "выполняет прочие поручения": [1.0, 0.0]},
    )
    model = ScriptedVerifier()

    _run(session, doc, embedder, model)

    assert sorted(set(embedder.embedded_formulations())) == ["выполняет иные поручения", "выполняет прочие поручения"]
    [pair] = _pairs(session, doc.id)
    question = model.questions[pair.question_id]
    assert "right: запрашивает документы" in question
    assert "ОБОБЩЁННАЯ формулировка" in question
    run = session.get(CollisionRun, doc.id)
    assert run is not None
    assert (run.compared_records, run.context_records) == (2, 2)


def test_unanswered_question_is_an_error_not_a_verdict(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    doc.record(ids["А"], "ведёт учёт")
    doc.record(ids["Б"], "ведёт учёт договоров")
    embedder = ScriptedEmbedder({"ведёт учёт": [1.0, 0.0], "ведёт учёт договоров": [1.0, 0.0]})
    model = ScriptedVerifier(decide=lambda qid, _text, _attempt: {"question_id": qid, "verdict": "maybe"})

    document = _run(session, doc, embedder, model)

    [pair] = _pairs(session, doc.id)
    assert (pair.status, pair.verdict, pair.explanation) == ("error", None, None)
    assert pair.error is not None
    assert "Нет корректного ответа за 2 попыток" in pair.error
    assert pair.attempts == 2
    assert document.collisions_status == "needs_review"


def test_collision_citing_one_side_is_sent_back(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    doc.record(ids["А"], "ведёт учёт")
    doc.record(ids["Б"], "ведёт учёт договоров")
    embedder = ScriptedEmbedder({"ведёт учёт": [1.0, 0.0], "ведёт учёт договоров": [1.0, 0.0]})

    def decide(qid: str, text: str, attempt: int) -> dict[str, Any]:
        answer = collision_answer(qid, text)
        if attempt == 1:
            answer["sources"] = answer["sources"][:1]
        return answer

    model = ScriptedVerifier(decide=decide)

    _run(session, doc, embedder, model)

    assert "нужен источник side_b из узлов стороны B" in model.requests[1][-1].content
    [pair] = _pairs(session, doc.id)
    assert (pair.verdict, pair.attempts) == ("collision", 2)


def test_similarity_only_explanation_is_rejected(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    doc.record(ids["А"], "ведёт учёт")
    doc.record(ids["Б"], "ведёт учёт договоров")
    embedder = ScriptedEmbedder({"ведёт учёт": [1.0, 0.0], "ведёт учёт договоров": [1.0, 0.0]})

    def decide(qid: str, text: str, _attempt: int) -> dict[str, Any]:
        answer = collision_answer(qid, text)
        answer["explanation"] = "Тексты похожи, сходство 0.99."
        return answer

    _run(session, doc, embedder, ScriptedVerifier(decide=decide))

    [pair] = _pairs(session, doc.id)
    assert pair.status == "error"
    assert pair.error is not None
    assert "объяснение не обосновывает вывод" in pair.error


def test_no_collision_and_insufficient_data(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    doc.record(ids["А"], "готовит отчёт по региону Север")
    doc.record(ids["Б"], "готовит отчёт по региону Юг")
    embedder = ScriptedEmbedder({"готовит отчёт по региону Север": [1.0, 0.0], "готовит отчёт по региону Юг": [1, 0]})

    def decide(qid: str, text: str, _attempt: int) -> dict[str, Any]:
        a, b = sides_of(text)
        return {
            "question_id": qid,
            "verdict": "no_collision",
            "explanation": "Стороны готовят отчёты по разным территориям: сторона A — по региону Север, "
            "сторона B — по региону Юг, поэтому предмет работы разграничен документом.",
            "sources": [
                {"node_id": a.node_id, "quote": "региону Север", "supports": ["side_a", "context"]},
                {"node_id": b.node_id, "quote": "региону Юг", "supports": ["side_b", "context"]},
            ],
        }

    document = _run(session, doc, embedder, ScriptedVerifier(decide=decide))

    [pair] = _pairs(session, doc.id)
    assert pair.verdict == "no_collision"
    assert document.collisions_status == "done"


@pytest.mark.parametrize(("category", "pairs"), [("unclear", 0), ("other", 0), ("department", 1)])
def test_category_path_needs_a_real_level(session: Session, category: str, pairs: int) -> None:
    doc = CollisionDoc(session)
    first = doc.entity("Первый", category)
    second = doc.entity("Второй", category)
    doc.record(first, "согласует бюджет")
    doc.record(second, "согласует бюджет проекта")
    embedder = ScriptedEmbedder({"согласует бюджет": [1.0, 0.0], "согласует бюджет проекта": [1.0, 0.0]})

    _run(session, doc, embedder, ScriptedVerifier())

    found = _pairs(session, doc.id)
    assert len(found) == pairs
    assert all(json.loads(pair.bases) == ["category"] for pair in found)


def test_same_entity_and_different_parents_are_not_paired(session: Session) -> None:
    doc = CollisionDoc(session)
    left = doc.entity("Блок 1", "block")
    right = doc.entity("Блок 2", "block")
    first = doc.entity("Сотрудник 1", "position", left)
    second = doc.entity("Отдел 2", "department", right)
    doc.record(first, "контролирует сроки")
    doc.record(first, "контролирует сроки проектов")
    doc.record(second, "контролирует сроки работ")
    vectors = {"контролирует сроки": [1.0, 0.0], "контролирует сроки проектов": [1.0, 0.0]}
    embedder = ScriptedEmbedder(vectors | {"контролирует сроки работ": [1.0, 0.0]})

    _run(session, doc, embedder, ScriptedVerifier())

    assert _pairs(session, doc.id) == []
    assert embedder.calls == []


def test_stage_is_skipped_until_activities_are_done(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    doc.record(ids["А"], "ведёт учёт")
    doc.record(ids["Б"], "ведёт учёт договоров")
    embedder = ScriptedEmbedder({"ведёт учёт": [1.0, 0.0], "ведёт учёт договоров": [1.0, 0.0]})
    _run(session, doc, embedder, ScriptedVerifier())
    assert len(_pairs(session, doc.id)) == 1
    doc.document.activities_status = "running"

    document = _run(session, doc, embedder, ScriptedVerifier())

    assert document.collisions_status == "not_started"
    assert _pairs(session, doc.id) == []
    assert session.get(CollisionRun, doc.id) is None
    assert len(embedder.calls) == 1


def test_rerun_replaces_rows(session: Session) -> None:
    doc = CollisionDoc(session)
    ids = _siblings(doc, "А", "Б")
    node = doc.node("А и Б совместно ведут учёт.")
    joint = {"participation": "joint", "provision_key": doc.provision_key(), "node": node}
    doc.record(ids["А"], "ведут учёт", **joint)
    doc.record(ids["Б"], "ведут учёт", **joint)
    solo = doc.entity("В", "position")
    doc.record(solo, "ведёт учёт")
    embedder = ScriptedEmbedder({"ведут учёт": [1.0, 0.0], "ведёт учёт": [1.0, 0.0]})

    _run(session, doc, embedder, ScriptedVerifier())
    first = [(pair.id, pair.pair_key) for pair in _pairs(session, doc.id)]
    _run(session, doc, embedder, ScriptedVerifier())
    second = [(pair.id, pair.pair_key) for pair in _pairs(session, doc.id)]

    assert [key for _id, key in first] == [key for _id, key in second]
    assert len(second) == 1
    assert session.scalar(select(func.count()).select_from(CollisionView)) == 1
    assert session.scalar(select(func.count()).select_from(CollisionSource)) == 2
    assert len(embedder.calls) == 1  # the second run reuses the cached vectors
