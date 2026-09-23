import json
from typing import Any

import pytest
from entities_support import mention, relation, resolved, src

from la_rp_peace.entities.answers import BlockAnswer, ConsolidationAnswer
from la_rp_peace.entities.blocks import Block, BlockLine
from la_rp_peace.entities.checks import finish
from la_rp_peace.entities.consolidate import consolidate
from la_rp_peace.entities.extract import BlockMark, extract_block
from la_rp_peace.entities.prompt import DocumentCard
from la_rp_peace.entities.registry import Registry
from la_rp_peace.entities.verify import SourceVerifier, check_block_answer, check_consolidation
from la_rp_peace.enums import BlockStatus, EntitiesStatus, EntityIssueType, ParentStatus, ReviewStatus
from la_rp_peace.llm import ChatModelError, Message
from la_rp_peace.navigation import NodePlace

TEXTS = {
    1: "3.4. БВА состоит из следующих структурных подразделений:",
    2: "а. Департамент ИТ-аудита и анализа данных (ДИТААД).",
    3: "б. Департамент операционного аудита (ДОА).",
    4: "3.6. Директору ДИТААД подчиняются работники ДИТААД в составе следующих должностей:",
    5: "в. Аудитор.",
    6: "3.7. Директору ДОА подчиняются работники ДОА в составе следующих должностей:",
    7: "в. Аудитор.",
}
CARD = DocumentCard(1, "Положение о внутреннем аудите", "АО «Компания»", "положение")
BLOCK = Block(1, tuple(BlockLine(node, f"п. {node}", text, False) for node, text in TEXTS.items()))
PLACES = {node: NodePlace(f"п. {node}", f"Разд. 3 › п. {node}", {}) for node in TEXTS}


def _registry() -> Registry:
    return Registry(SourceVerifier(TEXTS))


def _answer(*mentions: dict[str, Any], relations: list[dict[str, Any]] | None = None) -> BlockAnswer:
    return BlockAnswer.model_validate(
        {"block_status": "found", "mentions": list(mentions), "relations": relations or []},
    )


def _ditaad(ref: str = "d") -> dict[str, Any]:
    return mention(
        ref,
        "Департамент ИТ-аудита и анализа данных",
        "департамент",
        [src(2, "Департамент ИТ-аудита и анализа данных (ДИТААД)", "name", "type")],
        aliases=["ДИТААД"],
    )


def _doa(ref: str = "o") -> dict[str, Any]:
    return mention(
        ref,
        "Департамент операционного аудита",
        "департамент",
        [src(3, "Департамент операционного аудита", "name", "type")],
    )


def _auditor(ref: str, parent: str, node: int = 5, intro: int = 4) -> dict[str, Any]:
    return mention(
        ref,
        "Аудитор",
        "должность",
        [src(node, "Аудитор", "name", "type")],
        resolved(parent, src(intro, "в составе следующих должностей", "parent")),
    )


