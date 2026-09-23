"""Stage 4.2 with scripted embeddings and verdicts: the control examples of methodology §7 and more."""

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from cascade_support import (
    DocumentBuilder,
    FakeEmbedder,
    ScriptedVerifier,
    basis,
    exact_child,
    solved_child,
    unit,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.cascade.chains import build_chains
from la_rp_peace.cascade.pipeline import CascadeStage
from la_rp_peace.db import make_engine
from la_rp_peace.embeddings import METRIC, TEXT_FORMAT
from la_rp_peace.models import CascadeFinding, CascadeGroup, CascadeLink, Document, EmbeddingCache, create_schema

RETRIES = 1


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'cascade.sqlite3').as_posix()}")
    create_schema(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@dataclass
class Run:
    """What one stage run left in the database."""

    status: str
    links: list[CascadeLink]
    findings: list[CascadeFinding]
    groups: list[CascadeGroup]
    verifier: ScriptedVerifier
    embedder: FakeEmbedder

    def link(self, child_record_id: int) -> CascadeLink:
        return next(link for link in self.links if link.child_record_id == child_record_id)

    def about(self, record_id: int) -> list[tuple[str, str, int]]:
        return [(f.kind, f.reason, f.final) for f in self.findings if f.record_id == record_id]


def _run(
    factory: sessionmaker[Session],
    document_id: int,
    vectors: Mapping[str, Sequence[float]],
    verifier: ScriptedVerifier | None = None,
) -> Run:
    verifier = verifier or ScriptedVerifier()
    embedder = FakeEmbedder(vectors)
    with factory() as session:
        CascadeStage(verifier, embedder, retries=RETRIES).run(session, document_id)
    with factory() as session:
        document = session.get(Document, document_id)
        assert document is not None

        def rows[T: (CascadeLink, CascadeFinding, CascadeGroup)](model: type[T]) -> list[T]:
            return list(session.scalars(select(model).where(model.document_id == document_id).order_by(model.id)))

        return Run(
            document.cascade_status,
            rows(CascadeLink),
            rows(CascadeFinding),
            rows(CascadeGroup),
            verifier,
            embedder,
        )


def _two_levels(factory: sessionmaker[Session], parents: int, children: int) -> tuple[int, list[int], list[int]]:
    """Department with ``parents`` functions and one division with ``children`` functions."""
    with factory() as session:
        builder = DocumentBuilder(session)
        department = builder.entity("Департамент аудита")
        division = builder.entity("Отдел проверок", department, category="division")
        parent_ids = [builder.record(department, f"Функция департамента {n}", "task").id for n in range(parents)]
        child_ids = [builder.record(division, f"Функция отдела {n}").id for n in range(children)]
        session.commit()
        return builder.id, parent_ids, child_ids


def _parents(count: int) -> dict[str, list[float]]:
    return {f"Функция департамента {n}": basis(n) for n in range(count)}


def test_two_children_above_085_share_one_parent_automatically(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=1, children=2)
    vectors = _parents(1) | {
        "Функция отдела 0": exact_child({0: 0.91}),
        "Функция отдела 1": exact_child({0: 0.89}),
    }

    run = _run(factory, document_id, vectors)

    assert [(link.decision, link.status, link.parent_record_id) for link in run.links] == [
        ("auto", "accepted", parents[0]),
        ("auto", "accepted", parents[0]),
    ]
    assert [link.best_similarity for link in run.links] == [0.91, 0.89]
    assert (run.links[0].embedding_model, run.links[0].metric, run.links[0].text_format) == (
        FakeEmbedder.model,
        METRIC,
        TEXT_FORMAT,
    )
    assert run.verifier.calls == []
    assert run.findings == []
    assert run.status == "done"
    assert build_chains((parents[0], child) for child in children) == [[parents[0], c] for c in children]


def test_only_the_best_of_two_high_candidates_becomes_the_parent(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=2, children=1)
    first, second = basis(0), unit([0.6, 0.8])
    vectors = {
        "Функция департамента 0": first,
        "Функция департамента 1": second,
        "Функция отдела 0": solved_child([first, second], [0.88, 0.87]),
    }

    run = _run(factory, document_id, vectors)

    link = run.link(children[0])
    assert (link.decision, link.status, link.parent_record_id) == ("auto", "accepted", parents[0])
    assert link.best_similarity == pytest.approx(0.88)
    assert run.about(parents[1]) == [("parent_without_children", "no_accepted_child", 1)]


@pytest.mark.parametrize(("verdict", "status"), [("confirmed", "accepted"), ("rejected", "not_confirmed")])
def test_exactly_085_asks_one_question(factory: sessionmaker[Session], verdict: str, status: str) -> None:
    document_id, parents, children = _two_levels(factory, parents=1, children=1)
    vectors = _parents(1) | {"Функция отдела 0": exact_child({0: 0.85})}

    run = _run(factory, document_id, vectors, ScriptedVerifier(default=verdict))

    link = run.link(children[0])
    assert run.verifier.calls == [[f"q{children[0]}"]]
    assert link.best_similarity == 0.85
    assert (link.decision, link.verdict, link.status, link.parent_record_id) == ("llm", verdict, status, parents[0])
    question = run.verifier.conversations[0][-1].content
    assert "Функция департамента 0" in question
    assert "Функция отдела 0" in question
    assert "0.8500" in question
    assert "[node " in question
    assert "«Функция отдела 0»" in question


def test_exactly_050_is_no_pair_without_a_question(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=1, children=1)
    vectors = _parents(1) | {"Функция отдела 0": exact_child({0: 0.5})}

    run = _run(factory, document_id, vectors)

    link = run.link(children[0])
    assert link.best_similarity == 0.5
    assert (link.decision, link.status, link.parent_record_id) == ("none", "not_found", parents[0])
    assert run.verifier.calls == []
    assert run.about(children[0]) == [("child_without_parent", "not_found", 1)]
    assert run.about(parents[0]) == [("parent_without_children", "no_accepted_child", 1)]
    assert run.status == "needs_review"


def test_a_rejected_best_candidate_does_not_fall_back_to_the_second(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=2, children=1)
    first, second = basis(0), unit([0.6, 0.8])
    vectors = {
        "Функция департамента 0": first,
        "Функция департамента 1": second,
        "Функция отдела 0": solved_child([first, second], [0.80, 0.75]),
    }

    run = _run(factory, document_id, vectors, ScriptedVerifier(default="rejected"))

    link = run.link(children[0])
    assert run.verifier.calls == [[f"q{children[0]}"]]
    assert (link.status, link.verdict, link.parent_record_id) == ("not_confirmed", "rejected", parents[0])
    assert run.about(children[0]) == [("child_without_parent", "not_confirmed", 1)]
    assert [len(run.about(parent)) for parent in parents] == [1, 1]


def test_a_parent_function_left_without_children_is_flagged(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=2, children=2)
    vectors = _parents(2) | {
        "Функция отдела 0": exact_child({0: 0.95, 1: 0.2}),
        "Функция отдела 1": exact_child({0: 0.9, 1: 0.3}),
    }

    run = _run(factory, document_id, vectors)

    assert {run.link(child).parent_record_id for child in children} == {parents[0]}
    assert run.about(parents[0]) == []
    assert run.about(parents[1]) == [("parent_without_children", "no_accepted_child", 1)]
    finding = next(f for f in run.findings if f.record_id == parents[1])
    assert "требует проверки" in finding.message
    assert finding.group_id == run.groups[0].id


def test_a_missing_answer_is_an_error_and_not_an_anomaly(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=1, children=1)
    vectors = _parents(1) | {"Функция отдела 0": exact_child({0: 0.7})}

    run = _run(factory, document_id, vectors, ScriptedVerifier(default=None))

    link = run.link(children[0])
    assert len(run.verifier.calls) == RETRIES + 1
    assert (link.decision, link.status, link.verdict, link.attempts) == ("llm", "error", None, RETRIES + 1)
    assert link.error
    assert run.about(children[0]) == [("child_without_parent", "error", 0)]
    assert run.about(parents[0]) == [("parent_without_children", "pending", 0)]
    assert run.status == "needs_review"


def test_leaf_and_top_functions_are_not_anomalies_and_chains_span_three_levels(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        builder = DocumentBuilder(session)
        department = builder.entity("Департамент аудита")
        division = builder.entity("Отдел проверок", department, category="division")
        auditor = builder.entity("Аудитор отдела", division, category="position")
        task = builder.record(department, "Задача департамента", "task").id
        function = builder.record(division, "Функция отдела").id
        action = builder.record(auditor, "Действие аудитора", "duty").id
        builder.record(department, "Цель департамента", "goal")
        session.commit()
        document_id = builder.id
    # Both lower functions lean the same way, so the auditor's action is close to the division function.
    vectors = {
        "Задача департамента": basis(0),
        "Функция отдела": exact_child({0: 0.9}),
        "Действие аудитора": exact_child({0: 0.88}),
    }

    run = _run(factory, document_id, vectors)

    assert [(link.child_record_id, link.parent_record_id, link.status) for link in run.links] == [
        (function, task, "accepted"),
        (action, function, "accepted"),
    ]
    assert run.findings == []
    assert run.status == "done"
    assert [group.entity_id for group in run.groups] == [department.id, division.id]
    accepted = [(link.parent_record_id, link.child_record_id) for link in run.links if link.parent_record_id]
    assert build_chains(accepted) == [[task, function, action]]


def test_an_exact_tie_is_ambiguous_without_a_question(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=2, children=1)
    vectors = _parents(2) | {"Функция отдела 0": exact_child({0: 0.6, 1: 0.6})}

    run = _run(factory, document_id, vectors)

    link = run.link(children[0])
    assert (link.status, link.decision, link.parent_record_id) == ("ambiguous", "none", None)
    assert json.loads(link.tied_record_ids) == parents
    assert link.best_similarity == 0.6
    assert run.verifier.calls == []
    assert run.about(children[0]) == [("child_without_parent", "ambiguous", 0)]
    assert [run.about(parent) for parent in parents] == [[("parent_without_children", "pending", 0)]] * 2


def test_unknown_and_ambiguous_parents_need_clarification(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        builder = DocumentBuilder(session)
        department = builder.entity("Департамент аудита")
        division = builder.entity("Отдел проверок", department, category="division")
        orphan = builder.entity("Сектор методологии", status="unknown", category="group")
        unsure = builder.entity("Группа качества", status="ambiguous", candidates=[department], category="group")
        task = builder.record(department, "Задача департамента", "task").id
        builder.record(department, "Вторая задача департамента", "task")
        function = builder.record(division, "Функция отдела").id
        lost = builder.record(orphan, "Функция сектора").id
        unsure_function = builder.record(unsure, "Функция группы").id
        session.commit()
        document_id = builder.id
    vectors = {
        "Задача департамента": basis(0),
        "Вторая задача департамента": basis(1),
        "Функция отдела": exact_child({0: 0.9}),
    }

    run = _run(factory, document_id, vectors)

    assert [link.child_record_id for link in run.links] == [function]
    assert run.link(function).parent_record_id == task
    assert run.about(lost) == [("needs_clarification", "parent_unknown", 0)]
    assert run.about(unsure_function) == [("needs_clarification", "parent_ambiguous", 0)]
    assert json.loads(run.groups[0].uncertain_entity_ids) == [unsure.id]
    second = next(f for f in run.findings if f.kind == "parent_without_children")
    assert (second.reason, second.final) == ("group_incomplete", 0)
    assert all(finding.final == 0 for finding in run.findings)
    assert run.status == "needs_review"


def test_twenty_three_questions_go_in_batches_of_ten(factory: sessionmaker[Session]) -> None:
    document_id, parents, children = _two_levels(factory, parents=1, children=23)
    vectors = _parents(1) | {f"Функция отдела {n}": exact_child({0: 0.7}) for n in range(23)}

    run = _run(factory, document_id, vectors)

    assert [len(call) for call in run.verifier.calls] == [10, 10, 3]
    assert sorted(q for call in run.verifier.calls for q in call) == sorted(f"q{child}" for child in children)
    assert {(link.status, link.parent_record_id) for link in run.links} == {("accepted", parents[0])}


def test_the_stage_waits_for_stages_2_and_3(factory: sessionmaker[Session]) -> None:
    document_id, _parents_ids, _children = _two_levels(factory, parents=1, children=1)
    vectors = _parents(1) | {"Функция отдела 0": exact_child({0: 0.9})}
    assert _run(factory, document_id, vectors).links
    with factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        document.activities_status = "running"
        session.commit()

    run = _run(factory, document_id, vectors)

    assert run.status == "not_started"
    assert (run.links, run.findings, run.groups) == ([], [], [])
    assert run.embedder.calls == []
    assert run.verifier.calls == []


def test_a_rerun_replaces_the_previous_rows_and_reuses_cached_vectors(factory: sessionmaker[Session]) -> None:
    document_id, _parent_ids, children = _two_levels(factory, parents=1, children=1)
    vectors = _parents(1) | {"Функция отдела 0": exact_child({0: 0.7})}
    first = _run(factory, document_id, vectors, ScriptedVerifier(default="rejected"))

    second = _run(factory, document_id, vectors, ScriptedVerifier(default="confirmed"))

    assert (len(second.links), len(second.groups)) == (1, 1)
    assert first.link(children[0]).status == "not_confirmed"
    assert second.link(children[0]).status == "accepted"
    assert second.findings == []
    assert second.embedder.calls == []
    with factory() as session:
        assert len(session.scalars(select(EmbeddingCache)).all()) == 2


def test_records_without_entity_are_left_out(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        builder = DocumentBuilder(session)
        department = builder.entity("Департамент аудита")
        division = builder.entity("Отдел проверок", department, category="division")
        builder.record(department, "Задача департамента", "task")
        builder.record(division, "Функция отдела")
        loose = builder.record(None, "Функция без исполнителя").id
        session.commit()
        document_id = builder.id
    vectors = {"Задача департамента": basis(0), "Функция отдела": exact_child({0: 0.9})}

    run = _run(factory, document_id, vectors)

    assert loose not in {link.child_record_id for link in run.links}
    assert run.about(loose) == []
    assert "Функция без исполнителя" not in {text for call in run.embedder.calls for text in call}


def test_a_division_without_functions_is_missing_data(factory: sessionmaker[Session]) -> None:
    document_id, parents, _children = _two_levels(factory, parents=1, children=0)

    run = _run(factory, document_id, _parents(1))

    assert run.links == []
    assert run.about(parents[0]) == [("parent_without_children", "no_child_functions", 0)]
    assert run.embedder.calls == []


def test_fail_marks_the_stage_failed(factory: sessionmaker[Session]) -> None:
    document_id, _parents_ids, _children = _two_levels(factory, parents=1, children=1)
    with factory() as session:
        CascadeStage(ScriptedVerifier(), FakeEmbedder({}), retries=0).fail(session, document_id, "boom")
    with factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        assert document.cascade_status == "failed"
