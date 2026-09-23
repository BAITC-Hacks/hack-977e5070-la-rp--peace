"""Shapes of the model's stage 2 answers.

References: ``E<n>`` names an entity already in the document's registry (shown to the model);
any other ``ref`` is a new entity local to the answer. Every source is a node id plus a
verbatim quote and the list of claims it supports.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from la_rp_peace.enums import EntityCategory, ParentStatus, RelationType

SUPPORT_NAME = "name"
SUPPORT_TYPE = "type"
SUPPORT_CATEGORY = "category"
SUPPORT_PARENT = "parent"
SUPPORT_POSITION_TYPE = "position_type"
SUPPORT_LEVEL = "level"
SUPPORT_RELATION = "relation"
SUPPORT_SAME_ENTITY = "same_entity"
ROLE_SUPPORT_PREFIX = "role:"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SourceIn(_Strict):
    """A cited fragment: node, verbatim quote, and what it supports."""

    node_id: int
    quote: str = Field(min_length=1)
    supports: list[str] = Field(min_length=1)


class RoleIn(_Strict):
    """A confirmed functional role of a position, with its scope or condition."""

    role: str = Field(min_length=1)
    scope: str | None = None
    sources: list[SourceIn] = Field(min_length=1)


class ParentIn(_Strict):
    """The organisational parent as the model sees it."""

    ref: str | None = None
    status: ParentStatus
    candidates: list[str] = []
    sources: list[SourceIn] = []


class MentionIn(_Strict):
    """An organisational object mentioned in the block."""

    ref: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: list[str] = []
    type: str = Field(min_length=1)
    category: EntityCategory
    position_type: str | None = None
    level: str | None = None
    roles: list[RoleIn] = []
    parent: ParentIn
    sources: list[SourceIn] = Field(min_length=1)


class RelationIn(_Strict):
    """A relation other than organisational membership."""

    from_ref: str = Field(alias="from", min_length=1)
    to_ref: str = Field(alias="to", min_length=1)
    type: RelationType
    conditions: str | None = None
    sources: list[SourceIn] = Field(min_length=1)


class UnclearIn(_Strict):
    """A case the model could not settle."""

    message: str = Field(min_length=1)
    node_ids: list[int] = []
    refs: list[str] = []


class BlockAnswer(_Strict):
    """The answer for one block."""

    block_status: Literal["found", "none", "needs_clarification"]
    mentions: list[MentionIn] = []
    relations: list[RelationIn] = []
    unclear: list[UnclearIn] = []


class MergeIn(_Strict):
    """Two registry entities that are the same object (e.g. full name and abbreviation)."""

    keep: str
    merge: str
    sources: list[SourceIn] = Field(min_length=1)


class ParentUpdateIn(_Strict):
    """A corrected organisational parent."""

    entity: str
    parent: str | None = None
    status: ParentStatus
    candidates: list[str] = []
    sources: list[SourceIn] = []


class ConsolidationAnswer(_Strict):
    """The whole-document review of the registry."""

    merges: list[MergeIn] = []
    parent_updates: list[ParentUpdateIn] = []
    unresolved: list[UnclearIn] = []
