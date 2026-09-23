"""Compared sides of stage 4.1 (methodology 4.1 §2–§3).

A *side* is one assignment of work: a stage 3 record of type function or duty with a known
entity, or a consolidated view of a joint assignment. Records with participation ``joint`` that
share a ``provision_key`` (one provision split per participant by stage 3) become ONE view that
keeps all participants, their parents and categories, the source record ids, conditions and
sources; ``each``, ``alternative`` and ``unclear`` participation is never consolidated. Goals,
tasks, rights and prohibitions of the same entities are context for the verification only.
"""

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from la_rp_peace.embeddings import ActivityText, activity_text
from la_rp_peace.enums import ActivityType, CollisionSideKind, ParentStatus, Participation
from la_rp_peace.models import ActivityRecord, ActivitySource, Entity

COMPARED_TYPES = frozenset({ActivityType.FUNCTION.value, ActivityType.DUTY.value})
CONTEXT_TYPES = frozenset(
    {ActivityType.GOAL.value, ActivityType.TASK.value, ActivityType.RIGHT.value, ActivityType.PROHIBITION.value},
)


@dataclass(frozen=True, slots=True)
class Party:
    """An entity taking part in a side; ``parent_id`` only when the parent is resolved."""

    entity_id: int
    name: str
    entity_type: str
    category: str
    parent_id: int | None
    parent_name: str | None


@dataclass(frozen=True, slots=True)
class SideSource:
    """A stage 3 source of a side's record."""

    record_id: int
    node_id: int
    quote: str
    supports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextItem:
    """A goal, task, right or prohibition of an entity: context, never compared."""

    record_id: int
    entity_id: int
    record_type: str
    formulation: str


@dataclass(frozen=True, slots=True)
class Side:
    """One compared assignment: a record (``R<id>``) or a joint view (``V<provision_key>``)."""

    key: str
    kind: CollisionSideKind
    provision_key: str
    record_ids: tuple[int, ...]
    parties: tuple[Party, ...]
    record_type: str
    formulation: str
    specificity: str
    participation: str
    participant_designation: str
    conditions: tuple[str, ...]
    deadlines: tuple[str, ...]
    periodicities: tuple[str, ...]
    sources: tuple[SideSource, ...]

    @property
    def entity_ids(self) -> frozenset[int]:
        """Ids of the side's participants."""
        return frozenset(party.entity_id for party in self.parties)

    @property
    def source_nodes(self) -> frozenset[int]:
        """Nodes cited by the side's stage 3 sources."""
        return frozenset(source.node_id for source in self.sources)

    @property
    def parent_ids(self) -> tuple[int, ...]:
        """Resolved parents of the participants, in order, without repeats."""
        return tuple(dict.fromkeys(party.parent_id for party in self.parties if party.parent_id is not None))

    @property
    def categories(self) -> tuple[str, ...]:
        """Categories of the participants, in order, without repeats."""
        return tuple(dict.fromkeys(party.category for party in self.parties))

    def text(self) -> str:
        """The embedded text (format ``TEXT_FORMAT``)."""
        names = "; ".join(party.name for party in self.parties)
        participants = self.participant_designation
        if self.kind is CollisionSideKind.VIEW:
            participants = f"{names} (совместно; в документе: {self.participant_designation})"
        return activity_text(
            ActivityText(
                entity=names,
                category=", ".join(self.categories),
                record_type=self.record_type,
                formulation=self.formulation,
                participation=self.participation,
                participants=participants,
                condition=_joined(self.conditions),
                deadline=_joined(self.deadlines),
                periodicity=_joined(self.periodicities),
            ),
        )


