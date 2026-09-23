"""Extract text blocks from PDF documents with a text layer."""

import pymupdf

from la_rp_peace.ingestion.numbering import normalize_text
from la_rp_peace.ingestion.types import Block, Location

_TEXT_BLOCK = 0


def read_pdf(data: bytes) -> list[Block]:
    """Read the text blocks of every page in reading order.

    Scanned PDFs without a text layer yield no blocks; OCR is out of scope.

    Args:
        data: Raw file bytes.

    Returns:
        One block per PDF text block, tagged with its 1-based page number.
    """
    blocks: list[Block] = []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for page in document:
            for raw in page.get_text("blocks", sort=True):
                text, block_type = raw[4], raw[6]
                if block_type != _TEXT_BLOCK:
                    continue
                normalized = normalize_text(text)
                if normalized:
                    blocks.append(Block(text=normalized, location=Location(page=page.number + 1)))
    return blocks
