"""Domain enumerations shared by ingestion, storage and the API."""

from enum import StrEnum


class DocSet(StrEnum):
    """Which part of the comparison a document belongs to."""

    BEFORE = "before"
    AFTER = "after"
    REGULATORY = "regulatory"
    BENCHMARK = "benchmark"


class DocType(StrEnum):
    """Kind of organisational document, as listed in the tech task input."""

    ORG_STRUCTURE = "org_structure"
    UNIT_REGULATION = "unit_regulation"
    JOB_DESCRIPTION = "job_description"
    ORDER = "order"
    INTERNAL_REGULATION = "internal_regulation"
    UNKNOWN = "unknown"


class DocFormat(StrEnum):
    """Supported upload formats."""

    DOCX = "docx"
    PDF = "pdf"
    XLSX = "xlsx"


class ClauseKind(StrEnum):
    """Role of a text fragment in the document structure."""

    HEADING = "heading"
    CLAUSE = "clause"
    ITEM = "item"
    PARAGRAPH = "paragraph"
    ROW = "row"
