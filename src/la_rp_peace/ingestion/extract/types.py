"""Result of extracting text from a file, before any structure is recognised."""

from dataclasses import dataclass, field
from typing import Any

from la_rp_peace.enums import DocFormat

type Location = dict[str, Any]

BLOCK_SEPARATOR = "\n"
CELL_SEPARATOR = "\t"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Maps ``original_text[start:end]`` to a position in the file (page, paragraph, cell…)."""

    start: int
    end: int
    location: Location

    def as_json(self) -> dict[str, Any]:
        """Return the methodology's source_map entry."""
        return {"start": self.start, "end": self.end, "location": self.location}


@dataclass(frozen=True, slots=True)
class Cell:
    """A table cell inside a row block."""

    start: int
    end: int
    location: Location


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A paragraph, table row or page number, with its range in ``original_text``.

    Attributes:
        start: Offset of the block in ``original_text``.
        end: Offset just past the block.
        text: ``original_text[start:end]``.
        location: Where the block starts in the file.
        style: Word paragraph style, ``bold`` for bold PDF lines, ``page_number`` for PDF
            page numbers, ``table`` for table rows; None otherwise.
        cells: Cell ranges for table and worksheet rows.
    """

    start: int
    end: int
    text: str
    location: Location
    style: str | None = None
    cells: tuple[Cell, ...] = ()


@dataclass(slots=True)
class Extraction:
    """Text representation of one file.

    ``original_text`` is the blocks' whitespace-normalised text joined with newlines; it is
    never changed after extraction, and every offset in the pipeline refers to it.
    """

    source_format: DocFormat
    original_text: str
    blocks: list[TextBlock]
    source_map: list[SourceSpan]
    file_metadata: dict[str, Any] = field(default_factory=dict)


class TextBuilder:
    """Appends blocks to ``original_text`` while recording their offsets."""

    def __init__(self) -> None:
        """Start with empty text."""
        self._parts: list[str] = []
        self._length = 0
        self.blocks: list[TextBlock] = []
        self.source_map: list[SourceSpan] = []

    def _append(self, text: str) -> int:
        if self._parts:
            self._parts.append(BLOCK_SEPARATOR)
            self._length += len(BLOCK_SEPARATOR)
        start = self._length
        self._parts.append(text)
        self._length += len(text)
        return start

    def add(
        self,
        text: str,
        location: Location,
        style: str | None = None,
        pieces: list[tuple[int, int, Location]] | None = None,
    ) -> TextBlock:
        """Append a paragraph-like block.

        Args:
            text: Normalised block text; must not be empty.
            location: Where the block starts in the file.
            style: Style tag, see ``TextBlock.style``.
            pieces: Sub-ranges of ``text`` with their own locations (e.g. PDF lines on
                different pages); one span for the whole block when omitted.

        Returns:
            The recorded block.
        """
        start = self._append(text)
        for piece_start, piece_end, piece_location in pieces or [(0, len(text), location)]:
            self.source_map.append(SourceSpan(start + piece_start, start + piece_end, piece_location))
        block = TextBlock(start=start, end=start + len(text), text=text, location=location, style=style)
        self.blocks.append(block)
        return block

    def add_row(self, cells: list[tuple[str, Location]], location: Location) -> TextBlock:
        """Append a table or worksheet row; cells are joined with tabs.

        Args:
            cells: Non-empty normalised cell texts with their locations.
            location: Where the row is in the file.

        Returns:
            The recorded row block.
        """
        text = CELL_SEPARATOR.join(cell_text for cell_text, _ in cells)
        start = self._append(text)
        recorded: list[Cell] = []
        offset = start
        for cell_text, cell_location in cells:
            recorded.append(Cell(offset, offset + len(cell_text), cell_location))
            self.source_map.append(SourceSpan(offset, offset + len(cell_text), cell_location))
            offset += len(cell_text) + len(CELL_SEPARATOR)
        block = TextBlock(start, start + len(text), text, location, style="table", cells=tuple(recorded))
        self.blocks.append(block)
        return block

    def text(self) -> str:
        """Return the accumulated ``original_text``."""
        return "".join(self._parts)
