"""Final checks of a document's registry before it is saved (methodology §8).

Code checks what code can: every planned block has a mark and failures are not hidden,
parents exist in the same registry without self-references or cycles, every filled
attribute and every relation keeps a source that supports it, and a root or a resolved
parent without such a source falls back to ``unknown``. Whatever is left open is an issue;
an entity with an open issue needs review, and so does the document if any issue is
blocking or any block failed. Passing these checks is not a human confirmation.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from la_rp_peace.entities.answers import (
    SUPPORT_CATEGORY,
    SUPPORT_LEVEL,
    SUPPORT_NAME,
    SUPPORT_POSITION_TYPE,
    SUPPORT_RELATION,
)
from la_rp_peace.entities.blocks import Block
from la_rp_peace.entities.extract import BlockMark, block_path
from la_rp_peace.entities.registry import RegisteredEntity, Registry, RegistryIssue
from la_rp_peace.entities.verify import UNSOURCED, VerifiedSource, role_support
from la_rp_peace.enums import (
    BlockStatus,
    EntitiesStatus,
    EntityCategory,
    EntityIssueType,
    ParentStatus,
    ReviewStatus,
)


@dataclass(frozen=True, slots=True)
class StageReport:
    """Review status per entity key and the document's stage 2 status."""

    review: dict[str, ReviewStatus]
    status: EntitiesStatus


def _supports(sources: list[VerifiedSource], claim: str) -> bool:
    wanted = claim.casefold()
    return any(wanted in {value.casefold() for value in source.supports} for source in sources)


def _issue(registry: Registry, issue_type: EntityIssueType, message: str, blocking: bool, key: str) -> None:
    registry.add_issue(RegistryIssue(issue_type, message, blocking, key))


def _unset_parent(entity: RegisteredEntity) -> None:
    entity.parent, entity.parent_status, entity.candidates = None, ParentStatus.UNKNOWN, []


def _check_parent_links(registry: Registry) -> None:
    """Parents and candidates exist in this registry; no entity is its own ancestor."""
    for key, entity in registry.entities.items():
        entity.candidates = [candidate for candidate in entity.candidates if candidate in registry.entities]
        if entity.parent is not None and entity.parent not in registry.entities:
            _issue(registry, EntityIssueType.OTHER, f"Родитель {entity.parent} объекта {key} не найден", True, key)
            _unset_parent(entity)
    for key, entity in registry.entities.items():
        seen = {key}
        current = entity.parent
        while current is not None:
            if current in seen:
                _issue(registry, EntityIssueType.CYCLE, f"Цикл принадлежности через {key}; родитель снят", True, key)
                _unset_parent(entity)
                break
            seen.add(current)
            current = registry.entities[current].parent


def _check_parent_source(registry: Registry, key: str, entity: RegisteredEntity) -> None:
    if entity.parent_status not in (ParentStatus.ROOT, ParentStatus.RESOLVED) or registry.has_parent_source(key):
        return
    word = "корневой" if entity.parent_status is ParentStatus.ROOT else f"родитель {entity.parent}"
    message = f"{key}: статус «{word}» без источника (supports: parent) — принадлежность не установлена"
    _issue(registry, EntityIssueType.UNSUPPORTED_ATTRIBUTE, message, False, key)
    _unset_parent(entity)


def _check_attributes(registry: Registry, key: str, entity: RegisteredEntity) -> None:
    if not _supports(entity.sources, SUPPORT_NAME):
        message = f"{key} «{entity.name}»: нет источника названия (supports: name)"
        _issue(registry, EntityIssueType.UNSUPPORTED_ATTRIBUTE, message, True, key)
    if entity.position_type is not None and not _supports(entity.sources, SUPPORT_POSITION_TYPE):
        _issue(registry, EntityIssueType.UNSUPPORTED_ATTRIBUTE, f"{key}: тип позиции без источника снят", False, key)
        entity.position_type = None
    if entity.level is not None and not _supports(entity.sources, SUPPORT_LEVEL):
        _issue(registry, EntityIssueType.UNSUPPORTED_ATTRIBUTE, f"{key}: уровень без источника снят", False, key)
        entity.level = None
    kept = [role for role in entity.roles if _supports(entity.sources, role_support(role["role"] or ""))]
    if len(kept) != len(entity.roles):
        _issue(registry, EntityIssueType.UNSUPPORTED_ATTRIBUTE, f"{key}: роли без источника сняты", False, key)
        entity.roles = kept
    _check_category(registry, key, entity)
    _check_parent_source(registry, key, entity)


def _check_category(registry: Registry, key: str, entity: RegisteredEntity) -> None:
    """A stated category keeps a source; an unclear one is left for the responsible employee."""
    if entity.category not in UNSOURCED and not _supports(entity.sources, SUPPORT_CATEGORY):
        _issue(registry, EntityIssueType.UNSUPPORTED_ATTRIBUTE, f"{key}: категория без источника снята", False, key)
        entity.category = EntityCategory.UNCLEAR
    if entity.category is EntityCategory.UNCLEAR:
        message = f"{key} «{entity.name}»: категория объекта не установлена"
        _issue(registry, EntityIssueType.OTHER, message, False, key)


def _check_relations(registry: Registry) -> None:
    for index, relation in enumerate(registry.relations):
        ends = (relation.from_key, relation.to_key)
        if relation.from_key == relation.to_key or not all(end in registry.entities for end in ends):
            message = f"Связь {relation.from_key} → {relation.to_key}: концы должны быть разными объектами документа"
            registry.add_issue(RegistryIssue(EntityIssueType.OTHER, message, True, None, index))
        if not _supports(relation.sources, SUPPORT_RELATION):
            message = f"Связь {relation.from_key} → {relation.to_key} без источника (supports: relation)"
            registry.add_issue(RegistryIssue(EntityIssueType.UNSUPPORTED_ATTRIBUTE, message, False, None, index))


def _check_marks(registry: Registry, blocks: Sequence[Block], marks: Sequence[BlockMark]) -> None:
    marked = {mark.node_id for mark in marks}
    for block in blocks:
        if block.root_id not in marked:
            message = f"Блок «{block_path(block)}» не получил отметку обработки"
            registry.add_issue(RegistryIssue(EntityIssueType.BLOCK_FAILED, message, True))


def finish(registry: Registry, blocks: Sequence[Block], marks: Sequence[BlockMark]) -> StageReport:
    """Run the final checks, correcting unsupported claims in place.

    Args:
        registry: The document's registry after all blocks and the review.
        blocks: The planned blocks.
        marks: The marks the blocks received.

    Returns:
        Review status of every entity and the document's status.
    """
    _check_parent_links(registry)
    for key, entity in registry.entities.items():
        _check_attributes(registry, key, entity)
    _check_relations(registry)
    _check_marks(registry, blocks, marks)
    flagged = {issue.entity for issue in registry.issues if issue.entity is not None}
    review = {key: ReviewStatus.NEEDS_REVIEW if key in flagged else ReviewStatus.CHECKED for key in registry.entities}
    blocked = any(issue.is_blocking for issue in registry.issues) or any(
        mark.status is BlockStatus.FAILED for mark in marks
    )
    return StageReport(review, EntitiesStatus.NEEDS_REVIEW if blocked else EntitiesStatus.DONE)
