"""Intermediate structures produced by the format parsers."""

from dataclasses import dataclass, field

from la_rp_peace.enums import ClauseKind, DocFormat, DocType


@dataclass(frozen=True, slots=True)
class Location:
    """Where a fragment sits in the original file; unused fields stay None."""

    paragraph_index: int | None = None
    page: int | None = None
    sheet: str | None = None
    row: int | None = None


@dataclass(frozen=True, slots=True)
class Block:
    """A raw text block extracted from a file, before structure is recovered.

    Attributes:
        text: Whitespace-normalised text.
        location: Position in the source file.
        style: Source style name (Word paragraph style), if any.
    """

    text: str
    location: Location
    style: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedClause:
    """A structural fragment with its place in the clause tree.

    Attributes:
        kind: Structural role of the fragment.
        text: Fragment text, including its own number prefix.
        anchor: Short citation, e.g. «п. 5.3.2 «а»».
        path: Where to look in the document, from the section down, e.g.
            «Разд. 3 «Структура…» › п. 3.4 › подп. «а»».
        location: Position in the source file.
        number: Dotted clause number for numbered clauses, e.g. «5.3.2».
        parent: Index of the parent clause in the document's clause list.
    """

    kind: ClauseKind
    text: str
    anchor: str
    path: str
    location: Location
    number: str | None = None
    parent: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Everything recovered from one uploaded file."""

    format: DocFormat
    doc_type: DocType
    title: str | None
    clauses: list[ParsedClause] = field(default_factory=list)
