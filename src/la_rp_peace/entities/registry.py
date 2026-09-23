"""The document's registry of organisational objects, built block by block (methodology §4–§5).

Only verified answers reach the registry. A mention that references ``E<n>`` updates that
entity (new sources, aliases, empty attributes); a new ``ref`` always creates a new entity —
equal names are never merged by themselves. A second, different, sourced parent makes the
parent ``ambiguous`` rather than silently replacing it, and a parent that would close a
cycle is refused. Merges come only from the whole-document review, each with its evidence.
"""

from dataclasses import dataclass, field

from la_rp_peace.entities.answers import (
    SUPPORT_PARENT,
    BlockAnswer,
    ConsolidationAnswer,
    MentionIn,
    ParentIn,
    ParentUpdateIn,
    SourceIn,
    UnclearIn,
)
from la_rp_peace.entities.verify import REGISTRY_KEY, SourceVerifier, VerifiedSource
from la_rp_peace.enums import EntityIssueType, ParentStatus, RelationType

_PARENT_WORDS = {
    ParentStatus.ROOT: "корневой объект",
    ParentStatus.UNKNOWN: "не установлен",
}


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
    """A stage 2 problem; ``entity`` is a registry key, ``relation`` an index into ``Registry.relations``."""

    issue_type: EntityIssueType
    message: str
    is_blocking: bool = False
    entity: str | None = None
    relation: int | None = None


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
        self._merged: dict[str, str] = {}

    # -- bookkeeping -------------------------------------------------------------------

    def _new_key(self) -> str:
        # Keys are never reused, even after merges remove entities.
        self._allocated += 1
        return f"E{self._allocated}"

    def canonical(self, key: str) -> str:
        """The key an entity is known under after merges."""
        while key in self._merged:
            key = self._merged[key]
        return key

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
        while current is not None and current not in chain and current in self.entities:
            chain.append(current)
            current = self.entities[current].parent
        return chain

    def add_issue(self, issue: RegistryIssue) -> None:
        """Record a problem unless the same one is already recorded."""
        if issue not in self.issues:
            self.issues.append(issue)

    def parent_text(self, entity: RegisteredEntity) -> str:
        """The parent as shown to the model: key and name, candidates, or status."""
        if entity.parent is not None:
            return f"{entity.parent} «{self.entities[entity.parent].name}»"
        if entity.parent_status is ParentStatus.AMBIGUOUS:
            return f"неоднозначен ({', '.join(entity.candidates)})"
        return _PARENT_WORDS[entity.parent_status]

    def summary(self) -> str:
        """The registry as shown to the model: one line per entity."""
        lines = []
        for entity in self.entities.values():
            aliases = f" (также: {'; '.join(entity.aliases)})" if entity.aliases else ""
            parent = self.parent_text(entity)
            lines.append(f"{entity.key}: {entity.name}{aliases} — {entity.entity_type}; родитель: {parent}")
        return "\n".join(lines) or "(пока пусто)"

    def has_parent_source(self, key: str) -> bool:
        """Tell whether any source of the entity supports its parent (or root status)."""
        return any(SUPPORT_PARENT in source.supports for source in self.entities[key].sources)

    # -- parents -----------------------------------------------------------------------

    def _would_cycle(self, key: str, target: str) -> bool:
        return target == key or key in self.ancestors(target)

    def _set_parent(self, key: str, parent: ParentIn, resolve: dict[str, str]) -> None:
        entity = self.entities[key]
        entity.sources += self._sources(parent.sources, f"{key} родитель")
        if parent.status is ParentStatus.RESOLVED and parent.ref is not None:
            self._offer_parent(entity, self.canonical(resolve.get(parent.ref, parent.ref)))
        elif parent.status is ParentStatus.AMBIGUOUS:
            candidates = [self.canonical(resolve.get(ref, ref)) for ref in parent.candidates]
            self._make_ambiguous(entity, self._options(entity) + candidates)
        elif parent.status is ParentStatus.ROOT and entity.parent_status is ParentStatus.UNKNOWN:
            entity.parent_status = ParentStatus.ROOT
        elif parent.status is ParentStatus.ROOT and entity.parent_status is not ParentStatus.ROOT:
            message = f"{key} отмечен корневым, но у него уже есть родитель или кандидаты"
            self.add_issue(RegistryIssue(EntityIssueType.OTHER, message, False, key))

    def _options(self, entity: RegisteredEntity) -> list[str]:
        """Parents the entity currently has or may have."""
        return [entity.parent] if entity.parent is not None else list(entity.candidates)

    def _offer_parent(self, entity: RegisteredEntity, target: str) -> None:
        if entity.parent == target or target in entity.candidates:
            return
        if self._would_cycle(entity.key, target):
            message = f"Родитель {target} образует цикл принадлежности для {entity.key}"
            self.add_issue(RegistryIssue(EntityIssueType.CYCLE, message, True, entity.key))
            return
        if entity.parent_status in (ParentStatus.RESOLVED, ParentStatus.AMBIGUOUS):
            self._make_ambiguous(entity, [*self._options(entity), target])
            return
        if entity.parent_status is ParentStatus.ROOT:
            message = f"{entity.key} отмечен корневым, но найден родитель {target}"
            self.add_issue(RegistryIssue(EntityIssueType.OTHER, message, False, entity.key))
        entity.parent, entity.parent_status = target, ParentStatus.RESOLVED

    def _drop_ambiguity(self, key: str) -> None:
        self.issues = [
            issue
            for issue in self.issues
            if not (issue.issue_type is EntityIssueType.AMBIGUOUS_PARENT and issue.entity == key)
        ]

    def _make_ambiguous(self, entity: RegisteredEntity, candidates: list[str]) -> None:
        options = [option for option in dict.fromkeys(candidates) if option and option != entity.key]
        self._drop_ambiguity(entity.key)
        if not options:
            entity.parent, entity.parent_status, entity.candidates = None, ParentStatus.UNKNOWN, []
            return
        if len(options) == 1 and not self._would_cycle(entity.key, options[0]):
            entity.parent, entity.parent_status, entity.candidates = options[0], ParentStatus.RESOLVED, []
            return
        entity.parent, entity.parent_status, entity.candidates = None, ParentStatus.AMBIGUOUS, options
        message = f"Неоднозначный родитель {entity.key}: {', '.join(options) or 'нет кандидатов'}"
        self.add_issue(RegistryIssue(EntityIssueType.AMBIGUOUS_PARENT, message, False, entity.key))

    # -- applying block answers --------------------------------------------------------

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

    def _note_unclear(self, unclear: list[UnclearIn], resolve: dict[str, str]) -> None:
        for item in unclear:
            refs = [self.canonical(resolve.get(ref, ref)) for ref in item.refs]
            refs = [ref for ref in refs if ref in self.entities]
            message = item.message + (f" (объекты: {', '.join(refs)})" if len(refs) > 1 else "")
            self.add_issue(RegistryIssue(EntityIssueType.OTHER, message, False, refs[0] if refs else None))

    def apply_block(self, answer: BlockAnswer) -> None:
        """Apply a block answer that passed ``check_block_answer``."""
        resolve = {
            mention.ref: mention.ref if REGISTRY_KEY.match(mention.ref) else self._new_key()
            for mention in answer.mentions
        }
        for mention in answer.mentions:
            self._upsert(mention, resolve[mention.ref])
        for mention in answer.mentions:
            self._set_parent(resolve[mention.ref], mention.parent, resolve)
        for relation in answer.relations:
            self._add_relation(
                RegisteredRelation(
                    self.canonical(resolve.get(relation.from_ref, relation.from_ref)),
                    self.canonical(resolve.get(relation.to_ref, relation.to_ref)),
                    relation.type,
                    relation.conditions,
                    self._sources(relation.sources, "связь"),
                ),
            )
        self._note_unclear(answer.unclear, resolve)

    def _add_relation(self, relation: RegisteredRelation) -> None:
        if relation.from_key == relation.to_key:
            return
        for existing in self.relations:
            if (existing.from_key, existing.to_key, existing.relation_type) == (
                relation.from_key,
                relation.to_key,
                relation.relation_type,
            ):
                existing.sources += [source for source in relation.sources if source not in existing.sources]
                existing.conditions = existing.conditions or relation.conditions
                return
        self.relations.append(relation)

    # -- consolidation -----------------------------------------------------------------

    def apply_consolidation(self, answer: ConsolidationAnswer) -> None:
        """Apply a whole-document review that passed ``check_consolidation``: merges, then parents."""
        for merge in answer.merges:
            keep, gone = self.canonical(merge.keep), self.canonical(merge.merge)
            if keep != gone:
                self._merge(keep, gone, self._sources(merge.sources, "объединение"))
        for update in answer.parent_updates:
            self._update_parent(update)
        self._note_unclear(answer.unresolved, {})

    def _update_parent(self, update: ParentUpdateIn) -> None:
        entity = self.entities[self.canonical(update.entity)]
        target = self.canonical(update.parent) if update.parent is not None else None
        settles = (
            update.status is ParentStatus.RESOLVED
            and entity.parent_status is ParentStatus.AMBIGUOUS
            and target in entity.candidates
        )
        if settles and target is not None and not self._would_cycle(entity.key, target):
            entity.sources += self._sources(update.sources, f"{entity.key} родитель")
            entity.parent, entity.parent_status, entity.candidates = target, ParentStatus.RESOLVED, []
            self._drop_ambiguity(entity.key)
            return
        parent = ParentIn(ref=target, status=update.status, candidates=update.candidates, sources=update.sources)
        self._set_parent(entity.key, parent, {})

    def _merge(self, keep: str, merge: str, sources: list[VerifiedSource]) -> None:
        kept, gone = self.entities[keep], self.entities.pop(merge)
        self._merged[merge] = keep
        _add_unique(kept.aliases, [gone.name, *gone.aliases], kept.name)
        kept.sources += gone.sources + sources
        kept.roles += [role for role in gone.roles if role not in kept.roles]
        kept.position_type = kept.position_type or gone.position_type
        kept.level = kept.level or gone.level
        for entity in self.entities.values():
            self._repoint(entity, merge, keep)
        self._drop_ambiguity(merge)
        self._merge_parent(kept, gone)
        relations, self.relations = self.relations, []
        for relation in relations:
            relation.from_key = keep if relation.from_key == merge else relation.from_key
            relation.to_key = keep if relation.to_key == merge else relation.to_key
            self._add_relation(relation)
        self.issues = [
            RegistryIssue(
                issue.issue_type,
                issue.message,
                issue.is_blocking,
                keep if issue.entity == merge else issue.entity,
                issue.relation,
            )
            for issue in self.issues
        ]

    def _repoint(self, entity: RegisteredEntity, merge: str, keep: str) -> None:
        """Replace references to a merged entity; an entity never becomes its own parent."""
        if entity.parent == merge:
            entity.parent = keep
        if entity.parent == entity.key:
            entity.parent, entity.parent_status = None, ParentStatus.UNKNOWN
        if merge in entity.candidates or entity.key in entity.candidates:
            renamed = [keep if candidate == merge else candidate for candidate in entity.candidates]
            self._make_ambiguous(entity, renamed)

    def _merge_parent(self, kept: RegisteredEntity, gone: RegisteredEntity) -> None:
        gone_parent = None if gone.parent in (kept.key, gone.key) else gone.parent
        if gone.parent_status is ParentStatus.RESOLVED and gone_parent is not None:
            self._offer_parent(kept, gone_parent)
        elif gone.parent_status is ParentStatus.AMBIGUOUS:
            self._make_ambiguous(kept, self._options(kept) + gone.candidates)
        elif gone.parent_status is ParentStatus.ROOT and kept.parent_status is ParentStatus.UNKNOWN:
            kept.parent_status = ParentStatus.ROOT
