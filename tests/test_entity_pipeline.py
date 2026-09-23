import json
from pathlib import Path

import pytest
from entities_support import (
    ScriptedModel,
    ed8_structure,
    ed9_general,
    ed9_structure,
    parsed_document,
    session_factory,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.entities.pipeline import EntityStage
from la_rp_peace.entities.prompt import BLOCK_SYSTEM_PROMPT
from la_rp_peace.ingestion.pipeline import ParsingQueue
from la_rp_peace.llm import ChatModelError, Message
from la_rp_peace.models import (
    Document,
    DocumentNode,
    Entity,
    EntityBlock,
    EntityIssue,
    EntityRelation,
    EntitySource,
)


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    return session_factory(tmp_path)


def _run(factory: sessionmaker[Session], edition: int, model: ScriptedModel) -> int:
    document_id = parsed_document(factory, edition)
    with factory() as session:
        EntityStage(model, max_chars=12_000, retries=2).run(session, document_id)
    return document_id


def _by_name(session: Session, document_id: int, name: str) -> list[Entity]:
    query = select(Entity).where(Entity.document_id == document_id, Entity.name == name).order_by(Entity.id)
    return list(session.scalars(query))


def _sources(session: Session, entity: Entity) -> list[EntitySource]:
    return list(session.scalars(select(EntitySource).where(EntitySource.entity_id == entity.id)))


def _node_text(session: Session, node_id: int) -> str:
    node = session.get(DocumentNode, node_id)
    assert node is not None
    return node.text


def test_ed9_departments_and_their_auditors(factory: sessionmaker[Session]) -> None:
    model = ScriptedModel([ed9_general, ed9_structure])
    document_id = _run(factory, 9, model)

    with factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        assert document.entities_status == "done"
        bva = _by_name(session, document_id, "Блок внутреннего аудита")[0]
        ditaad = _by_name(session, document_id, "Департамент ИТ-аудита и анализа данных")[0]
        doa = _by_name(session, document_id, "Департамент операционного аудита")[0]
        auditors = _by_name(session, document_id, "Аудитор")

        assert json.loads(ditaad.aliases) == ["ДИТААД"]
        assert (ditaad.parent_id, doa.parent_id) == (bva.id, bva.id)
        parent_quote = next(s for s in _sources(session, ditaad) if "parent" in json.loads(s.supports))
        assert _node_text(session, parent_quote.node_id).startswith("3.4. БВА состоит")

        assert [auditor.parent_id for auditor in auditors] == [ditaad.id, doa.id]
        for auditor, clause in zip(auditors, ("3.6.", "3.7."), strict=True):
            evidence = {_node_text(session, s.node_id)[:4]: s for s in _sources(session, auditor)}
            assert clause in evidence
            assert json.loads(evidence[clause].supports) == ["parent"]
            assert auditor.review_status == "checked"

        bva_nodes = {_node_text(session, s.node_id)[:4] for s in _sources(session, bva)}
        assert {"1.1.", "3.4."} <= bva_nodes
        assert bva.parent_status == "unknown"


def test_ed9_relations_and_block_marks(factory: sessionmaker[Session]) -> None:
    model = ScriptedModel([ed9_general, ed9_structure])
    document_id = _run(factory, 9, model)

    with factory() as session:
        auditor = _by_name(session, document_id, "Аудитор")[0]
        director = _by_name(session, document_id, "Директор ДИТААД")[0]
        relations = list(session.scalars(select(EntityRelation).where(EntityRelation.document_id == document_id)))
        marks = list(session.scalars(select(EntityBlock).where(EntityBlock.document_id == document_id)))

        assert (auditor.id, director.id, "reports_to") in {
            (r.from_entity_id, r.to_entity_id, r.relation_type) for r in relations
        }
        assert all(
            session.scalars(select(EntitySource).where(EntitySource.relation_id == r.id)).first() for r in relations
        )
        assert sorted(mark.status for mark in marks).count("found") == 2
        assert {mark.status for mark in marks} == {"found", "none"}

    block_calls = [c for c in model.stage2_conversations() if c[0].content == BLOCK_SYSTEM_PROMPT]
    assert len(block_calls) == len(marks)
    structure_call = next(c for c in block_calls if "3.4. БВА состоит" in c[1].content)
    assert "E1: Блок внутреннего аудита (также: БВА)" in structure_call[1].content


def test_ed8_project_director_is_one_position(factory: sessionmaker[Session]) -> None:
    document_id = _run(factory, 8, ScriptedModel([ed8_structure]))

    with factory() as session:
        [project_director] = _by_name(session, document_id, "Директор проектов ДККМ")
        [dkkm] = _by_name(session, document_id, "Департамент контроля качества аудита и методологии")
        [functional_head] = _by_name(session, document_id, "Директор направления внутреннего аудита")
        [link] = session.scalars(select(EntityRelation).where(EntityRelation.document_id == document_id))

        assert (project_director.parent_id, project_director.parent_status) == (dkkm.id, "resolved")
        name_nodes = [s.node_id for s in _sources(session, project_director) if "name" in json.loads(s.supports)]
        assert len(set(name_nodes)) == 2
        assert (link.from_entity_id, link.to_entity_id) == (project_director.id, functional_head.id)
        assert (link.relation_type, link.conditions) == (
            "functional_subordination",
            "функционально в рамках Плана работ БВА",
        )
        assert functional_head.parent_status == "unknown"


def test_failed_request_marks_block_failed_not_none(factory: sessionmaker[Session]) -> None:
    class Broken(ScriptedModel):
        def complete(self, messages: list[Message]) -> str:
            if messages[0].content == BLOCK_SYSTEM_PROMPT and "3.4. БВА состоит" in messages[1].content:
                raise ChatModelError("timeout")
            return super().complete(messages)

    document_id = _run(factory, 9, Broken([ed9_general, ed9_structure]))

    with factory() as session:
        document = session.get(Document, document_id)
        failed = list(session.scalars(select(EntityBlock).where(EntityBlock.status == "failed")))
        issues = list(session.scalars(select(EntityIssue).where(EntityIssue.issue_type == "block_failed")))

        assert document is not None
        assert document.entities_status == "needs_review"
        assert len(failed) == 1
        assert _node_text(session, failed[0].node_id).startswith("3. Структура")
        assert [issue.is_blocking for issue in issues] == [1]
        assert "timeout" in issues[0].message


def test_rerun_replaces_previous_results(factory: sessionmaker[Session]) -> None:
    model = ScriptedModel([ed9_general, ed9_structure])
    document_id = _run(factory, 9, model)
    with factory() as session:
        EntityStage(model, max_chars=12_000, retries=2).run(session, document_id)
        count = len(list(session.scalars(select(Entity).where(Entity.document_id == document_id))))
        marks = len(list(session.scalars(select(EntityBlock).where(EntityBlock.document_id == document_id))))

    assert count == 9
    assert marks == len([c for c in model.stage2_conversations() if c[0].content == BLOCK_SYSTEM_PROMPT]) // 2


def test_crashing_stage_is_marked_failed_through_the_queue(factory: sessionmaker[Session]) -> None:
    class Crashing(ScriptedModel):
        def complete(self, messages: list[Message]) -> str:
            if messages[0].content == BLOCK_SYSTEM_PROMPT:
                raise RuntimeError("boom")
            return super().complete(messages)

    model = Crashing([])
    path_id = parsed_document(factory, 9)
    queue = ParsingQueue(factory, model, 150_000, 0, 1, stages=[EntityStage(model, 12_000, 0)])
    try:
        queue.submit_from(path_id, "entities").result(timeout=60)
    finally:
        queue.shutdown()

    with factory() as session:
        document = session.get(Document, path_id)
        issues = list(session.scalars(select(EntityIssue).where(EntityIssue.document_id == path_id)))
        assert document is not None
        assert document.entities_status == "failed"
        assert [(issue.issue_type, issue.is_blocking) for issue in issues] == [("other", 1)]
        assert "boom" in issues[0].message
