"""Build a document tree by applying a compiled AI parsing profile (methodology §3–5).

Blocks are split where the profile's inline patterns find glued markers (decimal markers
only when they continue the numbering, so «п. 3» inside a sentence stays text), then each
piece becomes a node:

- a ``clause`` pattern match → ``section`` (level 1) or ``clause``; decimal markers find
  their parent by prefix (5.3.1 → 5.3), fixed-level markers by level;
- a ``list_item`` match → an item of a ``list`` node under the current container; a new list
  starts when the lettering restarts, so the two «а…» lists of 9.3 stay separate;
- a block styled as a heading → an unnumbered ``heading`` under the current section;
- table rows → ``table`` / ``table_row`` / ``table_cell``;
- service rules → ``service`` nodes (approval stamp and title before the first clause,
  table of contents, page numbers);
- anything else → ``text`` under the current container.

Every node's ``text`` is its own slice of ``original_text``; ranges are widened afterwards to
cover children, as the methodology requires.
"""

from dataclasses import dataclass, field
from itertools import pairwise

import regex

from la_rp_peace.enums import IssueType, NodeType
from la_rp_peace.ingestion.extract.types import Extraction, TextBlock
from la_rp_peace.ingestion.numbering import Number, is_successor, parse_number
from la_rp_peace.ingestion.profile import MARKER_GROUP, CompiledPattern, CompiledProfile, PatternRule

_LIST_STARTS = frozenset({"а", "a", "1", "i", "I", "А", "A"})
_UNSET = -1


class ProfileRuntimeError(ValueError):
    """Applying the profile failed (e.g. a regex timed out on real text)."""


@dataclass(slots=True)
class ParsedNode:
    """A node before it is stored; indices refer to the node list.

    ``start``/``end`` delimit the node's own text; ``range_start``/``range_end`` also cover
    its children and are what the methodology stores as ``source_start``/``source_end``.
    """

    node_type: NodeType
    marker: str | None
    text: str
    start: int
    end: int
    parent: int | None
    range_start: int = _UNSET
    range_end: int = _UNSET
    position: int = 0


@dataclass(frozen=True, slots=True)
class IssueDraft:
    """A parsing issue before it is stored; ``node`` is an index into the node list."""

    issue_type: IssueType
    message: str
    is_blocking: bool
    node: int | None = None


@dataclass(frozen=True, slots=True)
class _Piece:
    start: int
    end: int
    text: str
    inline: tuple[PatternRule, str] | None = None


@dataclass(slots=True)
class _OpenList:
    container: int | None
    node: int
    last_marker: str


@dataclass(slots=True)
class _State:
    by_number: dict[Number, int] = field(default_factory=dict)
    levels: list[tuple[int, int]] = field(default_factory=list)
    last_number: Number | None = None
    container: int | None = None
    section: int | None = None
    open_list: _OpenList | None = None
    toc: int | None = None
    table: tuple[object, int] | None = None
    seen_structure: bool = False


def _next_letter(previous: str, marker: str) -> bool:
    return len(previous) == 1 and len(marker) == 1 and ord(marker) == ord(previous) + 1


