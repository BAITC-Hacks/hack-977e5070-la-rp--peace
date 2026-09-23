"""Groups of the cascade (methodology 4.2 §1): an object of level N, its direct executors N+1, their functions.

Levels come from established organisational links only: a child belongs to the group of N when
its ``parent_status`` is ``resolved`` and ``parent_id`` is N. Parent and child functions are the
``task``/``function``/``duty`` records of the entities themselves. Functions of entities whose
parent is unknown or ambiguous cannot be checked bottom-up; they need clarification, never «no
pair». Records without an entity (unresolved roles) cannot be placed in any group and are only
counted.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.enums import ActivityType, CascadeFindingReason, ParentStatus
from la_rp_peace.models import ActivityRecord, Entity

FUNCTION_TYPES = frozenset({ActivityType.TASK.value, ActivityType.FUNCTION.value, ActivityType.DUTY.value})

_UNCLEAR_PARENT = {
    ParentStatus.UNKNOWN.value: CascadeFindingReason.PARENT_UNKNOWN,
    ParentStatus.AMBIGUOUS.value: CascadeFindingReason.PARENT_AMBIGUOUS,
}


@dataclass(frozen=True, slots=True)
class Group:
    """Object N with its direct executors and the functions compared between them.

    Attributes:
        entity: The object of level N.
        children: Its direct executors (``parent_status = resolved``).
        parent_records: Functions of N, in id order.
        child_records: Functions of the children, in id order.
        uncertain_entity_ids: Entities whose parent is ambiguous with N among the candidates:
            the set of executors is not established, so N's missing children are not final.
    """

    entity: Entity
    children: tuple[Entity, ...]
    parent_records: tuple[ActivityRecord, ...]
    child_records: tuple[ActivityRecord, ...]
    uncertain_entity_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Clarification:
    """A function whose basis cannot be checked because its entity's parent is not established."""

    record: ActivityRecord
    entity: Entity
    reason: CascadeFindingReason


@dataclass(frozen=True, slots=True)
class Structure:
    """Everything the cascade checks in one document.

    Attributes:
        entities: All entities of the document by id.
        groups: One group per entity with at least one direct executor.
        clarifications: Functions of entities with an unknown or ambiguous parent.
        excluded: Functions without an entity; they belong to no group.
    """

    entities: dict[int, Entity]
    groups: tuple[Group, ...]
    clarifications: tuple[Clarification, ...]
    excluded: tuple[ActivityRecord, ...]


def entity_of(record: ActivityRecord) -> int:
    """Return the entity of a grouped function record.

    Raises:
        ValueError: If the record has no entity (such records are excluded from every group).
    """
    if record.entity_id is None:
        raise ValueError(f"Activity record {record.id} has no entity and belongs to no group")
    return record.entity_id


def _uncertain(entity_id: int, entities: Sequence[Entity]) -> tuple[int, ...]:
    return tuple(
        other.id
        for other in entities
        if other.parent_status == ParentStatus.AMBIGUOUS.value and entity_id in json.loads(other.parent_candidates)
    )


def build_structure(entities: Sequence[Entity], records: Sequence[ActivityRecord]) -> Structure:
    """Build the groups, clarifications and exclusions from the stage 2 and stage 3 rows.

    Args:
        entities: All entities of the document.
        records: All activity records of the document; non-function types are ignored.

    Returns:
        The structure, with groups in entity id order and records in id order.
    """
    functions = sorted((record for record in records if record.record_type in FUNCTION_TYPES), key=lambda r: r.id)
    by_entity: dict[int, list[ActivityRecord]] = {}
    for record in functions:
        if record.entity_id is not None:
            by_entity.setdefault(record.entity_id, []).append(record)
    ordered = sorted(entities, key=lambda entity: entity.id)
    children: dict[int, list[Entity]] = {}
    for entity in ordered:
        if entity.parent_status == ParentStatus.RESOLVED.value and entity.parent_id is not None:
            children.setdefault(entity.parent_id, []).append(entity)
    by_id = {entity.id: entity for entity in ordered}
    groups = tuple(
        Group(
            entity=by_id[parent_id],
            children=tuple(kids),
            parent_records=tuple(by_entity.get(parent_id, [])),
            child_records=tuple(record for kid in kids for record in by_entity.get(kid.id, [])),
            uncertain_entity_ids=_uncertain(parent_id, ordered),
        )
        for parent_id, kids in sorted(children.items())
    )
    clarifications = tuple(
        Clarification(record, entity, _UNCLEAR_PARENT[entity.parent_status])
        for entity in ordered
        if entity.parent_status in _UNCLEAR_PARENT
        for record in by_entity.get(entity.id, [])
    )
    excluded = tuple(record for record in functions if record.entity_id is None)
    return Structure(by_id, groups, clarifications, excluded)


def load_structure(session: Session, document_id: int) -> Structure:
    """Read the document's entities and records from the database and build the structure."""
    entities = session.scalars(select(Entity).where(Entity.document_id == document_id)).all()
    records = session.scalars(select(ActivityRecord).where(ActivityRecord.document_id == document_id)).all()
    return build_structure(entities, records)
