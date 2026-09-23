"""Shapes of the model's stage 3 answer for one block.

The model answers *provisions*: one provision with its shared fields (type, formulation,
condition, deadline, periodicity, specificity, participation) and its participants. The code
expands every provision into one record per participant, so the shared sources and the
participation mark stay identical in all of them.

A participant is named by its registry key ``E<entity_id>`` (the stage 2 registry of the
current document is shown to the model); ``null`` is an unresolved role or the undisclosed
remainder of a group, kept with its original designation and a note. Every source is a node
id, a verbatim quote and the list of claims it supports.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from la_rp_peace.entities.answers import SourceIn
from la_rp_peace.enums import ActivityType, Participation, Specificity

SUPPORT_FORMULATION = "formulation"
SUPPORT_TYPE = "type"
SUPPORT_CONDITION = "condition"
SUPPORT_DEADLINE = "deadline"
SUPPORT_PERIODICITY = "periodicity"
SUPPORT_PARTICIPATION = "participation"
SUPPORT_SPECIFICITY = "specificity"
SUPPORT_ENTITY = "entity"
SUPPORT_MEMBERSHIP = "membership"

PROVISION_SUPPORTS = frozenset(
    {
        SUPPORT_FORMULATION,
        SUPPORT_TYPE,
        SUPPORT_CONDITION,
        SUPPORT_DEADLINE,
        SUPPORT_PERIODICITY,
        SUPPORT_PARTICIPATION,
        SUPPORT_SPECIFICITY,
    },
)
PARTICIPANT_SUPPORTS = frozenset({SUPPORT_ENTITY, SUPPORT_MEMBERSHIP, SUPPORT_CONDITION})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParticipantIn(_Strict):
    """One participant of a provision; becomes a record of its own.

    ``group`` is the group wording through which the participant was included (e.g.
    «работники БВА»); its membership must then be confirmed by a ``membership`` source.
    ``condition`` is the participant's own condition, e.g. authority or appointment.
    """

    entity: str | None
    designation: str | None = None
    group: str | None = None
    condition: str | None = None
    note: str | None = None
    sources: list[SourceIn] = []


class ProvisionIn(_Strict):
    """One standalone provision of the block with all of its participants."""

    type: ActivityType
    type_unclear: bool = False
    formulation: str = Field(min_length=1)
    specificity: Specificity = Specificity.SPECIFIC
    condition: str | None = None
    deadline: str | None = None
    periodicity: str | None = None
    participation: Participation
    participant_designation: str = Field(min_length=1)
    participants: list[ParticipantIn] = Field(min_length=1)
    sources: list[SourceIn] = Field(min_length=1)
    notes: list[str] = []


class UnclearIn(_Strict):
    """A case in the block the model could not settle."""

    message: str = Field(min_length=1)
    node_ids: list[int] = []


class BlockAnswer(_Strict):
    """The answer for one block."""

    block_status: Literal["found", "none", "needs_clarification"]
    provisions: list[ProvisionIn] = []
    unclear: list[UnclearIn] = []
