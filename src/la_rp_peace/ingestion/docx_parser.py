"""Extract text blocks from Word (.docx) documents."""

from io import BytesIO

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from la_rp_peace.ingestion.numbering import normalize_text
from la_rp_peace.ingestion.types import Block, Location

_TITLE_STYLE_MARKERS = ("title", "название")


def _row_text(cells: list[str]) -> str:
    # Merged cells repeat the same text in every grid cell they span.
    unique: list[str] = []
    for cell in cells:
        if cell and (not unique or unique[-1] != cell):
            unique.append(cell)
    return " | ".join(unique)


def _table_blocks(table: Table, index: int) -> list[Block]:
    blocks = []
    for row_number, row in enumerate(table.rows, start=1):
        text = _row_text([normalize_text(cell.text) for cell in row.cells])
        if text:
            blocks.append(Block(text=text, location=Location(paragraph_index=index, row=row_number), style="table"))
    return blocks


def read_docx(data: bytes) -> tuple[list[Block], str | None]:
    """Read paragraphs and table rows of a .docx file in document order.

    Args:
        data: Raw file bytes.

    Returns:
        The blocks, and the document title assembled from title-styled paragraphs
        (None when the document has none).
    """
    document = docx.Document(BytesIO(data))
    blocks: list[Block] = []
    title_parts: list[str] = []
    for index, item in enumerate(document.iter_inner_content()):
        if isinstance(item, Table):
            blocks.extend(_table_blocks(item, index))
            continue
        paragraph: Paragraph = item
        text = normalize_text(paragraph.text)
        style = paragraph.style.name if paragraph.style is not None else None
        if style is not None and any(marker in style.lower() for marker in _TITLE_STYLE_MARKERS) and text:
            title_parts.append(text)
        blocks.append(Block(text=text, location=Location(paragraph_index=index), style=style))
    return blocks, " ".join(title_parts) or None
