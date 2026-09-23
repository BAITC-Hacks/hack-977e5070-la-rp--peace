"""Shapes of the model's stage 3 answer for one block.

An entity is named by its registry key ``E<entity_id>`` (the stage 2 registry of the current
document is shown to the model); ``null`` means the executor is not in the registry and the
original designation plus a note are kept instead. Every source is a node id, a verbatim quote
and the list of fields it supports.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from la_rp_peace.entities.answers import SourceIn
from la_rp_peace.enums import ActivityType, Participation

SUPPORT_FORMULATION = "formulation"
SUPPORT_TYPE = "type"
SUPPORT_CONDITION = "condition"
SUPPORT_DEADLINE = "deadline"
SUPPORT_PERIODICITY = "periodicity"
SUPPORT_BINDING = "binding"

RECORD_SUPPORTS = frozenset(
    {SUPPORT_FORMULATION, SUPPORT_TYPE, SUPPORT_CONDITION, SUPPORT_DEADLINE, SUPPORT_PERIODICITY},
)
BINDING_SUPPORTS = frozenset({SUPPORT_BINDING, SUPPORT_CONDITION})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BindingIn(_Strict):
    """An entity a record is assigned to, or an executor missing from the registry."""

    entity: str | None
    designation: str | None = None
    participation: Participation
    condition: str | None = None
    note: str | None = None
    sources: list[SourceIn] = []


class RecordIn(_Strict):
    """One standalone provision of the block."""

    type: ActivityType
    type_unclear: bool = False
    formulation: str = Field(min_length=1)
    condition: str | None = None
    deadline: str | None = None
    periodicity: str | None = None
    bindings: list[BindingIn] = Field(min_length=1)
    sources: list[SourceIn] = Field(min_length=1)
    notes: list[str] = []


class UnclearIn(_Strict):
    """A case in the block the model could not settle."""

    message: str = Field(min_length=1)
    node_ids: list[int] = []


class BlockAnswer(_Strict):
    """The answer for one block."""

    block_status: Literal["found", "none", "needs_clarification"]
    records: list[RecordIn] = []
    unclear: list[UnclearIn] = []
