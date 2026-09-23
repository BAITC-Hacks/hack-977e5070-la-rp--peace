"""Human-readable locations of stored nodes: short anchor, section path, file location.

Example for ed. 9: anchor «п. 3.4 «а»», path «Разд. 3 «Структура и организация работы
внутреннего аудита» › п. 3.4 › подп. «а»», location ``{"page": 6}`` (PDF) or
``{"paragraph": 103}`` (DOCX). Clause numbers are printed in the documents, so path plus
quote finds the spot with Ctrl+F in Word or any PDF viewer.
"""

import bisect
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from la_rp_peace.enums import NodeType
from la_rp_peace.models import DocumentNode

PATH_SEPARATOR = " › "
_ROOT_ANCHOR = "вводная часть"
_LEADING_MARKER = re.compile(r"^\S+?[.)]?\s+")


@dataclass(frozen=True, slots=True)
class NodePlace:
    """Where a node is, for people."""

    anchor: str
    path: str
    location: dict[str, Any]


def _shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _section_title(node: DocumentNode) -> str:
    text = node.text
    if node.marker and text.startswith(node.marker):
        text = text[len(node.marker) :].lstrip(". ")
    return _shorten(text)


class _Describer:
    def __init__(self, nodes: Sequence[DocumentNode]) -> None:
        self._by_id = {node.id: node for node in nodes}
        self._children: dict[int | None, list[DocumentNode]] = {}
        for node in sorted(nodes, key=lambda item: item.position):
            self._children.setdefault(node.parent_id, []).append(node)
        self._labels: dict[int, str] = {}
        self._anchors: dict[int, str] = {}

    def _ordinal(self, node: DocumentNode, same_type: bool = True) -> int:
        siblings = self._children.get(node.parent_id, [])
        peers = [sibling for sibling in siblings if not same_type or sibling.node_type == node.node_type]
        return peers.index(node) + 1

    def label(self, node: DocumentNode) -> str:
        if node.id in self._labels:
            return self._labels[node.id]
        labels = {
            NodeType.SECTION: lambda: f"Разд. {node.marker} «{_section_title(node)}»",
            NodeType.CLAUSE: lambda: f"п. {node.marker}",
            NodeType.HEADING: lambda: f"«{_shorten(node.text)}»",
            NodeType.LIST: lambda: self._list_label(node),
            NodeType.LIST_ITEM: lambda: self._item_label(node),
            NodeType.TEXT: lambda: f"абз. {self._ordinal(node)}",
            NodeType.SERVICE: lambda: f"служебный блок «{_shorten(node.text, 40)}»",
            NodeType.TABLE: lambda: f"таблица {self._ordinal(node)}",
            NodeType.TABLE_ROW: lambda: f"стр. {self._ordinal(node)}",
            NodeType.TABLE_CELL: lambda: f"ячейка {self._ordinal(node)}",
        }
        self._labels[node.id] = labels[NodeType(node.node_type)]()
        return self._labels[node.id]

    def _list_label(self, node: DocumentNode) -> str:
        lists = [s for s in self._children.get(node.parent_id, []) if s.node_type == NodeType.LIST]
        return f"список {lists.index(node) + 1}" if len(lists) > 1 else ""

    def _item_label(self, node: DocumentNode) -> str:
        marker = node.marker or ""
        return f"подп. «{marker}»" if marker.isalpha() else f"подп. {self._ordinal(node)}"

    def ancestors(self, node: DocumentNode) -> list[DocumentNode]:
        chain = [node]
        while chain[-1].parent_id is not None:
            chain.append(self._by_id[chain[-1].parent_id])
        return list(reversed(chain))

    def path(self, node: DocumentNode) -> str:
        return PATH_SEPARATOR.join(label for item in self.ancestors(node) if (label := self.label(item)))

    def anchor(self, node: DocumentNode) -> str:
        if node.node_type == NodeType.SECTION:
            return f"разд. {node.marker}"
        if node.node_type == NodeType.CLAUSE:
            return f"п. {node.marker}"
        numbered = [item for item in self.ancestors(node)[:-1] if item.node_type in (NodeType.SECTION, NodeType.CLAUSE)]
        base = self.anchor(numbered[-1]) if numbered else _ROOT_ANCHOR
        label = self.label(node)
        if node.node_type == NodeType.LIST_ITEM and (node.marker or "").isalpha():
            return f"{base} «{node.marker}»"
        return f"{base}, {label}" if label else base


def _location(source_map: list[dict[str, Any]], starts: list[int], offset: int) -> dict[str, Any]:
    index = bisect.bisect_right(starts, offset) - 1
    if index >= 0 and offset < source_map[index]["end"]:
        location: dict[str, Any] = source_map[index]["location"]
        return location
    return {}


def describe(nodes: Sequence[DocumentNode], source_map: list[dict[str, Any]]) -> dict[int, NodePlace]:
    """Describe every node of one document.

    Args:
        nodes: All nodes of the document.
        source_map: The document's parsed ``source_map``.

    Returns:
        Place of each node by id.
    """
    describer = _Describer(nodes)
    starts = [span["start"] for span in source_map]
    return {
        node.id: NodePlace(
            describer.anchor(node), describer.path(node), _location(source_map, starts, node.source_start)
        )
        for node in nodes
    }
