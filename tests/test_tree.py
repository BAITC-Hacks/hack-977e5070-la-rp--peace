from functools import cache

import pytest
from conftest import edition_path, load_fixture

from la_rp_peace.enums import DocFormat, IssueType, NodeType
from la_rp_peace.ingestion.checks import check_tree
from la_rp_peace.ingestion.extract import detect_format, extract
from la_rp_peace.ingestion.extract.types import Extraction, TextBuilder
from la_rp_peace.ingestion.profile import CompiledProfile, compile_profile
from la_rp_peace.ingestion.tree import ParsedNode, build_tree

type Signature = tuple[str, str | None, str, object]


@cache
def _profile() -> CompiledProfile:
    return compile_profile(load_fixture("parsing_profile.json"))


@cache
def _parsed(edition: int, suffix: str) -> tuple[Extraction, list[ParsedNode]]:
    path = edition_path(edition, suffix)
    extraction = extract(detect_format(path.name, path.read_bytes()), path.read_bytes())
    return extraction, build_tree(extraction, _profile())


def _nodes(edition: int, suffix: str = ".docx") -> list[ParsedNode]:
    return _parsed(edition, suffix)[1]


def _signature(nodes: list[ParsedNode]) -> list[Signature]:
    def key(index: int) -> Signature:
        node = nodes[index]
        parent = key(node.parent) if node.parent is not None else None
        return (node.node_type.value, node.marker, node.text, parent)

    return [
        key(index)
        for index, node in enumerate(nodes)
        if not (node.node_type is NodeType.SERVICE and node.text.isdigit())
    ]


def _find(nodes: list[ParsedNode], marker: str) -> int:
    return next(
        index for index, node in enumerate(nodes) if node.marker == marker and node.node_type is not NodeType.LIST_ITEM
    )


def _children(nodes: list[ParsedNode], parent: int) -> list[ParsedNode]:
    return [node for node in nodes if node.parent == parent]


@pytest.mark.parametrize("edition", [8, 9])
def test_pdf_builds_the_same_tree_as_docx(edition: int) -> None:
    assert _signature(_nodes(edition, ".pdf")) == _signature(_nodes(edition, ".docx"))


@pytest.mark.parametrize(("edition", "suffix"), [(8, ".docx"), (9, ".docx"), (9, ".pdf")])
def test_node_text_is_a_slice_of_original_text_and_ranges_nest(edition: int, suffix: str) -> None:
    extraction, nodes = _parsed(edition, suffix)

    for node in nodes:
        assert extraction.original_text[node.start : node.end] == node.text
        assert node.range_start < node.range_end
        if node.parent is not None:
            parent = nodes[node.parent]
            assert parent.range_start <= node.range_start <= node.range_end <= parent.range_end


def test_glued_clauses_are_separate_nodes() -> None:
    nodes = _nodes(9)
    section_three = _find(nodes, "3")

    numbers = [node.marker for node in _children(nodes, section_three) if node.node_type is NodeType.CLAUSE]

    assert numbers[-3:] == ["3.10", "3.11", "3.12"]
    assert nodes[_find(nodes, "3.10")].text.startswith("3.10.Рабочие места")


def test_glued_heading_becomes_a_section() -> None:
    nodes = _nodes(8)

    section = nodes[_find(nodes, "10")]

    assert (section.node_type, section.text, section.parent) == (NodeType.SECTION, "10.Контроль качества", None)


def test_clause_9_3_has_two_separate_lists() -> None:
    nodes = _nodes(8)
    clause = _find(nodes, "9.3")

    lists = [index for index, node in enumerate(nodes) if node.parent == clause and node.node_type is NodeType.LIST]
    markers = [[item.marker for item in _children(nodes, index)] for index in lists]

    assert markers == [["а", "б", "в", "г"], ["а", "б", "в"]]


def test_new_departments_are_items_of_3_4() -> None:
    nodes = _nodes(9)
    (list_index,) = [
        i for i, node in enumerate(nodes) if node.parent == _find(nodes, "3.4") and node.node_type is NodeType.LIST
    ]

    items = [node.text for node in _children(nodes, list_index)]

    assert items[:2] == [
        "а. Департамент ИТ-аудита и анализа данных (ДИТААД).",
        "б. Департамент операционного аудита (ДОА).",
    ]


def test_table_of_contents_and_front_matter_are_service_blocks() -> None:
    nodes = _nodes(8)

    roots = [node for node in nodes if node.parent is None and node.node_type is NodeType.SERVICE]
    toc = next(index for index, node in enumerate(nodes) if node.text == "Оглавление")
    sections = [node.marker for node in nodes if node.node_type is NodeType.SECTION]

    assert [node.text for node in roots[:3]] == ["УТВЕРЖДЕНО", "Советом директоров", "АО «Компания»"]
    assert len(_children(nodes, toc)) == 14
    assert sections == [str(number) for number in range(1, 15)]


def test_unnumbered_headings_stay_in_their_section() -> None:
    nodes = _nodes(8)

    heading = next(node for node in nodes if node.text == "Главный аудитор:")

    assert heading.node_type is NodeType.HEADING
    assert heading.parent is not None
    assert nodes[heading.parent].marker == "5"


def test_empty_clause_is_reported_without_blocking() -> None:
    extraction, nodes = _parsed(8, ".docx")

    issues = check_tree(extraction, nodes, "numbering")

    assert [(issue.issue_type, issue.is_blocking) for issue in issues] == [(IssueType.EMPTY_CONTENT, False)]
    assert issues[0].node is not None
    assert nodes[issues[0].node].text == "5.5.3. ;"


def _synthetic(*texts: str) -> Extraction:
    builder = TextBuilder()
    for index, text in enumerate(texts):
        builder.add(text, {"paragraph": index})
    return Extraction(DocFormat.DOCX, builder.text(), builder.blocks, builder.source_map)


def test_references_and_dates_do_not_start_clauses() -> None:
    extraction = _synthetic(
        "1. Общие положения",
        "1.1. Текст в соответствии с п.11 Положения. 11.Оценка по п. 3 от 25.06.2021 года.",
    )

    nodes = build_tree(extraction, _profile())

    assert [node.marker for node in nodes] == ["1", "1.1"]


def test_numbering_gap_is_reported() -> None:
    extraction = _synthetic("1. Общие положения", "1.1. Первый.", "1.3. Третий.")
    nodes = build_tree(extraction, _profile())

    issues = check_tree(extraction, nodes, "numbering")

    assert [(issue.issue_type, issue.message) for issue in issues] == [(IssueType.NUMBERING_GAP, "После 1.1 идёт 1.3")]


def test_profile_that_finds_no_clauses_is_blocking() -> None:
    extraction = _synthetic("Просто текст без нумерации.")
    nodes = build_tree(extraction, _profile())

    issues = check_tree(extraction, nodes, "numbering")

    assert any(issue.is_blocking and issue.issue_type is IssueType.OTHER for issue in issues)
