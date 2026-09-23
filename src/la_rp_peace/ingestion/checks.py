"""Checks of a built tree against its source (methodology §8), producing parsing issues."""

from la_rp_peace.enums import IssueType, NodeType
from la_rp_peace.ingestion.extract.types import Extraction
from la_rp_peace.ingestion.numbering import Number, is_successor, parse_number
from la_rp_peace.ingestion.tree import IssueDraft, ParsedNode

_NUMBERED = (NodeType.SECTION, NodeType.CLAUSE)
_CONTENT = (NodeType.SECTION, NodeType.CLAUSE, NodeType.LIST_ITEM)


def _uncovered(extraction: Extraction, nodes: list[ParsedNode]) -> list[IssueDraft]:
    covered = [False] * len(extraction.original_text)
    for node in nodes:
        covered[node.start : node.end] = [True] * (node.end - node.start)
    issues: list[IssueDraft] = []
    for block in extraction.blocks:
        missing = "".join(
            char
            for offset, char in enumerate(block.text, start=block.start)
            if not covered[offset] and not char.isspace() and char != "\t"
        )
        if missing:
            issues.append(
                IssueDraft(IssueType.UNCOVERED_TEXT, f"Текст блока не вошёл в дерево: «{block.text[:80]}»", True),
            )
    return issues


def _numbering(nodes: list[ParsedNode]) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    last: Number | None = None
    sections: dict[str, int] = {}
    for index, node in enumerate(nodes):
        number = parse_number(node.marker) if node.marker and node.node_type in _NUMBERED else None
        if number is None:
            continue
        if not is_successor(number, last):
            previous = ".".join(map(str, last)) if last else "начала документа"
            message = f"После {previous} идёт {node.marker}"
            issues.append(IssueDraft(IssueType.NUMBERING_GAP, message, False, index))
        if node.node_type is NodeType.SECTION:
            if node.marker in sections:
                message = f"Раздел {node.marker} встречается повторно"
                issues.append(IssueDraft(IssueType.AMBIGUOUS_BOUNDARY, message, True, index))
            sections[node.marker or ""] = index
        last = number
    return issues


def _empty(nodes: list[ParsedNode]) -> list[IssueDraft]:
    issues = []
    for index, node in enumerate(nodes):
        body = node.text[len(node.marker) :] if node.marker and node.text.startswith(node.marker) else node.text
        if node.node_type in _CONTENT and not any(char.isalnum() for char in body):
            message = f"Пункт {node.marker} не содержит текста: «{node.text}»"
            issues.append(IssueDraft(IssueType.EMPTY_CONTENT, message, False, index))
    return issues


def _nesting(nodes: list[ParsedNode]) -> list[IssueDraft]:
    issues = []
    for index, node in enumerate(nodes):
        if node.range_end <= node.range_start:
            issues.append(
                IssueDraft(IssueType.AMBIGUOUS_BOUNDARY, "Узел без текста и без дочерних элементов", True, index)
            )
            continue
        if node.parent is None:
            continue
        parent = nodes[node.parent]
        if not parent.range_start <= node.range_start <= node.range_end <= parent.range_end:
            issues.append(
                IssueDraft(IssueType.AMBIGUOUS_PARENT, "Диапазон узла выходит за пределы родителя", True, index)
            )
    return issues


def check_tree(extraction: Extraction, nodes: list[ParsedNode], strategy: str) -> list[IssueDraft]:
    """Run all checks on a built tree.

    Args:
        extraction: The source the tree was built from.
        nodes: The tree, with ranges finished.
        strategy: The profile's strategy; numbering strategies must find numbered nodes.

    Returns:
        Issues in document order; blocking ones prevent the ``validated`` status.
    """
    issues = _uncovered(extraction, nodes) + _numbering(nodes) + _empty(nodes) + _nesting(nodes)
    if strategy in ("numbering", "mixed") and not any(node.node_type in _NUMBERED for node in nodes):
        issues.append(IssueDraft(IssueType.OTHER, "Профиль не выделил ни одного раздела или пункта", True))
    return issues
