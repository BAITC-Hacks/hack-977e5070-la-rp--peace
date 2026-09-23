"""Code-side checks of a stage 2 answer (methodology §8): ids, document boundary, quotes, support.

Every cited node must belong to the current document and contain the quote verbatim; every
filled attribute, parent and relation must be backed by a source that says what it supports.
Problems are returned as messages for the model; nothing is applied until an answer passes.
"""

import re
from dataclasses import dataclass

from la_rp_peace.entities.answers import (
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
    SourceIn,
)
from la_rp_peace.enums import ParentStatus
from la_rp_peace.quotes import find_quote

REGISTRY_KEY = re.compile(r"^E\d+$")


@dataclass(frozen=True, slots=True)
class VerifiedSource:
    """A source whose quote was found in its node; ``start``/``end`` index the node text."""

    node_id: int
    quote: str
    start: int
    end: int
    supports: tuple[str, ...]


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
            errors.append(f"{owner}: цитата «{source.quote}» не найдена в узле {source.node_id}")
            return None
        start, end = found
        return VerifiedSource(source.node_id, text[start:end], start, end, tuple(source.supports))

    def verify_all(self, sources: list[SourceIn], owner: str, errors: list[str]) -> list[VerifiedSource]:
        """Verify a list of sources, keeping those that pass."""
        return [verified for source in sources if (verified := self.verify(source, owner, errors)) is not None]


def _supported(sources: list[SourceIn], claim: str) -> bool:
    return any(claim in source.supports for source in sources)


class _RefScope:
    """Which references an answer may use: registry keys and its own new refs."""

    def __init__(self, registry_keys: set[str], local: set[str]) -> None:
        self.registry_keys = registry_keys
        self.local = local

    def known(self, ref: str) -> bool:
        return ref in self.registry_keys or ref in self.local


def _check_parent(owner: str, own_ref: str, parent: ParentIn, scope: _RefScope, errors: list[str]) -> None:
    if parent.status is ParentStatus.RESOLVED:
        if parent.ref is None or not scope.known(parent.ref) or parent.ref == own_ref:
            errors.append(f"{owner}: родитель «{parent.ref}» не найден среди объектов документа")
        if not _supported(parent.sources, SUPPORT_PARENT):
            errors.append(f"{owner}: нет источника, подтверждающего родителя (supports: parent)")
    elif parent.status is ParentStatus.ROOT:
        if not _supported(parent.sources, SUPPORT_PARENT):
            errors.append(f"{owner}: корневой объект без подтверждения (supports: parent)")
    elif parent.status is ParentStatus.AMBIGUOUS:
        if len(parent.candidates) < 2 or not all(scope.known(ref) for ref in parent.candidates):
            errors.append(f"{owner}: для неоднозначного родителя нужны минимум два известных кандидата")
    if parent.status is not ParentStatus.RESOLVED and parent.ref is not None:
        errors.append(f"{owner}: ref родителя указывается только при статусе resolved")


def _check_mention(mention: MentionIn, scope: _RefScope, errors: list[str]) -> None:
    owner = f"{mention.ref} «{mention.name}»"
    if REGISTRY_KEY.match(mention.ref) and mention.ref not in scope.registry_keys:
        errors.append(f"{owner}: объекта {mention.ref} нет в реестре документа")
    required = [(SUPPORT_NAME, True), (SUPPORT_TYPE, True)]
    required += [(SUPPORT_POSITION_TYPE, mention.position_type is not None), (SUPPORT_LEVEL, mention.level is not None)]
    for claim, needed in required:
        if needed and not _supported(mention.sources, claim):
            errors.append(f"{owner}: признак «{claim}» не подтверждён источником (supports: {claim})")
    _check_parent(owner, mention.ref, mention.parent, scope, errors)


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
    local = [mention.ref for mention in answer.mentions if not REGISTRY_KEY.match(mention.ref)]
    if len(local) != len(set(local)):
        errors.append("ref новых объектов должны быть уникальны в ответе")
    scope = _RefScope(registry_keys, set(local))
    for mention in answer.mentions:
        _check_mention(mention, scope, errors)
        verifier.verify_all(mention.sources + mention.parent.sources, mention.ref, errors)
        for role in mention.roles:
            verifier.verify_all(role.sources, f"{mention.ref} роль «{role.role}»", errors)
    for relation in answer.relations:
        owner = f"связь {relation.from_ref}→{relation.to_ref}"
        if (
            not (scope.known(relation.from_ref) and scope.known(relation.to_ref))
            or relation.from_ref == relation.to_ref
        ):
            errors.append(f"{owner}: концы связи должны быть разными известными объектами")
        if not _supported(relation.sources, SUPPORT_RELATION):
            errors.append(f"{owner}: нет источника связи (supports: relation)")
        verifier.verify_all(relation.sources, owner, errors)
    for unclear in answer.unclear:
        errors += [
            f"замечание: узел {node} не относится к документу"
            for node in unclear.node_ids
            if not verifier.has_node(node)
        ]
    if answer.block_status == "none" and answer.mentions:
        errors.append("block_status «none», но объекты перечислены")
    return errors


def check_consolidation(answer: ConsolidationAnswer, verifier: SourceVerifier, registry_keys: set[str]) -> list[str]:
    """Check the whole-document review answer against the registry and the text."""
    errors: list[str] = []
    scope = _RefScope(registry_keys, set())
    for merge in answer.merges:
        owner = f"объединение {merge.merge}→{merge.keep}"
        if merge.keep == merge.merge or not (scope.known(merge.keep) and scope.known(merge.merge)):
            errors.append(f"{owner}: нужны два разных объекта из реестра")
        if not _supported(merge.sources, SUPPORT_SAME_ENTITY):
            errors.append(f"{owner}: нет источника, что это один объект (supports: same_entity)")
        verifier.verify_all(merge.sources, owner, errors)
    for update in answer.parent_updates:
        owner = f"родитель {update.entity}"
        if not scope.known(update.entity):
            errors.append(f"{owner}: объекта нет в реестре")
        parent = ParentIn(ref=update.parent, status=update.status, candidates=update.candidates, sources=update.sources)
        _check_parent(owner, update.entity, parent, scope, errors)
        verifier.verify_all(update.sources, owner, errors)
    return errors
