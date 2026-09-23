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


class EntitiesStatus(StrEnum):
    """Progress of stage 2 (organisational entities) for a document."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ParentStatus(StrEnum):
    """How an entity's organisational parent is established."""

    RESOLVED = "resolved"
    ROOT = "root"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class EntityCategory(StrEnum):
    """Normalised category of an organisational object; later stages compare objects of one category."""

    ORGANIZATION = "organization"
    GOVERNING_BODY = "governing_body"
    BLOCK = "block"
    DEPARTMENT = "department"
    DIVISION = "division"
    GROUP = "group"
    POSITION = "position"
    COLLECTIVE = "collective"
    OTHER = "other"
    UNCLEAR = "unclear"


class ReviewStatus(StrEnum):
    """Review state of an entity."""

    PENDING = "pending"
    CHECKED = "checked"
    NEEDS_REVIEW = "needs_review"


class RelationType(StrEnum):
    """Relations kept apart from organisational membership."""

    FUNCTIONAL_SUBORDINATION = "functional_subordination"
    ADMINISTRATIVE_MANAGEMENT = "administrative_management"
    REPORTS_TO = "reports_to"
    MEMBERSHIP = "membership"
    OTHER = "other"


class BlockStatus(StrEnum):
    """Outcome of one block sent to the model."""

    FOUND = "found"
    NONE = "none"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"


class EntityIssueType(StrEnum):
    """Kinds of stage 2 problems."""

    AMBIGUOUS_PARENT = "ambiguous_parent"
    AMBIGUOUS_MERGE = "ambiguous_merge"
    UNSUPPORTED_ATTRIBUTE = "unsupported_attribute"
    BLOCK_FAILED = "block_failed"
    CYCLE = "cycle"
    OTHER = "other"


class ActivitiesStatus(StrEnum):
    """Progress of stage 3 (activities) for a document."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ActivityType(StrEnum):
    """Kind of provision assigned to an entity, judged by meaning, not by section title."""

    GOAL = "goal"
    TASK = "task"
    FUNCTION = "function"
    DUTY = "duty"
    RIGHT = "right"
    PROHIBITION = "prohibition"
    OTHER = "other"


class Participation(StrEnum):
    """How the participants of one provision share it (each keeps a record of their own)."""

    INDIVIDUAL = "individual"
    EACH = "each"
    JOINT = "joint"
    ALTERNATIVE = "alternative"
    UNCLEAR = "unclear"


class Specificity(StrEnum):
    """Whether a record's content is disclosed; does not replace its type."""

    SPECIFIC = "specific"
    GENERALIZED = "generalized"
    NEEDS_CLARIFICATION = "needs_clarification"


class ActivityIssueType(StrEnum):
    """Kinds of stage 3 problems."""

    UNCLEAR_TYPE = "unclear_type"
    UNRESOLVED_ENTITY = "unresolved_entity"
    UNCLEAR_PARTICIPATION = "unclear_participation"
    UNCLEAR = "unclear"
    BLOCK_FAILED = "block_failed"
    OTHER = "other"


class AnalysisStatus(StrEnum):
    """Progress of an analysis stage (4.1 collisions, 4.2 cascade) for a document."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


# Stage 4.1 enums (function collisions) go below this line.


# Stage 4.2 enums (function cascade) go below this line.
