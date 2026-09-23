"""The document's registry of organisational objects, built block by block (methodology §4–§5).

Only verified answers reach the registry. A mention that references ``E<n>`` updates that
entity (new sources, aliases, empty attributes); a new ``ref`` always creates a new entity —
equal names are never merged by themselves. A second, different, sourced parent makes the
parent ``ambiguous`` rather than silently replacing it, and a parent that would close a
cycle is refused.
"""

from dataclasses import dataclass, field

from la_rp_peace.entities.answers import (
    SUPPORT_PARENT,
    BlockAnswer,
    ConsolidationAnswer,
    MentionIn,
    ParentIn,
    SourceIn,
)
from la_rp_peace.entities.verify import REGISTRY_KEY, SourceVerifier, VerifiedSource
from la_rp_peace.enums import EntityIssueType, ParentStatus, RelationType


@dataclass(slots=True)
class RegisteredEntity:
    """An entity of the current document."""

    key: str
    name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    position_type: str | None = None
    level: str | None = None
    roles: list[dict[str, str | None]] = field(default_factory=list)
    parent: str | None = None
    parent_status: ParentStatus = ParentStatus.UNKNOWN
    candidates: list[str] = field(default_factory=list)
    sources: list[VerifiedSource] = field(default_factory=list)


@dataclass(slots=True)
class RegisteredRelation:
    """A non-membership relation between two entities of the document."""

    from_key: str
    to_key: str
    relation_type: RelationType
    conditions: str | None
    sources: list[VerifiedSource] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RegistryIssue:
    """A stage 2 problem; ``entity`` is a registry key."""

    issue_type: EntityIssueType
    message: str
    is_blocking: bool = False
    entity: str | None = None


def _add_unique(target: list[str], values: list[str], exclude: str) -> None:
    for value in values:
        if value and value != exclude and value not in target:
            target.append(value)


