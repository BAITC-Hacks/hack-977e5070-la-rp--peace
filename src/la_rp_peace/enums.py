"""Domain enumerations shared by ingestion, storage and the API.

Values match the CHECK constraints in schema.sql.
"""

from enum import StrEnum


class DocSet(StrEnum):
    """Which part of the comparison a document belongs to."""

    BEFORE = "before"
    AFTER = "after"
    REGULATORY = "regulatory"
    BENCHMARK = "benchmark"


class DocFormat(StrEnum):
    """Supported upload formats."""

    DOCX = "docx"
    PDF = "pdf"
    XLSX = "xlsx"


class NodeType(StrEnum):
    """Type of a document tree node."""

    SECTION = "section"
    CLAUSE = "clause"
    HEADING = "heading"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    TEXT = "text"
    SERVICE = "service"


class ParseStatus(StrEnum):
    """Lifecycle of a document's parsing."""

    PENDING = "pending"
    PARSED = "parsed"
    NEEDS_REVIEW = "needs_review"
    VALIDATED = "validated"


class IssueType(StrEnum):
    """Kinds of parsing problems."""

    EMPTY_CONTENT = "empty_content"
    AMBIGUOUS_BOUNDARY = "ambiguous_boundary"
    AMBIGUOUS_PARENT = "ambiguous_parent"
    NUMBERING_GAP = "numbering_gap"
    UNCOVERED_TEXT = "uncovered_text"
    OTHER = "other"
