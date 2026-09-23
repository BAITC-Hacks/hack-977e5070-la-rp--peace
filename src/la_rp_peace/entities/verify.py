"""Code-side checks of a stage 2 answer (methodology §8): ids, document boundary, quotes, support.

Every cited node must belong to the current document and contain the quote verbatim; every
filled attribute, parent and relation must be backed by a source that says what it supports.
Problems are returned as messages for the model; nothing is applied until an answer passes.
"""

import re
from dataclasses import dataclass

from la_rp_peace.entities.answers import (
    ROLE_SUPPORT_PREFIX,
    SUPPORT_LEVEL,
    SUPPORT_NAME,
    SUPPORT_PARENT,
    SUPPORT_POSITION_TYPE,
    SUPPORT_RELATION,
    SUPPORT_SAME_ENTITY,
    SUPPORT_TYPE,
    BlockAnswer,
    ConsolidationAnswer,
    MentionIn,
    ParentIn,
    RelationIn,
    SourceIn,
    UnclearIn,
)
from la_rp_peace.enums import ParentStatus
from la_rp_peace.quotes import find_quote

REGISTRY_KEY = re.compile(r"^E\d+$")
PLAIN_SUPPORTS = frozenset(
    {
        SUPPORT_NAME,
        SUPPORT_TYPE,
        SUPPORT_PARENT,
        SUPPORT_POSITION_TYPE,
        SUPPORT_LEVEL,
        SUPPORT_RELATION,
        SUPPORT_SAME_ENTITY,
    },
)


@dataclass(frozen=True, slots=True)
class VerifiedSource:
    """A source whose quote was found in its node; ``start``/``end`` index the node text."""

    node_id: int
    quote: str
    start: int
    end: int
    supports: tuple[str, ...]


def _known_support(claim: str) -> bool:
    return claim in PLAIN_SUPPORTS or (claim.startswith(ROLE_SUPPORT_PREFIX) and len(claim) > len(ROLE_SUPPORT_PREFIX))


class SourceVerifier:
    """Resolves quotes against the node texts of one document."""

    def __init__(self, node_texts: dict[int, str]) -> None:
        """Remember the document's nodes."""
        self._texts = node_texts

    def has_node(self, node_id: int) -> bool:
        """Tell whether the node belongs to the document."""
        return node_id in self._texts

    def verify(self, source: SourceIn, owner: str, errors: list[str]) -> VerifiedSource | None:
        """Verify one source, appending a message to ``errors`` if it fails."""
        text = self._texts.get(source.node_id)
        if text is None:
            errors.append(f"{owner}: узел {source.node_id} не относится к текущему документу")
            return None
        found = find_quote(text, source.quote)
        if found is None:
            errors.append(f"{owner}: цитата «{source.quote}» не найдена дословно в узле {source.node_id}")
            return None
        start, end = found
        return VerifiedSource(source.node_id, text[start:end], start, end, tuple(dict.fromkeys(source.supports)))

    def verify_all(self, sources: list[SourceIn], owner: str, errors: list[str]) -> list[VerifiedSource]:
        """Verify a list of sources, keeping those that pass."""
        return [verified for source in sources if (verified := self.verify(source, owner, errors)) is not None]


def role_support(role: str) -> str:
    """The ``supports`` value that backs a role, e.g. ``role:аудитор``."""
    return f"{ROLE_SUPPORT_PREFIX}{role.strip()}"


def _supported(sources: list[SourceIn], claim: str) -> bool:
    wanted = claim.casefold()
    return any(wanted in {value.strip().casefold() for value in source.supports} for source in sources)


def _verify_stage2(verifier: SourceVerifier, sources: list[SourceIn], owner: str, errors: list[str]) -> None:
    """Verify quotes and restrict ``supports`` to the stage 2 vocabulary."""
    for source in sources:
        unknown = [claim for claim in source.supports if not _known_support(claim)]
        if unknown:
            errors.append(f"{owner}: недопустимые значения supports {unknown}")
    verifier.verify_all(sources, owner, errors)


class _RefScope:
    """Which references an answer may use: registry keys and its own new refs."""

    def __init__(self, registry_keys: set[str], local: set[str]) -> None:
        self.registry_keys = registry_keys
        self.local = local

    def known(self, ref: str) -> bool:
        return ref in self.registry_keys or ref in self.local


def _check_parent(owner: str, own_ref: str, parent: ParentIn, scope: _RefScope, errors: list[str]) -> None:
    """Check a parent claim; ``parent.sources`` must already include any other sources that may back it."""
    if parent.status is ParentStatus.RESOLVED:
        if parent.ref is None or not scope.known(parent.ref) or parent.ref == own_ref:
            errors.append(f"{owner}: родитель «{parent.ref}» не найден среди других объектов документа")
        if not _supported(parent.sources, SUPPORT_PARENT):
            errors.append(f"{owner}: нет источника, подтверждающего родителя (supports: parent)")
    elif parent.status is ParentStatus.ROOT:
        if not _supported(parent.sources, SUPPORT_PARENT):
            errors.append(f"{owner}: корневой объект без подтверждения (supports: parent)")
    elif parent.status is ParentStatus.AMBIGUOUS:
        candidates = set(parent.candidates)
        if len(candidates) < 2 or own_ref in candidates or not all(scope.known(ref) for ref in candidates):
            errors.append(f"{owner}: для неоднозначного родителя нужны минимум два других известных кандидата")
    if parent.status is not ParentStatus.RESOLVED and parent.ref is not None:
        errors.append(f"{owner}: ref родителя указывается только при статусе resolved")


