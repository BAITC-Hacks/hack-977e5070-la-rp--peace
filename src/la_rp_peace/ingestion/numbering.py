"""Recover the clause tree of a regulation from its flat text blocks.

Regulations number their clauses in plain text («5.3.2. организует…»), not with Word list
numbering, and conversion often glues a clause onto the end of the previous paragraph
(«…Общества. 3.10.Рабочие места…»). A glued number is split off only when it is a valid
successor of the last clause seen, so in-text references such as «п.11 Положения» stay intact.
"""

import re
from collections import defaultdict
from collections.abc import Iterable

from la_rp_peace.enums import ClauseKind
from la_rp_peace.ingestion.types import Block, ParsedClause

type Number = tuple[int, ...]

_LEADING_NUMBER = re.compile(
    r"^(?:(?P<multi>\d{1,3}(?:\.\d{1,3})+)(?:\.\s*|\s+)|(?P<single>\d{1,3})\.\s*)(?=[^\d\s])",
)
_GLUED_NUMBER = re.compile(r"(?<=[.;:!?)»])\s+(?P<num>\d{1,3}(?:\.\d{1,3})*)\.\s*(?=[А-ЯЁA-Z])")
_LETTER_ITEM = re.compile(r"^(?P<letter>[а-яёa-z])[.)]\s+")
_DASH_ITEM = re.compile(r"^[-–—•]\s*")
_TOC_MARKERS = frozenset({"оглавление", "содержание"})
_TOC_ENTRY = re.compile(r"\s\d{1,3}$")
_WHITESPACE = re.compile(r"\s+")
_ROOT_ANCHOR = "вводная часть"


def normalize_text(text: str) -> str:
    """Collapse all whitespace (including non-breaking spaces) to single spaces."""
    return _WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip()


def leading_number(text: str) -> Number | None:
    """Return the clause number a fragment starts with, e.g. (5, 3, 2) for «5.3.2. текст»."""
    match = _LEADING_NUMBER.match(text)
    if match is None:
        return None
    raw = match.group("multi") or match.group("single")
    return tuple(int(part) for part in raw.split("."))


def is_successor(candidate: Number, last: Number | None) -> bool:
    """Tell whether a clause number may directly follow the previous one.

    Args:
        candidate: Number found in the text.
        last: Number of the most recent clause, or None at the start of a document.

    Returns:
        True for the first child of ``last`` or the next sibling at any depth.
    """
    if last is None:
        return candidate == (1,)
    if candidate == (*last, 1):
        return True
    return any(candidate == (*last[:depth], last[depth] + 1) for depth in range(len(last)))


def split_glued(text: str, last: Number | None) -> tuple[list[str], Number | None]:
    """Split clauses that were glued onto the end of a paragraph.

    Args:
        text: Normalised paragraph text.
        last: Number of the clause seen before this text.

    Returns:
        The pieces in order, and the last clause number seen once the text is consumed.
    """
    last = leading_number(text) or last
    pieces: list[str] = []
    start = 0
    for match in _GLUED_NUMBER.finditer(text):
        candidate = tuple(int(part) for part in match.group("num").split("."))
        if is_successor(candidate, last):
            pieces.append(text[start : match.start()].strip())
            start = match.start("num")
            last = candidate
    pieces.append(text[start:].strip())
    return [piece for piece in pieces if piece], last


def item_letter(text: str) -> str | None:
    """Return the letter of a lettered list item («б. текст» → «б»), else None."""
    match = _LETTER_ITEM.match(text)
    return None if match is None else match.group("letter")


def starts_dash_item(text: str) -> bool:
    """Tell whether text opens a dash («–») list item."""
    return _DASH_ITEM.match(text) is not None


def is_toc_marker(text: str) -> bool:
    """Tell whether text is a table-of-contents heading."""
    return text.casefold() in _TOC_MARKERS


def _is_heading_style(style: str | None) -> bool:
    if style is None:
        return False
    lowered = style.lower()
    return "heading" in lowered or lowered.startswith("заголовок")


def _shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class _TreeBuilder:
    """Accumulates clauses and tracks the numbering state while blocks stream in."""

    def __init__(self) -> None:
        self.clauses: list[ParsedClause] = []
        self._by_number: dict[Number, int] = {}
        self._last_number: Number | None = None
        self._container: int | None = None
        self._child_counts: defaultdict[int | None, int] = defaultdict(int)

    def add_block(self, block: Block) -> None:
        pieces, _ = split_glued(block.text, self._last_number)
        for piece in pieces:
            self._add_piece(piece, block)

    def _add_piece(self, text: str, block: Block) -> None:
        number = leading_number(text)
        if number is not None:
            self._add_numbered(number, text, block)
        elif (letter := _LETTER_ITEM.match(text)) is not None:
            self._add_child(ClauseKind.ITEM, text, block, f" «{letter.group('letter')}»")
        elif _DASH_ITEM.match(text) is not None:
            self._add_child(ClauseKind.ITEM, text, block, ", подп. {n}")
        elif _is_heading_style(block.style):
            self._add_unnumbered_heading(text, block)
        else:
            self._add_child(ClauseKind.PARAGRAPH, text, block, ", абз. {n}")

    def _append(self, clause: ParsedClause) -> int:
        self.clauses.append(clause)
        return len(self.clauses) - 1

    def _anchor_of(self, index: int | None) -> str:
        return _ROOT_ANCHOR if index is None else self.clauses[index].anchor

    def _add_numbered(self, number: Number, text: str, block: Block) -> None:
        parent = next(
            (
                self._by_number[number[:depth]]
                for depth in range(len(number) - 1, 0, -1)
                if number[:depth] in self._by_number
            ),
            None,
        )
        is_section = len(number) == 1 or _is_heading_style(block.style)
        dotted = ".".join(str(part) for part in number)
        index = self._append(
            ParsedClause(
                kind=ClauseKind.HEADING if is_section else ClauseKind.CLAUSE,
                text=text,
                anchor=f"разд. {dotted}" if len(number) == 1 else f"п. {dotted}",
                location=block.location,
                number=dotted,
                parent=parent,
            ),
        )
        self._by_number[number] = index
        self._last_number = number
        self._container = index

    def _add_unnumbered_heading(self, text: str, block: Block) -> None:
        section = self._by_number.get(self._last_number[:1]) if self._last_number else None
        index = self._append(
            ParsedClause(
                kind=ClauseKind.HEADING,
                text=text,
                anchor=f"«{_shorten(text)}»",
                location=block.location,
                parent=section,
            ),
        )
        self._container = index

    def _add_child(self, kind: ClauseKind, text: str, block: Block, suffix: str) -> None:
        parent = self._container
        self._child_counts[parent] += 1
        anchor = self._anchor_of(parent) + suffix.format(n=self._child_counts[parent])
        self._append(ParsedClause(kind=kind, text=text, anchor=anchor, location=block.location, parent=parent))


def build_clauses(blocks: Iterable[Block]) -> list[ParsedClause]:
    """Turn ordered text blocks into a clause tree.

    Table-of-contents entries (lines ending in a page number right after an
    «Оглавление»/«Содержание» marker) are dropped.

    Args:
        blocks: Blocks in reading order, text already normalised.

    Returns:
        Clauses in reading order; ``parent`` points at earlier list indices.
    """
    builder = _TreeBuilder()
    in_toc = False
    for block in blocks:
        if not block.text:
            continue
        if is_toc_marker(block.text):
            in_toc = True
            continue
        if in_toc and _TOC_ENTRY.search(block.text):
            continue
        in_toc = False
        builder.add_block(block)
    return builder.clauses
