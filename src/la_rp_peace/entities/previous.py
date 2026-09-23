"""The stored stage 2 result of a document, as the starting point of a re-run (methodology §4).

A re-run replaces each block's previous contribution with its new, verified answer. What the
previous run stored is still needed for two things: a block that fails in the re-run keeps
its previous contribution (a failed attempt never overwrites a result), and unchanged objects
keep their ids so that later-stage records referencing ``entities.id`` stay valid. Identity
is decided conservatively: a shared name or alias, the same type, the same parent — and the
match must be unique in both directions, otherwise the object gets a new id.
"""

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.enums import ParentStatus, RelationType
from la_rp_peace.models import Entity, EntityRelation, EntitySource


@dataclass(frozen=True, slots=True)
class PreviousSource:
    """A stored source and the block (root node id) whose answer produced it."""

    node_id: int
    quote: str
    supports: tuple[str, ...]
    block: int | None


@dataclass(slots=True)
class PreviousEntity:
    """A stored entity; ids are database ids."""

    id: int
    name: str
    aliases: list[str]
    entity_type: str
    position_type: str | None
    level: str | None
    roles: list[dict[str, str | None]]
    parent_id: int | None
    parent_status: ParentStatus
    candidates: list[int]
    sources: list[PreviousSource] = field(default_factory=list)

    def names(self) -> set[str]:
        """Normalised name and aliases."""
        return {normalise(value) for value in [self.name, *self.aliases]}


@dataclass(slots=True)
class PreviousRelation:
    """A stored relation; ids are database ids."""

    id: int
    from_id: int
    to_id: int
    relation_type: RelationType
    conditions: str | None
    sources: list[PreviousSource] = field(default_factory=list)


@dataclass(slots=True)
class PreviousResult:
    """Everything stage 2 stored for one document."""

    entities: dict[int, PreviousEntity] = field(default_factory=dict)
    relations: list[PreviousRelation] = field(default_factory=list)

    def entities_of_block(self, block: int) -> list[PreviousEntity]:
        """Entities that the block's previous answer contributed sources to."""
        return [entity for entity in self.entities.values() if any(s.block == block for s in entity.sources)]

    def relations_of_block(self, block: int) -> list[PreviousRelation]:
        """Relations that the block's previous answer contributed sources to."""
        return [relation for relation in self.relations if any(s.block == block for s in relation.sources)]


def normalise(value: str) -> str:
    """Case- and whitespace-insensitive form of a name."""
    return " ".join(value.split()).casefold()


def same_identity(names: set[str], entity_type: str, parent_id: int | None, previous: PreviousEntity) -> bool:
    """Tell whether an entity of this run may be the stored one: shared name, same type and parent.

    Args:
        names: Normalised name and aliases of the entity.
        entity_type: Its type.
        parent_id: Previous id of its parent (None without a parent, or a parent new in this run).
        previous: The stored entity.
    """
    same_type = normalise(entity_type) == normalise(previous.entity_type)
    return same_type and parent_id == previous.parent_id and bool(names & previous.names())


def _source(row: EntitySource) -> PreviousSource:
    return PreviousSource(row.node_id, row.quote, tuple(json.loads(row.supports)), row.block_node_id)


def load_previous(session: Session, document_id: int) -> PreviousResult:
    """Read the document's stored stage 2 result.

    Args:
        session: Database session.
        document_id: The document.

    Returns:
        Stored entities and relations with their sources; empty before the first run.
    """
    result = PreviousResult()
    for row in session.scalars(select(Entity).where(Entity.document_id == document_id).order_by(Entity.id)):
        result.entities[row.id] = PreviousEntity(
            id=row.id,
            name=row.name,
            aliases=json.loads(row.aliases),
            entity_type=row.entity_type,
            position_type=row.position_type,
            level=row.level,
            roles=json.loads(row.roles),
            parent_id=row.parent_id,
            parent_status=ParentStatus(row.parent_status),
            candidates=json.loads(row.parent_candidates),
        )
    relations: dict[int, PreviousRelation] = {}
    query = select(EntityRelation).where(EntityRelation.document_id == document_id).order_by(EntityRelation.id)
    for link in session.scalars(query):
        relations[link.id] = PreviousRelation(
            link.id, link.from_entity_id, link.to_entity_id, RelationType(link.relation_type), link.conditions
        )
    result.relations = list(relations.values())
    query_sources = select(EntitySource).where(EntitySource.document_id == document_id).order_by(EntitySource.id)
    for source in session.scalars(query_sources):
        if source.entity_id is not None and source.entity_id in result.entities:
            result.entities[source.entity_id].sources.append(_source(source))
        elif source.relation_id is not None and source.relation_id in relations:
            relations[source.relation_id].sources.append(_source(source))
    return result
