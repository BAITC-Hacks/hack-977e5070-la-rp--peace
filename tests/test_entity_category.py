import json
from pathlib import Path
from typing import Any

import pytest
from entities_support import ScriptedModel, ed9_general, ed9_structure, mention, parsed_document, session_factory, src
from sqlalchemy import select

from la_rp_peace.entities.answers import BlockAnswer, ConsolidationAnswer
from la_rp_peace.entities.blocks import Block, BlockLine
from la_rp_peace.entities.checks import finish
from la_rp_peace.entities.conversation import parse_answer
from la_rp_peace.entities.extract import BlockMark
from la_rp_peace.entities.pipeline import EntityStage
from la_rp_peace.entities.registry import Registry
from la_rp_peace.entities.verify import SourceVerifier, check_block_answer, check_consolidation
from la_rp_peace.enums import BlockStatus, EntityCategory, EntityIssueType, ReviewStatus
from la_rp_peace.models import Entity

TEXTS = {
    1: "а. Департамент ИТ-аудита и анализа данных (ДИТААД).",
    2: "3.6. Директору ДИТААД подчиняются работники ДИТААД в составе следующих должностей:",
}
BLOCK = Block(1, tuple(BlockLine(node, f"п. {node}", text, False) for node, text in TEXTS.items()))
MARKS = [BlockMark(1, BlockStatus.FOUND, None, 1)]


def _answer(*mentions: dict[str, Any]) -> BlockAnswer:
    return BlockAnswer.model_validate({"block_status": "found", "mentions": list(mentions)})


def _ditaad(ref: str = "d", category: str = "department", *supports: str) -> dict[str, Any]:
    claims = supports or ("name", "type", "category")
    return mention(ref, "ДИТААД", "департамент", [src(1, "ДИТААД", *claims)], category=category)


def test_category_is_required_and_validated() -> None:
    missing = _ditaad()
    del missing["category"]
    wrong = _ditaad(category="section")

    _, missing_errors = parse_answer(json.dumps({"block_status": "found", "mentions": [missing]}), BlockAnswer)
    _, wrong_errors = parse_answer(json.dumps({"block_status": "found", "mentions": [wrong]}), BlockAnswer)

    assert any(error.startswith("mentions.0.category") for error in missing_errors)
    assert any(error.startswith("mentions.0.category") for error in wrong_errors)


@pytest.mark.parametrize(("category", "rejected"), [("department", True), ("unclear", False), ("other", False)])
def test_stated_category_needs_a_source(category: str, rejected: bool) -> None:
    answer = _answer(_ditaad("d", category, "name", "type"))

    errors = check_block_answer(answer, SourceVerifier(TEXTS), set())

    assert any("«category» не подтверждён" in error for error in errors) is rejected


def test_conflicting_category_keeps_the_first_with_an_issue() -> None:
    registry = Registry(SourceVerifier(TEXTS))
    registry.apply_block(_answer(_ditaad()))
    registry.apply_block(_answer(_ditaad("E1", "division")))

    assert registry.entities["E1"].category is EntityCategory.DEPARTMENT
    assert [(i.issue_type, i.is_blocking) for i in registry.issues] == [(EntityIssueType.OTHER, False)]
    assert "противоречит" in registry.issues[0].message


def test_unclear_category_is_settled_by_a_later_mention() -> None:
    registry = Registry(SourceVerifier(TEXTS))
    registry.apply_block(_answer(_ditaad(category="unclear")))
    registry.apply_block(_answer(_ditaad("E1", "department")))

    assert registry.entities["E1"].category is EntityCategory.DEPARTMENT
    assert registry.issues == []


def test_unclear_category_needs_review() -> None:
    registry = Registry(SourceVerifier(TEXTS))
    registry.apply_block(_answer(_ditaad(category="unclear")))

    report = finish(registry, [BLOCK], MARKS)

    assert report.review["E1"] is ReviewStatus.NEEDS_REVIEW
    assert any("категория объекта не установлена" in issue.message for issue in registry.issues)


def test_merge_across_categories_is_refused() -> None:
    registry = Registry(SourceVerifier(TEXTS))
    director = mention("p", "Директор ДИТААД", "должность", [src(2, "Директору ДИТААД", "name", "type", "category")])
    registry.apply_block(_answer(_ditaad(), director))
    merge = {"keep": "E1", "merge": "E2", "sources": [src(1, "ДИТААД", "same_entity")]}
    answer = ConsolidationAnswer.model_validate({"merges": [merge]})
    categories = {key: entity.category for key, entity in registry.entities.items()}

    errors = check_consolidation(answer, registry.verifier, set(registry.entities), categories)
    registry.apply_consolidation(answer)

    assert errors == ["объединение E2→E1: разные категории position и department"]
    assert list(registry.entities) == ["E1", "E2"]
    assert [i.issue_type for i in registry.issues] == [EntityIssueType.AMBIGUOUS_MERGE]


def test_control_categories_of_edition_9(tmp_path: Path) -> None:
    factory = session_factory(tmp_path)
    document_id = parsed_document(factory, 9)
    with factory() as session:
        EntityStage(ScriptedModel([ed9_general, ed9_structure]), 12_000, 1).run(session, document_id)
        categories = {row.name: row.category for row in session.scalars(select(Entity))}

    assert categories == {
        "Блок внутреннего аудита": "block",
        "Главный аудитор": "position",
        "Совет директоров": "governing_body",
        "работники БВА": "collective",
        "Департамент ИТ-аудита и анализа данных": "department",
        "Департамент операционного аудита": "department",
        "Директор ДИТААД": "position",
        "Директор ДОА": "position",
        "Аудитор": "position",
    }
