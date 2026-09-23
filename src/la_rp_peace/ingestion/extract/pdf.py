"""Extract paragraphs from PDF documents with a text layer.

A PDF has positioned text fragments, not paragraphs: PyMuPDF's layout blocks both merge
neighbouring clauses and split wrapped ones, and justified lines arrive as one fragment
per word. Fragments sharing a baseline are first merged into visual lines, then lines
into paragraphs. This is layout recovery, done before the AI profile exists, so it relies
on generic cues: a new paragraph starts at the next decimal clause number, at a dash item
after a line that ends a sentence, at a letter item that does so, is «а», or continues the
lettering, or where bold text begins or ends; consecutive bold lines stay together only
when tightly spaced, so a wrapped heading is one block while table-of-contents entries
are not. Before the first clause every line is its own paragraph (approval stamp, title).
Paragraphs continue across page breaks, and a line ending in a hyphen joins the next
without a space. Bare page numbers become separate ``page_number`` blocks placed after
the paragraph they interrupt, so no text is lost and paragraphs stay whole.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pymupdf

from la_rp_peace.enums import DocFormat
from la_rp_peace.ingestion.extract.types import Extraction, Location, TextBuilder
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

BOLD_STYLE = "bold"
PAGE_NUMBER_STYLE = "page_number"
_TEXT_BLOCK = 0
_PAGE_NUMBER = re.compile(r"^\d{1,3}$")
_SENTENCE_END = (".", ";", ":", "!", "?")
_LETTERS = "абвгдежзиклмнопрстуфхцчшщэюя"
_LINE_END_HYPHEN = re.compile(r"\w-$")
# Wrapped heading lines sit ~3pt apart; separate headings and TOC entries 10pt or more.
_MAX_HEADING_GAP_RATIO = 0.5
_METADATA_SOURCE = "pdf.metadata"
_METADATA_KEYS = ("title", "author", "creator", "producer", "creationDate", "modDate")


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    page: int
    bold: bool
    top: float
    bottom: float


@dataclass(slots=True)
class _Fragment:
    x: float
    top: float
    bottom: float
    spans: list[dict[str, Any]]


def _join(lines: list[_Line]) -> tuple[str, list[tuple[int, int, Location]]]:
    """Join wrapped lines; a line ending in a hyphen continues the word («нормативно-» + «правовые»).

    Returns:
        The paragraph text and each line's range in it with its page.
    """
    text = ""
    pieces: list[tuple[int, int, Location]] = []
    for line in lines:
        if text and not _LINE_END_HYPHEN.search(text):
            text += " "
        pieces.append((len(text), len(text) + len(line.text), {"page": line.page}))
        text += line.text
    return text, pieces


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
            if text:
                yield _Line(
                    text=text,
                    page=page.number + 1,
                    bold=_is_bold(spans),
                    top=min(fragment.top for fragment in row),
                    bottom=max(fragment.bottom for fragment in row),
                )


class _ParagraphAssembler:
    """Joins lines into paragraph blocks while tracking the clause numbering."""

    def __init__(self, builder: TextBuilder) -> None:
        self._builder = builder
        self._lines: list[_Line] = []
        self._page_numbers: list[_Line] = []
        self._bold = False
        self._previous: _Line | None = None
        self._letter: str | None = None
        self._last_before: Number | None = None
        self._last: Number | None = None

    def feed(self, line: _Line) -> None:
        if _PAGE_NUMBER.match(line.text):
            self._page_numbers.append(line)
            if not self._lines:
                self._flush_page_numbers()
            return
        if self._lines and not self._starts_paragraph(line):
            self._lines.append(line)
        else:
            self.flush()
            self._lines, self._bold = [line], line.bold
            self._last_before = self._last
            self._letter = item_letter(line.text)
        _, self._last = split_glued(_join(self._lines)[0], self._last_before)
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

    def _flush_page_numbers(self) -> None:
        for line in self._page_numbers:
            self._builder.add(line.text, {"page": line.page}, style=PAGE_NUMBER_STYLE)
        self._page_numbers = []

    def flush(self) -> None:
        if self._lines:
            text, pieces = _join(self._lines)
            style = BOLD_STYLE if self._bold else None
            self._builder.add(text, {"page": self._lines[0].page}, style=style, pieces=pieces)
            self._lines = []
        self._flush_page_numbers()


def _file_metadata(document: pymupdf.Document) -> dict[str, Any]:
    raw = document.metadata or {}
    return {key: {"value": raw[key], "source": _METADATA_SOURCE} for key in _METADATA_KEYS if raw.get(key)}


def extract_pdf(data: bytes) -> Extraction:
    """Read the paragraphs of every page in reading order.

    Scanned PDFs without a text layer yield no blocks; OCR is out of scope.

    Args:
        data: Raw file bytes.

    Returns:
        The extraction; each line of a paragraph is mapped to its own page.
    """
    builder = TextBuilder()
    assembler = _ParagraphAssembler(builder)
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for line in _lines(document):
            assembler.feed(line)
        assembler.flush()
        metadata = _file_metadata(document)
    return Extraction(
        source_format=DocFormat.PDF,
        original_text=builder.text(),
        blocks=builder.blocks,
        source_map=builder.source_map,
        file_metadata=metadata,
    )