class Replies:
    def __init__(self, *replies: dict[str, Any] | Exception) -> None:
        self.replies = list(replies)
        self.conversations: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        self.conversations.append(list(messages))
        reply = self.replies[min(len(self.conversations), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply, ensure_ascii=False)


# -- answer checks ------------------------------------------------------------------------


def test_invented_quote_is_fed_back_and_corrected() -> None:
    invented = {
        "block_status": "found",
        "mentions": [mention("d", "ДИТААД", "департамент", [src(2, "Дирекция ИТ", "name", "type")])],
    }
    model = Replies(invented, {"block_status": "found", "mentions": [_ditaad()]})
    registry = _registry()

    mark = extract_block(model, CARD, BLOCK, registry, retries=2)

    assert (mark.status, mark.attempts) == (BlockStatus.FOUND, 2)
    feedback = model.conversations[1][-1].content
    assert "цитата «Дирекция ИТ» не найдена" in feedback
    assert [entity.name for entity in registry.entities.values()] == ["Департамент ИТ-аудита и анализа данных"]


def test_node_of_another_document_is_rejected() -> None:
    answer = _answer(mention("d", "ДИТААД", "департамент", [src(999, "ДИТААД", "name", "type")]))

    errors = check_block_answer(answer, SourceVerifier(TEXTS), set())

    assert errors == ["d «ДИТААД»: узел 999 не относится к текущему документу"]


def test_attributes_need_their_own_support() -> None:
    answer = _answer(
        mention(
            "a",
            "Аудитор",
            "должность",
            [src(5, "Аудитор", "name")],
            position_type="специалист",
            roles=[{"role": "аудитор", "sources": [src(5, "Аудитор", "name")]}],
        ),
    )

    errors = check_block_answer(answer, SourceVerifier(TEXTS), set())

    assert any("«type» не подтверждён" in error for error in errors)
    assert any("«position_type» не подтверждён" in error for error in errors)
    assert any("нет источника роли (supports: role:аудитор)" in error for error in errors)


def test_parent_needs_a_parent_source_and_known_ref() -> None:
    no_source = _auditor("a", "d")
    no_source["parent"]["sources"] = []
    unknown_parent = _auditor("b", "E7")

    errors = check_block_answer(_answer(_ditaad(), no_source, unknown_parent), SourceVerifier(TEXTS), set())

    assert any("a «Аудитор»: нет источника, подтверждающего родителя" in error for error in errors)
    assert any("b «Аудитор»: родитель «E7» не найден" in error for error in errors)


def test_unknown_supports_value_and_registry_key_are_rejected() -> None:
    answer = _answer(mention("E4", "ДИТААД", "департамент", [src(2, "ДИТААД", "name", "type", "headcount")]))

    errors = check_block_answer(answer, SourceVerifier(TEXTS), {"E1"})

    assert any("объекта E4 нет в реестре" in error for error in errors)
    assert any("недопустимые значения supports ['headcount']" in error for error in errors)


def test_exhausted_retries_fail_the_block_with_a_blocking_issue() -> None:
    model = Replies({"block_status": "found"})
    registry = _registry()

    mark = extract_block(model, CARD, BLOCK, registry, retries=1)

    assert (mark.status, mark.attempts) == (BlockStatus.FAILED, 2)
    assert [(i.issue_type, i.is_blocking) for i in registry.issues] == [(EntityIssueType.BLOCK_FAILED, True)]


def test_request_error_is_failed_not_none() -> None:
    registry = _registry()

    mark = extract_block(Replies(ChatModelError("нет сети")), CARD, BLOCK, registry, retries=2)
    report = finish(registry, [BLOCK], [mark])

    assert mark.status is BlockStatus.FAILED
    assert mark.attempts == 1
    assert "нет сети" in (mark.message or "")
    assert report.status is EntitiesStatus.NEEDS_REVIEW


# -- registry -----------------------------------------------------------------------------


def test_equal_names_without_registry_key_stay_separate() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad()))
    registry.apply_block(_answer(_ditaad()))

    assert list(registry.entities) == ["E1", "E2"]


def test_registry_key_adds_sources_to_the_same_entity() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad()))
    again = mention("E1", "ДИТААД", "департамент", [src(4, "ДИТААД", "name", "type")])
    registry.apply_block(_answer(again))

    assert list(registry.entities) == ["E1"]
    assert {source.node_id for source in registry.entities["E1"].sources} == {2, 4}


def test_two_auditors_of_two_departments_are_two_entities() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad(), _doa(), _auditor("a1", "d"), _auditor("a2", "o", node=7, intro=6)))

    auditors = [entity for entity in registry.entities.values() if entity.name == "Аудитор"]

    assert [auditor.parent for auditor in auditors] == ["E1", "E2"]


def test_conflicting_parent_becomes_ambiguous_with_an_issue() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad(), _doa(), _auditor("a", "d")))
    registry.apply_block(_answer(_auditor("E3", "E2", node=7, intro=6)))

    auditor = registry.entities["E3"]
    report = finish(registry, [BLOCK], [BlockMark(1, BlockStatus.FOUND, None, 1)])

    assert (auditor.parent, auditor.parent_status, auditor.candidates) == (None, ParentStatus.AMBIGUOUS, ["E1", "E2"])
    assert [i.issue_type for i in registry.issues] == [EntityIssueType.AMBIGUOUS_PARENT]
    assert report.review["E3"] is ReviewStatus.NEEDS_REVIEW
    assert report.review["E1"] is ReviewStatus.CHECKED
    assert report.status is EntitiesStatus.DONE


def test_cycle_is_refused() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad(), _auditor("a", "d")))
    loop = _ditaad("E1")
    loop["parent"] = resolved("E2", src(4, "в составе следующих должностей", "parent"))
    registry.apply_block(_answer(loop))

    assert registry.entities["E1"].parent is None
    assert registry.entities["E2"].parent == "E1"
    assert [(i.issue_type, i.is_blocking) for i in registry.issues] == [(EntityIssueType.CYCLE, True)]


