"""Text helpers for layout recovery and decimal clause numbering.

Used before an AI parsing profile exists (rebuilding PDF paragraphs from lines) and by the
tree engine for decimal markers. Regulations number clauses in plain text («5.3.2. …»), and
conversion often glues a clause onto the previous paragraph («…Общества. 3.10.Рабочие…»);
a number counts as a new clause only when it is a valid successor of the previous one, so
in-text references such as «п.11 Положения» stay intact.
"""

import re

type Number = tuple[int, ...]

_LEADING_NUMBER = re.compile(
    r"^(?:(?P<multi>\d{1,3}(?:\.\d{1,3})+)(?:\.\s*|\s+)|(?P<single>\d{1,3})\.\s*)(?=[^\d\s])",
)
_GLUED_NUMBER = re.compile(r"(?<=[.;:!?)»])\s+(?P<num>\d{1,3}(?:\.\d{1,3})*)\.\s*(?=[А-ЯЁA-Z])")
_LETTER_ITEM = re.compile(r"^(?P<letter>[а-яёa-z])[.)]\s+")
_DASH_ITEM = re.compile(r"^[-–—•]\s*")
_TOC_MARKERS = frozenset({"оглавление", "содержание"})
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse all whitespace (including non-breaking spaces) to single spaces."""
    return _WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip()


def parse_number(marker: str) -> Number | None:
    """Parse a decimal marker such as «5.3.2» into (5, 3, 2); None if it is not decimal."""
    parts = marker.strip(".").split(".")
    return tuple(int(part) for part in parts) if all(part.isdigit() for part in parts) else None


def leading_number(text: str) -> Number | None:
    """Return the clause number a fragment starts with, e.g. (5, 3, 2) for «5.3.2. текст»."""
    match = _LEADING_NUMBER.match(text)
    if match is None:
        return None
    return parse_number(match.group("multi") or match.group("single"))


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
        candidate = parse_number(match.group("num"))
        if candidate is not None and is_successor(candidate, last):
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