def _check_mention(mention: MentionIn, scope: _RefScope, verifier: SourceVerifier, errors: list[str]) -> None:
    owner = f"{mention.ref} «{mention.name}»"
    if REGISTRY_KEY.match(mention.ref) and mention.ref not in scope.registry_keys:
        errors.append(f"{owner}: объекта {mention.ref} нет в реестре документа")
    required = [(SUPPORT_NAME, True), (SUPPORT_TYPE, True)]
    required += [(SUPPORT_POSITION_TYPE, mention.position_type is not None), (SUPPORT_LEVEL, mention.level is not None)]
    for claim, needed in required:
        if needed and not _supported(mention.sources, claim):
            errors.append(f"{owner}: признак «{claim}» не подтверждён источником (supports: {claim})")
    backing = mention.parent.model_copy(update={"sources": mention.parent.sources + mention.sources})
    _check_parent(owner, mention.ref, backing, scope, errors)
    _verify_stage2(verifier, mention.sources + mention.parent.sources, owner, errors)
    for role in mention.roles:
        role_owner = f"{owner} роль «{role.role}»"
        if not _supported(role.sources, role_support(role.role)):
            errors.append(f"{role_owner}: нет источника роли (supports: {role_support(role.role)})")
        _verify_stage2(verifier, role.sources, role_owner, errors)


def _check_relation(relation: RelationIn, scope: _RefScope, verifier: SourceVerifier, errors: list[str]) -> None:
    owner = f"связь {relation.from_ref}→{relation.to_ref}"
    ends_known = scope.known(relation.from_ref) and scope.known(relation.to_ref)
    if not ends_known or relation.from_ref == relation.to_ref:
        errors.append(f"{owner}: концы связи должны быть разными известными объектами")
    if not _supported(relation.sources, SUPPORT_RELATION):
        errors.append(f"{owner}: нет источника связи (supports: relation)")
    _verify_stage2(verifier, relation.sources, owner, errors)


def _check_unclear(unclear: list[UnclearIn], scope: _RefScope, verifier: SourceVerifier, errors: list[str]) -> None:
    for item in unclear:
        errors += [
            f"замечание: узел {node} не относится к документу" for node in item.node_ids if not verifier.has_node(node)
        ]
        errors += [f"замечание: объект {ref} неизвестен" for ref in item.refs if not scope.known(ref)]


def _check_status(answer: BlockAnswer, errors: list[str]) -> None:
    if answer.block_status == "none" and (answer.mentions or answer.relations):
        errors.append("block_status «none», но объекты или связи перечислены")
    if answer.block_status == "found" and not (answer.mentions or answer.relations):
        errors.append("block_status «found», но объектов нет — используйте «none»")
    if answer.block_status == "needs_clarification" and not answer.unclear:
        errors.append("block_status «needs_clarification» требует хотя бы одного пункта unclear")


def check_block_answer(answer: BlockAnswer, verifier: SourceVerifier, registry_keys: set[str]) -> list[str]:
    """Check one block answer.

    Args:
        answer: Parsed answer.
        verifier: Quote resolver of the current document.
        registry_keys: Keys of entities already registered for the document.

    Returns:
        Problems for the model; empty if the answer can be applied.
    """
    errors: list[str] = []
    refs = [mention.ref for mention in answer.mentions]
    if len(refs) != len(set(refs)):
        errors.append("каждый ref может встречаться в mentions только один раз")
    local = {ref for ref in refs if not REGISTRY_KEY.match(ref)}
    scope = _RefScope(registry_keys, local)
    for mention in answer.mentions:
        _check_mention(mention, scope, verifier, errors)
    for relation in answer.relations:
        _check_relation(relation, scope, verifier, errors)
    _check_unclear(answer.unclear, scope, verifier, errors)
    _check_status(answer, errors)
    return errors


def check_consolidation(answer: ConsolidationAnswer, verifier: SourceVerifier, registry_keys: set[str]) -> list[str]:
    """Check the whole-document review answer against the registry and the text.

    Args:
        answer: Parsed answer.
        verifier: Quote resolver of the current document.
        registry_keys: Keys of the registered entities.

    Returns:
        Problems for the model; empty if the answer can be applied.
    """
    errors: list[str] = []
    scope = _RefScope(registry_keys, set())
    merged = [merge.merge for merge in answer.merges]
    if len(merged) != len(set(merged)):
        errors.append("один объект нельзя объединять с несколькими объектами")
    for merge in answer.merges:
        owner = f"объединение {merge.merge}→{merge.keep}"
        if merge.keep == merge.merge or not (scope.known(merge.keep) and scope.known(merge.merge)):
            errors.append(f"{owner}: нужны два разных объекта из реестра")
        if not _supported(merge.sources, SUPPORT_SAME_ENTITY):
            errors.append(f"{owner}: нет источника, что это один объект (supports: same_entity)")
        _verify_stage2(verifier, merge.sources, owner, errors)
    for update in answer.parent_updates:
        owner = f"родитель {update.entity}"
        if not scope.known(update.entity):
            errors.append(f"{owner}: объекта нет в реестре")
        parent = ParentIn(ref=update.parent, status=update.status, candidates=update.candidates, sources=update.sources)
        _check_parent(owner, update.entity, parent, scope, errors)
        _verify_stage2(verifier, update.sources, owner, errors)
    _check_unclear(answer.unresolved, scope, verifier, errors)
    return errors