def test_root_without_parent_source_becomes_unknown() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad()))
    registry.entities["E1"].parent_status = ParentStatus.ROOT

    report = finish(registry, [BLOCK], [BlockMark(1, BlockStatus.FOUND, None, 1)])

    assert registry.entities["E1"].parent_status is ParentStatus.UNKNOWN
    assert [i.issue_type for i in registry.issues] == [EntityIssueType.UNSUPPORTED_ATTRIBUTE]
    assert report.review["E1"] is ReviewStatus.NEEDS_REVIEW


def test_unmarked_block_blocks_the_document() -> None:
    report = finish(_registry(), [BLOCK], [])

    assert report.status is EntitiesStatus.NEEDS_REVIEW


def test_relation_is_kept_apart_from_parent() -> None:
    registry = _registry()
    director = mention("dir", "Директор ДИТААД", "должность", [src(4, "Директору ДИТААД", "name", "type")])
    reports = relation("a", "dir", "reports_to", src(4, "Директору ДИТААД подчиняются", "relation"))
    registry.apply_block(_answer(_ditaad(), director, _auditor("a", "d"), relations=[reports]))

    assert registry.entities["E3"].parent == "E1"
    assert [(r.from_key, r.to_key, r.relation_type.value) for r in registry.relations] == [("E3", "E2", "reports_to")]


# -- consolidation ------------------------------------------------------------------------


def _split_names() -> Registry:
    registry = _registry()
    abbreviation = mention("s", "ДИТААД", "департамент", [src(4, "ДИТААД", "name", "type")])
    registry.apply_block(_answer(abbreviation, _auditor("a", "s")))
    registry.apply_block(_answer(_ditaad()))
    return registry


def test_consolidation_merges_abbreviation_and_full_name() -> None:
    registry = _split_names()
    merge = {"keep": "E3", "merge": "E1", "sources": [src(2, "анализа данных (ДИТААД)", "same_entity")]}
    model = Replies({"merges": [merge], "parent_updates": [], "unresolved": []})

    consolidate(model, CARD, registry, PLACES, TEXTS, retries=0)

    kept = registry.entities["E3"]
    assert list(registry.entities) == ["E2", "E3"]
    assert kept.aliases == ["ДИТААД"]
    assert {source.node_id for source in kept.sources} == {2, 4}
    assert any("same_entity" in source.supports for source in kept.sources)
    assert registry.entities["E2"].parent == "E3"
    review = model.conversations[0][1].content
    assert "E1: ДИТААД" in review
    assert "[node 4] Разд. 3 › п. 4 | 3.6. Директору ДИТААД" in review


def test_merge_without_same_entity_evidence_is_rejected() -> None:
    registry = _split_names()
    answer = ConsolidationAnswer.model_validate(
        {"merges": [{"keep": "E3", "merge": "E1", "sources": [src(2, "ДИТААД", "name")]}]},
    )

    errors = check_consolidation(answer, registry.verifier, set(registry.entities))

    assert errors == ["объединение E1→E3: нет источника, что это один объект (supports: same_entity)"]


def test_failed_consolidation_is_a_blocking_issue() -> None:
    registry = _split_names()

    consolidate(Replies({"merges": [{"keep": "E3", "merge": "E9", "sources": []}]}), CARD, registry, PLACES, TEXTS, 0)

    assert len(registry.entities) == 3
    assert [(i.issue_type, i.is_blocking) for i in registry.issues] == [(EntityIssueType.OTHER, True)]


def test_consolidation_settles_an_ambiguous_parent() -> None:
    registry = _registry()
    registry.apply_block(_answer(_ditaad(), _doa(), _auditor("a", "d")))
    registry.apply_block(_answer(_auditor("E3", "E2", node=7, intro=6)))
    update = {"entity": "E3", "parent": "E1", "status": "resolved", "sources": [src(4, "работники ДИТААД", "parent")]}

    consolidate(Replies({"parent_updates": [update]}), CARD, registry, PLACES, TEXTS, 0)

    assert (registry.entities["E3"].parent, registry.entities["E3"].parent_status) == ("E1", ParentStatus.RESOLVED)
    assert registry.issues == []


@pytest.mark.parametrize("status", ["found", "none"])
def test_block_status_must_match_the_content(status: str) -> None:
    mentions = [] if status == "found" else [_ditaad()]
    answer = BlockAnswer.model_validate({"block_status": status, "mentions": mentions})

    assert check_block_answer(answer, SourceVerifier(TEXTS), set())
