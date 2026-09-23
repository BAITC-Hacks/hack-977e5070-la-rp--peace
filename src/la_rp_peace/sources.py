"""Resolve citations to the exact words of the original documents.

Every AI finding cites sources as (clause id, quote). A quote is accepted only if it
occurs word for word in that clause's text (whitespace differences aside); anything
else is rejected, so no conclusion can rest on words the documents do not contain. A
resolved source carries everything a person needs to find the passage by hand: the
document, its side, the section path, the page for PDFs, and the quote's position
within the clause text.
"""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from la_rp_peace.enums import DocSet
from la_rp_peace.ingestion.numbering import normalize_text
from la_rp_peace.models import Clause


class ClauseNotFoundError(LookupError):
    """No clause has the cited id."""


class QuoteNotFoundError(ValueError):
    """The quote does not occur in the cited clause."""


class SourceRef(BaseModel):
    """A verified citation of original document text.

    Attributes:
        clause_id: Cited clause.
        document_id: Document the clause belongs to.
        document_name: Original file name.
        doc_set: Side of the comparison («before», «after», …).
        anchor: Short citation, e.g. «п. 3.4 «а»».
        path: Where to look, from the section down.
        page: 1-based page (PDF only).
        paragraph_index: Paragraph position (DOCX only).
        sheet: Worksheet name (XLSX only).
        row: Worksheet row (XLSX only).
        quote: The cited words, as they appear in the clause.
        context: Full clause text containing the quote.
        start: Offset of the quote in ``context``.
        end: Offset just past the quote in ``context``.
    """

    clause_id: str
    document_id: str
    document_name: str
    doc_set: DocSet = Field(serialization_alias="set")
    anchor: str
    path: str
    page: int | None
    paragraph_index: int | None
    sheet: str | None
    row: int | None
    quote: str
    context: str
    start: int
    end: int


def locate_quote(text: str, quote: str) -> tuple[int, int]:
    """Find a quote in clause text.

    Args:
        text: Normalised clause text.
        quote: Cited words; whitespace is normalised before matching.

    Returns:
        Start and end offsets of the first occurrence.

    Raises:
        QuoteNotFoundError: If the quote is empty or not in the text.
    """
    needle = normalize_text(quote)
    start = text.find(needle) if needle else -1
    if start < 0:
        raise QuoteNotFoundError(f"Цитата не найдена в тексте пункта: «{quote}»")
    return start, start + len(needle)


def resolve_source(session: Session, clause_id: str, quote: str | None = None) -> SourceRef:
    """Verify a citation and describe where it is in the original document.

    Args:
        session: Database session.
        clause_id: Cited clause.
        quote: Cited words; None cites the whole clause.

    Returns:
        The resolved source.

    Raises:
        ClauseNotFoundError: If the clause does not exist.
        QuoteNotFoundError: If the quote is not in the clause.
    """
    clause = session.get(Clause, clause_id)
    if clause is None:
        raise ClauseNotFoundError(f"Пункт {clause_id} не найден")
    start, end = (0, len(clause.text)) if quote is None else locate_quote(clause.text, quote)
    document = clause.document
    return SourceRef(
        clause_id=clause.id,
        document_id=document.id,
        document_name=document.filename,
        doc_set=document.doc_set,
        anchor=clause.anchor,
        path=clause.path,
        page=clause.page,
        paragraph_index=clause.paragraph_index,
        sheet=clause.sheet,
        row=clause.row,
        quote=clause.text[start:end],
        context=clause.text,
        start=start,
        end=end,
    )
