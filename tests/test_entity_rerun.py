import json
from pathlib import Path

import pytest
from entities_support import (
    Answer,
    ScriptedModel,
    View,
    ed9_general,
    ed9_structure,
    parsed_document,
    session_factory,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.entities.pipeline import EntityStage
from la_rp_peace.entities.prompt import BLOCK_SYSTEM_PROMPT
from la_rp_peace.llm import ChatModelError, Message
from la_rp_peace.models import Document, DocumentNode, Entity, EntityBlock, EntityIssue, EntityRelation, EntitySource

STRUCTURE = "3.4. БВА состоит"
INTRO_36 = "3.6. Директору ДИТААД"


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    return session_factory(tmp_path)


def _stage(session: Session, document_id: int, model: ScriptedModel) -> None:
    EntityStage(model, max_chars=12_000, retries=1).run(session, document_id)


def _snapshot(session: Session, document_id: int) -> dict[tuple[str, int | None], int]:
    """Entity id by (name, parent id); names repeat, so the parent is part of the key."""
    rows = list(session.scalars(select(Entity).where(Entity.document_id == document_id)))
    return {(row.name, row.parent_id): row.id for row in rows}


def _relations(session: Session, document_id: int) -> set[tuple[int, int, int, str]]:
    rows = session.scalars(select(EntityRelation).where(EntityRelation.document_id == document_id))
    return {(row.id, row.from_entity_id, row.to_entity_id, row.relation_type) for row in rows}


def _entity(session: Session, document_id: int, name: str) -> Entity:
    return session.scalars(select(Entity).where(Entity.document_id == document_id, Entity.name == name)).one()


class FailingStructure(ScriptedModel):
    """Answers like the scripted model, but the request for the structure block fails."""

    def complete(self, messages: list[Message]) -> str:
        if messages[0].content == BLOCK_SYSTEM_PROMPT and STRUCTURE in messages[1].content:
            raise ChatModelError("timeout")
        return super().complete(messages)


def _without_doa(view: View) -> Answer | None:
    """The structure block answered again, without ДОА and its positions and without mentioning БВА."""
    answer = ed9_structure(view)
    if answer is None:
        return None
    dropped = {"ДОА", "d_ДОА", "a_ДОА", view.key("Блок внутреннего аудита")}
    answer["mentions"] = [m for m in answer["mentions"] if m["ref"] not in dropped]
    answer["relations"] = [r for r in answer["relations"] if not {r["from"], r["to"]} & dropped]
    return answer


def test_identical_rerun_keeps_ids_and_adds_nothing(factory: sessionmaker[Session]) -> None:
    model = ScriptedModel([ed9_general, ed9_structure])
    document_id = parsed_document(factory, 9)
    with factory() as session:
        _stage(session, document_id, model)
        entities, relations = _snapshot(session, document_id), _relations(session, document_id)
        sources = len(list(session.scalars(select(EntitySource).where(EntitySource.document_id == document_id))))
        _stage(session, document_id, model)

        assert _snapshot(session, document_id) == entities
        assert _relations(session, document_id) == relations
        again = list(session.scalars(select(EntitySource).where(EntitySource.document_id == document_id)))
        assert len(again) == sources
        assert all(source.block_node_id is not None for source in again)


def test_changed_block_replaces_only_its_contribution(factory: sessionmaker[Session]) -> None:
    document_id = parsed_document(factory, 9)
    with factory() as session:
        _stage(session, document_id, ScriptedModel([ed9_general, ed9_structure]))
        before = _snapshot(session, document_id)
        bva = _entity(session, document_id, "Блок внутреннего аудита")
        _stage(session, document_id, ScriptedModel([ed9_general, _without_doa]))
        after = _snapshot(session, document_id)
        bva_nodes = {
            session.get(DocumentNode, source.node_id).text[:4]  # type: ignore[union-attr]
            for source in session.scalars(select(EntitySource).where(EntitySource.entity_id == bva.id))
        }

        gone = {key for key in before if key not in after}
        assert {name for name, _ in gone} == {"Департамент операционного аудита", "Директор ДОА", "Аудитор"}
        assert all(after[key] == before[key] for key in after)
        assert _entity(session, document_id, "Блок внутреннего аудита").id == bva.id
        assert bva_nodes == {"1.1."}


def test_failed_block_keeps_its_previous_result(factory: sessionmaker[Session]) -> None:
    document_id = parsed_document(factory, 9)
    with factory() as session:
        _stage(session, document_id, ScriptedModel([ed9_general, ed9_structure]))
        before, relations = _snapshot(session, document_id), _relations(session, document_id)
        _stage(session, document_id, FailingStructure([ed9_general, ed9_structure]))
        document = session.get(Document, document_id)
        [failed] = session.scalars(select(EntityBlock).where(EntityBlock.status == "failed"))
        issues = [issue.issue_type for issue in session.scalars(select(EntityIssue))]

        assert _snapshot(session, document_id) == before
        assert _relations(session, document_id) == relations
        assert "сохранён прежний результат блока" in (failed.message or "")
        assert issues == ["block_failed"]
        assert document is not None
        assert document.entities_status == "needs_review"


def test_stale_source_is_dropped_with_an_issue(factory: sessionmaker[Session]) -> None:
    document_id = parsed_document(factory, 9)
    with factory() as session:
        _stage(session, document_id, ScriptedModel([ed9_general, ed9_structure]))
        intro = session.scalars(select(DocumentNode).where(DocumentNode.text.startswith(INTRO_36))).one()
        session.execute(update(DocumentNode).where(DocumentNode.id == intro.id).values(text=INTRO_36 + " (изменено)."))
        session.commit()
        _stage(session, document_id, FailingStructure([ed9_general, ed9_structure]))
        auditors = list(session.scalars(select(Entity).where(Entity.name == "Аудитор").order_by(Entity.id)))
        quotes = [s.quote for s in session.scalars(select(EntitySource).where(EntitySource.node_id == intro.id))]
        messages = [issue.message for issue in session.scalars(select(EntityIssue))]

        assert quotes == []
        assert any("Прежний источник снят" in message and str(intro.id) in message for message in messages)
        assert [auditor.parent_status for auditor in auditors] == ["unknown", "resolved"]
        assert json.loads(auditors[1].aliases) == []