class Registry:
    """All entities, relations and issues of one document."""

    def __init__(self, verifier: SourceVerifier) -> None:
        """Start empty for a document."""
        self.verifier = verifier
        self.entities: dict[str, RegisteredEntity] = {}
        self.relations: list[RegisteredRelation] = []
        self.issues: list[RegistryIssue] = []
        self._allocated = 0

    # -- bookkeeping -------------------------------------------------------------------

    def _new_key(self) -> str:
        # Keys are never reused, even after merges remove entities.
        self._allocated += 1
        return f"E{self._allocated}"

    def _sources(self, sources: list[SourceIn], owner: str) -> list[VerifiedSource]:
        errors: list[str] = []
        verified = self.verifier.verify_all(sources, owner, errors)
        if errors:
            raise ValueError("; ".join(errors))
        return verified

    def ancestors(self, key: str) -> list[str]:
        """Parent chain of an entity (nearest first), stopping at a repeat."""
        chain: list[str] = []
        current = self.entities[key].parent
        while current is not None and current not in chain:
            chain.append(current)
            current = self.entities[current].parent
        return chain

    def summary(self) -> str:
        """The registry as shown to the model: one line per entity."""
        lines = []
        for entity in self.entities.values():
            parent = entity.parent or entity.parent_status.value
            aliases = f" (также: {', '.join(entity.aliases)})" if entity.aliases else ""
            lines.append(f"{entity.key}: {entity.name}{aliases} — {entity.entity_type}; родитель: {parent}")
        return "\n".join(lines) or "(пока пусто)"

    # -- parents -----------------------------------------------------------------------

    def _set_parent(self, key: str, parent: ParentIn, resolve: dict[str, str]) -> None:
        entity = self.entities[key]
        sources = self._sources(parent.sources, f"{key} родитель")
        entity.sources += sources
        status = parent.status
        target = resolve.get(parent.ref, parent.ref) if parent.ref else None
        if status is ParentStatus.RESOLVED and target is not None:
            self._resolve_parent(entity, target)
        elif status is ParentStatus.AMBIGUOUS:
            self._make_ambiguous(entity, [resolve.get(ref, ref) for ref in parent.candidates])
        elif status is ParentStatus.ROOT and entity.parent is None:
            entity.parent_status = ParentStatus.ROOT
        elif entity.parent is None and entity.parent_status is ParentStatus.UNKNOWN:
            entity.parent_status = status

    def _resolve_parent(self, entity: RegisteredEntity, target: str) -> None:
        if entity.parent == target:
            return
        if entity.parent is not None or entity.parent_status is ParentStatus.AMBIGUOUS:
            self._make_ambiguous(entity, [*(entity.candidates or [entity.parent or ""]), target])
            return
        if target == entity.key or entity.key in self.ancestors(target):
            self.issues.append(
                RegistryIssue(
                    EntityIssueType.CYCLE, f"Родитель {target} образует цикл для {entity.key}", True, entity.key
                ),
            )
            return
        entity.parent, entity.parent_status = target, ParentStatus.RESOLVED

    def _make_ambiguous(self, entity: RegisteredEntity, candidates: list[str]) -> None:
        options = [candidate for candidate in dict.fromkeys(candidates) if candidate]
        entity.parent, entity.parent_status, entity.candidates = None, ParentStatus.AMBIGUOUS, options
        message = f"Неоднозначный родитель {entity.key} «{entity.name}»: {', '.join(options)}"
        self.issues.append(RegistryIssue(EntityIssueType.AMBIGUOUS_PARENT, message, False, entity.key))

    # -- applying answers ----------------------------------------------------------------

    def _upsert(self, mention: MentionIn, key: str) -> None:
        sources = self._sources(mention.sources, key)
        roles = [{"role": role.role, "scope": role.scope} for role in mention.roles]
        role_sources = [s for role in mention.roles for s in self._sources(role.sources, f"{key} роль")]
        entity = self.entities.get(key)
        if entity is None:
            entity = RegisteredEntity(key, mention.name, mention.type)
            self.entities[key] = entity
        _add_unique(entity.aliases, [mention.name, *mention.aliases], entity.name)
        entity.position_type = entity.position_type or mention.position_type
        entity.level = entity.level or mention.level
        entity.roles += [role for role in roles if role not in entity.roles]
        entity.sources += sources + role_sources

    def apply_block(self, answer: BlockAnswer) -> None:
        """Apply a verified block answer."""
        resolve = {
            mention.ref: mention.ref if REGISTRY_KEY.match(mention.ref) else self._new_key()
            for mention in answer.mentions
        }
        for mention in answer.mentions:
            self._upsert(mention, resolve[mention.ref])
        for mention in answer.mentions:
            self._set_parent(resolve[mention.ref], mention.parent, resolve)
        for relation in answer.relations:
            sources = self._sources(relation.sources, "связь")
            self._add_relation(
                resolve.get(relation.from_ref, relation.from_ref),
                resolve.get(relation.to_ref, relation.to_ref),
                relation.type,
                relation.conditions,
                sources,
            )
        for unclear in answer.unclear:
            refs = [resolve.get(ref, ref) for ref in unclear.refs if resolve.get(ref, ref) in self.entities]
            self.issues.append(RegistryIssue(EntityIssueType.OTHER, unclear.message, False, refs[0] if refs else None))

    def _add_relation(
        self,
        from_key: str,
        to_key: str,
        relation_type: RelationType,
        conditions: str | None,
        sources: list[VerifiedSource],
    ) -> None:
        for existing in self.relations:
            if (existing.from_key, existing.to_key, existing.relation_type) == (from_key, to_key, relation_type):
                existing.sources += sources
                existing.conditions = existing.conditions or conditions
                return
        self.relations.append(RegisteredRelation(from_key, to_key, relation_type, conditions, sources))

    # -- consolidation -----------------------------------------------------------------

    def apply_consolidation(self, answer: ConsolidationAnswer) -> None:
        """Apply a verified whole-document review: merges first, then parent corrections."""
        for merge in answer.merges:
            if merge.keep in self.entities and merge.merge in self.entities:
                self._merge(merge.keep, merge.merge, self._sources(merge.sources, "объединение"))
        for update in answer.parent_updates:
            if update.entity not in self.entities:
                continue
            parent = ParentIn(
                ref=update.parent, status=update.status, candidates=update.candidates, sources=update.sources
            )
            entity = self.entities[update.entity]
            if update.status is ParentStatus.RESOLVED and entity.parent_status is not ParentStatus.RESOLVED:
                entity.parent, entity.parent_status = None, ParentStatus.UNKNOWN
            self._set_parent(update.entity, parent, {})
        for unresolved in answer.unresolved:
            refs = [ref for ref in unresolved.refs if ref in self.entities]
            self.issues.append(
                RegistryIssue(EntityIssueType.OTHER, unresolved.message, False, refs[0] if refs else None)
            )

    def _merge(self, keep: str, merge: str, sources: list[VerifiedSource]) -> None:
        kept, gone = self.entities[keep], self.entities.pop(merge)
        _add_unique(kept.aliases, [gone.name, *gone.aliases], kept.name)
        kept.sources += gone.sources + sources
        kept.roles += [role for role in gone.roles if role not in kept.roles]
        kept.position_type = kept.position_type or gone.position_type
        kept.level = kept.level or gone.level
        if gone.parent is not None and gone.parent != kept.parent and gone.parent != keep:
            if kept.parent is None and kept.parent_status is ParentStatus.UNKNOWN:
                kept.parent, kept.parent_status = gone.parent, ParentStatus.RESOLVED
            elif kept.parent is not None:
                self._make_ambiguous(kept, [kept.parent, gone.parent])
        for entity in self.entities.values():
            if entity.parent == merge:
                entity.parent = keep
            entity.candidates = [keep if candidate == merge else candidate for candidate in entity.candidates]
        for relation in self.relations:
            relation.from_key = keep if relation.from_key == merge else relation.from_key
            relation.to_key = keep if relation.to_key == merge else relation.to_key
        self.relations = [relation for relation in self.relations if relation.from_key != relation.to_key]
        self.issues = [
            RegistryIssue(
                issue.issue_type, issue.message, issue.is_blocking, keep if issue.entity == merge else issue.entity
            )
            for issue in self.issues
        ]

    def has_parent_source(self, key: str) -> bool:
        """Tell whether any source of the entity supports its parent (or root status)."""
        return any(SUPPORT_PARENT in source.supports for source in self.entities[key].sources)