@dataclass(frozen=True, slots=True)
class Inputs:
    """Everything stage 4.1 compares and shows, read from stages 2 and 3."""

    sides: tuple[Side, ...]
    context: dict[int, tuple[ContextItem, ...]]
    entities: dict[int, Party]

    @property
    def context_count(self) -> int:
        """Number of context records of the compared entities."""
        return sum(len(items) for items in self.context.values())

    def context_of(self, side: Side) -> list[ContextItem]:
        """Context records of the side's participants."""
        return [item for party in side.parties for item in self.context.get(party.entity_id, ())]


def _joined(values: tuple[str, ...]) -> str | None:
    return "; ".join(values) if values else None


def _distinct(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def parties(entities: Sequence[Entity]) -> dict[int, Party]:
    """Describe every entity of the document as a possible participant."""
    names = {entity.id: entity.name for entity in entities}
    result: dict[int, Party] = {}
    for entity in entities:
        resolved = entity.parent_status == ParentStatus.RESOLVED.value and entity.parent_id is not None
        parent_id = entity.parent_id if resolved else None
        parent_name = names.get(parent_id) if parent_id is not None else None
        result[entity.id] = Party(entity.id, entity.name, entity.entity_type, entity.category, parent_id, parent_name)
    return result


def _side(
    key: str,
    kind: CollisionSideKind,
    records: Sequence[ActivityRecord],
    known: dict[int, Party],
    sources: dict[int, list[SideSource]],
) -> Side:
    first = records[0]
    return Side(
        key=key,
        kind=kind,
        provision_key=first.provision_key,
        record_ids=tuple(record.id for record in records),
        parties=tuple(known[record.entity_id] for record in records if record.entity_id is not None),
        record_type=first.record_type,
        formulation=first.formulation,
        specificity=", ".join(_distinct(record.specificity for record in records)),
        participation=first.participation,
        participant_designation=first.participant_designation,
        conditions=_distinct(record.condition for record in records),
        deadlines=_distinct(record.deadline for record in records),
        periodicities=_distinct(record.periodicity for record in records),
        sources=tuple(source for record in records for source in sources.get(record.id, [])),
    )


def _source_index(sources: Sequence[ActivitySource]) -> dict[int, list[SideSource]]:
    index: dict[int, list[SideSource]] = defaultdict(list)
    for source in sources:
        supports = tuple(json.loads(source.supports))
        index[source.record_id].append(SideSource(source.record_id, source.node_id, source.quote, supports))
    return index


def build_inputs(
    records: Sequence[ActivityRecord],
    entities: Sequence[Entity],
    sources: Sequence[ActivitySource],
) -> Inputs:
    """Build the compared sides and their context.

    Args:
        records: Stage 3 records of the document.
        entities: Stage 2 entities of the document.
        sources: Stage 3 sources of the document.

    Returns:
        Record sides (``R<id>``) for function/duty records with a known entity and non-joint
        participation, one view side (``V<provision_key>``) per joint provision, and context.
    """
    known = parties(entities)
    by_source = _source_index(sources)
    compared = [r for r in records if r.entity_id in known and r.record_type in COMPARED_TYPES]
    joint: dict[str, list[ActivityRecord]] = defaultdict(list)
    sides: list[Side] = []
    for record in sorted(compared, key=lambda item: item.id):
        if record.participation == Participation.JOINT.value:
            joint[record.provision_key].append(record)
        else:
            sides.append(_side(f"R{record.id}", CollisionSideKind.RECORD, [record], known, by_source))
    sides += [_side(f"V{key}", CollisionSideKind.VIEW, group, known, by_source) for key, group in joint.items()]
    compared_entities = {party.entity_id for side in sides for party in side.parties}
    context: dict[int, list[ContextItem]] = defaultdict(list)
    for record in sorted(records, key=lambda item: item.id):
        entity_id = record.entity_id
        if entity_id is not None and entity_id in compared_entities and record.record_type in CONTEXT_TYPES:
            context[entity_id].append(ContextItem(record.id, entity_id, record.record_type, record.formulation))
    return Inputs(tuple(sides), {key: tuple(items) for key, items in context.items()}, known)
