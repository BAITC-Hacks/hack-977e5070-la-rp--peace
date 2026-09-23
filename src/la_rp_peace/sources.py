"""Resolve citations to the exact words of the original documents.

Every AI finding cites sources as (node id, quote). A quote is accepted only if it occurs
word for word in that node's own text (whitespace differences aside); anything else is
rejected, so no conclusion can rest on words the documents do not contain. A resolved source
carries everything a person needs to find the passage by hand — document, side, section
path, file location — plus exact offsets in the node text and in ``original_text``.
"""

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.enums import DocSet
from la_rp_peace.models import DocumentNode
from la_rp_peace.navigation import describe
from la_rp_peace.quotes import locate_quote


class NodeNotFoundError(LookupError):
    """No node has the cited id."""


class SourceRef(BaseModel):
    """A verified citation of original document text.

    Attributes:
        node_id: Cited node.
        document_id: Document the node belongs to.
        document_name: Original file name.
        doc_set: Side of the comparison («before», «after», …).
        anchor: Short citation, e.g. «п. 3.4 «а»».
        path: Where to look, from the section down.
        location: File position: ``page`` (PDF), ``paragraph`` (DOCX), ``sheet``/``row`` (XLSX).
        quote: The cited words, as they appear in the document.
        context: The node's own text containing the quote.
        start: Offset of the quote in ``context``.
        end: Offset just past the quote in ``context``.
        source_start: Offset of the quote in the document's ``original_text``.
        source_end: Offset just past the quote in ``original_text``.
    """

    node_id: int
    document_id: int
    document_name: str
    doc_set: DocSet | None = Field(serialization_alias="set")
    anchor: str
    path: str
    location: dict[str, Any]
    quote: str
    context: str
    start: int
    end: int
    source_start: int
    source_end: int


def resolve_source(session: Session, node_id: int, quote: str | None = None) -> SourceRef:
    """Verify a citation and describe where it is in the original document.

    Args:
        session: Database session.
        node_id: Cited node.
        quote: Cited words; None cites the node's whole own text.

    Returns:
        The resolved source.

    Raises:
        NodeNotFoundError: If the node does not exist.
        QuoteNotFoundError: If the quote is not in the node's text.
    """
    node = session.get(DocumentNode, node_id)
    if node is None:
        raise NodeNotFoundError(f"Узел {node_id} не найден")
    start, end = (0, len(node.text)) if quote is None else locate_quote(node.text, quote)
    document = node.document
    siblings = session.scalars(select(DocumentNode).where(DocumentNode.document_id == document.id)).all()
    place = describe(siblings, json.loads(document.source_map))[node.id]
    return SourceRef(
        node_id=node.id,
        document_id=document.id,
        document_name=document.file_name,
        doc_set=DocSet(document.doc_set) if document.doc_set else None,
        anchor=place.anchor,
        path=place.path,
        location=place.location,
        quote=node.text[start:end],
        context=node.text,
        start=start,
        end=end,
        source_start=node.source_start + start,
        source_end=node.source_start + end,
    )