class _TreeEngine:
    def __init__(self, extraction: Extraction, profile: CompiledProfile) -> None:
        self._extraction = extraction
        self._profile = profile
        self.nodes: list[ParsedNode] = []
        self._state = _State()

    # -- node bookkeeping ------------------------------------------------------------

    def _add(self, node_type: NodeType, start: int, end: int, parent: int | None, marker: str | None = None) -> int:
        text = self._extraction.original_text[start:end]
        self.nodes.append(ParsedNode(node_type, marker, text, start, end, parent))
        return len(self.nodes) - 1

    def _reset_context(self) -> None:
        self._state.container = None
        self._state.section = None
        self._state.open_list = None
        self._state.levels = []

    # -- blocks ----------------------------------------------------------------------

    def add_block(self, block: TextBlock) -> None:
        if self._service_block(block):
            return
        if block.style == "table":
            self._table_row(block)
            return
        self._state.table = None
        for piece in self._pieces(block):
            self._piece(piece, block)

    def _service_block(self, block: TextBlock) -> bool:
        state, profile, text = self._state, self._profile, block.text
        if state.toc is not None:
            if any(rule.continues(text) for rule in profile.service("toc")):
                self._add(NodeType.SERVICE, block.start, block.end, state.toc)
                return True
            state.toc = None
        if any(rule.starts(text) for rule in profile.service("toc")):
            state.toc = self._add(NodeType.SERVICE, block.start, block.end, None)
            self._reset_context()
            return True
        if any(rule.starts(text) for rule in profile.service("page_number")):
            self._add(NodeType.SERVICE, block.start, block.end, state.container)
            return True
        if any(rule.starts(text) for rule in profile.service("other")):
            self._add(NodeType.SERVICE, block.start, block.end, None)
            self._reset_context()
            return True
        if not state.seen_structure and profile.service("front_matter") and not self._opens_clause(text):
            self._add(NodeType.SERVICE, block.start, block.end, None)
            return True
        return False

    def _opens_clause(self, text: str) -> bool:
        return any(p.rule.node_type == "clause" and p.match_start(text) for p in self._profile.block_patterns)

    def _table_row(self, block: TextBlock) -> None:
        state = self._state
        key = block.location.get("sheet", block.location.get("paragraph"))
        if state.table is None or state.table[0] != key:
            state.open_list = None
            state.table = (key, self._add(NodeType.TABLE, block.start, block.start, state.container))
        row = self._add(NodeType.TABLE_ROW, block.start, block.start, state.table[1])
        for cell in block.cells:
            self._add(NodeType.TABLE_CELL, cell.start, cell.end, row)

    # -- splitting glued markers -----------------------------------------------------

    def _block_start_number(self, text: str) -> Number | None:
        for pattern in self._profile.block_patterns:
            match = pattern.match_start(text)
            if match is not None and pattern.rule.hierarchy == "marker_depth":
                return parse_number(match.group(MARKER_GROUP).strip().rstrip("."))
        return None

    @staticmethod
    def _accepts_inline(pattern: CompiledPattern, marker: str, running: Number | None) -> tuple[bool, Number | None]:
        """Tell whether an inline marker starts a new node, and the numbering after it."""
        if pattern.rule.hierarchy != "marker_depth":
            return True, running
        number = parse_number(marker.strip().rstrip("."))
        if number is None or not is_successor(number, running):
            return False, running
        return True, number

    def _cuts(self, block: TextBlock) -> list[tuple[int, tuple[PatternRule, str]]]:
        found: list[tuple[int, CompiledPattern, regex.Match[str]]] = [
            (match.start(MARKER_GROUP), pattern, match)
            for pattern in self._profile.inline_patterns
            for match in pattern.find_inline(block.text)
        ]
        running = self._block_start_number(block.text) or self._state.last_number
        cuts: list[tuple[int, tuple[PatternRule, str]]] = []
        for position, pattern, match in sorted(found, key=lambda item: item[0]):
            if position == 0:
                continue
            marker = match.group(MARKER_GROUP)
            accepted, running = self._accepts_inline(pattern, marker, running)
            if accepted:
                cuts.append((position, (pattern.rule, marker)))
        return cuts

    def _pieces(self, block: TextBlock) -> list[_Piece]:
        cuts = self._cuts(block)
        bounds = [0, *(position for position, _ in cuts), len(block.text)]
        inline = [None, *(hit for _, hit in cuts)]
        pieces: list[_Piece] = []
        for (left, right), hit in zip(pairwise(bounds), inline, strict=True):
            raw = block.text[left:right]
            stripped = raw.strip()
            if stripped:
                offset = block.start + left + (len(raw) - len(raw.lstrip()))
                pieces.append(_Piece(offset, offset + len(stripped), stripped, hit))
        return pieces

    # -- pieces ----------------------------------------------------------------------

    def _match(self, piece: _Piece) -> tuple[PatternRule, str] | None:
        for pattern in self._profile.block_patterns:
            match = pattern.match_start(piece.text)
            if match is not None:
                return pattern.rule, match.group(MARKER_GROUP)
        return piece.inline

    def _piece(self, piece: _Piece, block: TextBlock) -> None:
        hit = self._match(piece)
        if hit is not None and hit[0].node_type == "clause":
            self._structural(piece, hit[0], hit[1])
        elif hit is not None:
            self._list_item(piece, hit[1].strip())
        elif (block.style or "").casefold() in self._profile.heading_styles:
            self._heading(piece)
        else:
            self._state.open_list = None
            self._add(NodeType.TEXT, piece.start, piece.end, self._state.container)

    def _structural(self, piece: _Piece, rule: PatternRule, raw_marker: str) -> None:
        state = self._state
        state.seen_structure = True
        state.open_list = None
        marker = raw_marker.strip().rstrip(".")
        number = parse_number(marker) if rule.hierarchy == "marker_depth" else None
        if rule.hierarchy == "marker_depth" and number is None:
            raise ProfileRuntimeError(f"{rule.id}: маркер «{raw_marker}» не является десятичным номером")
        level = len(number) if number is not None else (rule.level or 1)
        if number is not None:
            parent = next(
                (state.by_number[number[:d]] for d in range(len(number) - 1, 0, -1) if number[:d] in state.by_number),
                None,
            )
        else:
            parent = next((index for lvl, index in reversed(state.levels) if lvl < level), None)
        node_type = NodeType.SECTION if level == 1 else NodeType.CLAUSE
        index = self._add(node_type, piece.start, piece.end, parent, marker)
        state.levels = [*(entry for entry in state.levels if entry[0] < level), (level, index)]
        if number is not None:
            state.by_number[number] = index
            state.last_number = number
        state.container = index
        if level == 1:
            state.section = index

    def _list_item(self, piece: _Piece, marker: str) -> None:
        state = self._state
        current = state.open_list
        restarts = current is not None and marker in _LIST_STARTS and not _next_letter(current.last_marker, marker)
        if current is None or current.container != state.container or restarts:
            list_node = self._add(NodeType.LIST, piece.start, piece.start, state.container)
            current = state.open_list = _OpenList(state.container, list_node, marker)
        self._add(NodeType.LIST_ITEM, piece.start, piece.end, current.node, marker)
        current.last_marker = marker

    def _heading(self, piece: _Piece) -> None:
        state = self._state
        state.open_list = None
        state.container = self._add(NodeType.HEADING, piece.start, piece.end, state.section)

    # -- finishing -------------------------------------------------------------------

    def finish(self) -> list[ParsedNode]:
        counts: dict[int | None, int] = {}
        for node in self.nodes:
            node.position = counts.get(node.parent, 0)
            counts[node.parent] = node.position + 1
            has_text = node.end > node.start
            node.range_start = node.start if has_text else len(self._extraction.original_text)
            node.range_end = node.end if has_text else _UNSET
        for node in reversed(self.nodes):
            if node.parent is not None:
                parent = self.nodes[node.parent]
                parent.range_start = min(parent.range_start, node.range_start)
                parent.range_end = max(parent.range_end, node.range_end)
        return self.nodes


def build_tree(extraction: Extraction, profile: CompiledProfile) -> list[ParsedNode]:
    """Apply a profile to an extraction.

    Args:
        extraction: Blocks and ``original_text`` of one file.
        profile: Validated profile for that file.

    Returns:
        Nodes in reading order; parents precede their children.

    Raises:
        ProfileRuntimeError: If a profile expression times out or yields an unusable marker.
    """
    engine = _TreeEngine(extraction, profile)
    try:
        for block in extraction.blocks:
            engine.add_block(block)
    except TimeoutError as exc:
        raise ProfileRuntimeError("Регулярное выражение профиля работает слишком долго на тексте документа") from exc
    return engine.finish()
