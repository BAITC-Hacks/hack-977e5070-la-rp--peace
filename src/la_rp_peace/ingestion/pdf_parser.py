"""Extract paragraphs from PDF documents with a text layer.

A PDF has positioned text fragments, not paragraphs: PyMuPDF's layout blocks both merge
neighbouring clauses and split wrapped ones, and justified lines arrive as one fragment
per word. Fragments sharing a baseline are first merged into visual lines, then lines
into paragraphs. A new paragraph starts at a structural marker (the next clause number;
a dash item after a line that ends a sentence; a letter item that does so, is «а», or
continues the lettering) or where bold text begins or ends; consecutive bold lines stay
together only when tightly spaced, so a wrapped heading is one block while
table-of-contents entries are not. Before the first clause every line is its own
paragraph (approval stamp, title). Paragraphs continue across page breaks, a line
ending in a hyphen joins the next without a space, and bare page numbers are dropped.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pymupdf

from la_rp_peace.ingestion.numbering import (
    Number,
    is_successor,
    is_toc_marker,
    item_letter,
    leading_number,
    normalize_text,
    split_glued,
    starts_dash_item,
)
from la_rp_peace.ingestion.types import Block, Location

HEADING_STYLE = "pdf-heading"
_TEXT_BLOCK = 0
_PAGE_NUMBER = re.compile(r"^\d{1,3}$")
_SENTENCE_END = (".", ";", ":", "!", "?")
_LETTERS = "абвгдежзиклмнопрстуфхцчшщэюя"
_LINE_END_HYPHEN = re.compile(r"\w-$")
# Wrapped heading lines sit ~3pt apart; separate headings and TOC entries 10pt or more.
_MAX_HEADING_GAP_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    page: int
    bold: bool
    top: float
    bottom: float


def _join(parts: list[str]) -> str:
    """Join wrapped lines; a line ending in a hyphen continues the word («нормативно-» + «правовые»)."""
    text = ""
    for part in parts:
        separator = "" if not text or _LINE_END_HYPHEN.search(text) else " "
        text += separator + part
    return text


@dataclass(slots=True)
class _Fragment:
    x: float
    top: float
    bottom: float
    spans: list[dict[str, Any]]


def _is_bold(spans: list[dict[str, Any]]) -> bool:
    visible = [span for span in spans if span["text"].strip()]
    return bool(visible) and all(span["flags"] & pymupdf.TEXT_FONT_BOLD for span in visible)


def _fragments(page: pymupdf.Page) -> list[_Fragment]:
    fragments = [
        _Fragment(x=line["bbox"][0], top=line["bbox"][1], bottom=line["bbox"][3], spans=line["spans"])
        for block in page.get_text("dict")["blocks"]
        if block["type"] == _TEXT_BLOCK
        for line in block["lines"]
    ]
    return sorted(fragments, key=lambda fragment: ((fragment.top + fragment.bottom) / 2, fragment.x))


def _same_baseline(row: list[_Fragment], fragment: _Fragment) -> bool:
    middle = (fragment.top + fragment.bottom) / 2
    return row[0].top <= middle <= row[0].bottom


def _visual_rows(page: pymupdf.Page) -> Iterator[list[_Fragment]]:
    row: list[_Fragment] = []
    for fragment in _fragments(page):
        if row and not _same_baseline(row, fragment):
            yield sorted(row, key=lambda item: item.x)
            row = []
        row.append(fragment)
    if row:
        yield sorted(row, key=lambda item: item.x)


def _lines(document: pymupdf.Document) -> Iterator[_Line]:
    for page in document.pages():
        for row in _visual_rows(page):
            spans = [span for fragment in row for span in fragment.spans]
            text = normalize_text(" ".join(span["text"] for span in spans))
            if text and not _PAGE_NUMBER.match(text):
                yield _Line(
                    text=text,
                    page=page.number + 1,
                    bold=_is_bold(spans),
                    top=min(fragment.top for fragment in row),
                    bottom=max(fragment.bottom for fragment in row),
                )


class _ParagraphAssembler:
    """Joins lines into paragraph blocks while tracking the clause numbering."""

    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.title_parts: list[str] = []
        self._parts: list[str] = []
        self._page = 0
        self._bold = False
        self._previous: _Line | None = None
        self._letter: str | None = None
        self._last_before: Number | None = None
        self._last: Number | None = None

    def feed(self, line: _Line) -> None:
        if self._parts and not self._starts_paragraph(line):
            self._parts.append(line.text)
        else:
            self.flush()
            self._parts, self._page, self._bold = [line.text], line.page, line.bold
            self._last_before = self._last
            self._letter = item_letter(line.text)
        _, self._last = split_glued(_join(self._parts), self._last_before)
        self._previous = line

    def _starts_paragraph(self, line: _Line) -> bool:
        previous = self._previous
        # Before the first clause sit approval stamps and titles: short lines, not prose.
        if previous is None or self._last is None or line.bold != self._bold or is_toc_marker(line.text):
            return True
        if line.bold:
            gap = line.top - previous.bottom
            return line.page != previous.page or gap > _MAX_HEADING_GAP_RATIO * (line.bottom - line.top)
        if self._starts_item(line.text, previous.text.endswith(_SENTENCE_END)):
            return True
        number = leading_number(line.text)
        return number is not None and is_successor(number, self._last)

    def _starts_item(self, text: str, after_sentence_end: bool) -> bool:
        letter = item_letter(text)
        if letter is None:
            return after_sentence_end and starts_dash_item(text)
        if after_sentence_end or letter == _LETTERS[0]:
            return True
        previous = self._letter
        return previous is not None and previous in _LETTERS[:-1] and letter == _LETTERS[_LETTERS.index(previous) + 1]

    def flush(self) -> None:
        if not self._parts:
            return
        text = _join(self._parts)
        is_title = self._bold and self._last_before is None and leading_number(text) is None
        if is_title:
            self.title_parts.append(text)
        # Title lines are plain paragraphs, matching title-styled Word paragraphs.
        style = HEADING_STYLE if self._bold and not is_title else None
        self.blocks.append(Block(text=text, location=Location(page=self._page), style=style))
        self._parts = []


def read_pdf(data: bytes) -> tuple[list[Block], str | None]:
    """Read the paragraphs of every page in reading order.

    Scanned PDFs without a text layer yield no blocks; OCR is out of scope.

    Args:
        data: Raw file bytes.

    Returns:
        Paragraph blocks tagged with the 1-based page they start on, and the title
        assembled from bold lines before the first numbered clause (None if absent).
    """
    assembler = _ParagraphAssembler()
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for line in _lines(document):
            assembler.feed(line)
    assembler.flush()
    return assembler.blocks, " ".join(assembler.title_parts) or None
