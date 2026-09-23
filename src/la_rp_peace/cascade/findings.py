"""The two cascade checks over one set of links (methodology 4.2 §5–§6).

Bottom-up: a child function without an accepted parent is «Основание не найдено»; its reason
keeps no pair (``not_found``) apart from an LLM rejection (``not_confirmed``). Ties, unfinished
or failed verification and a parent level without any functions in the document are recorded
too, but not as final anomalies (§5). Top-down: a parent function of a group without any
accepted child is «Исполнитель не найден»; it is final only when no unresolved link of the group
could still give it a child and the group's executors and their functions are known.

Only expected transitions are checked: functions of a top object need no parent (they are never
child functions of a group), functions of a leaf object need no children (a leaf has no group).
Functions of objects with an unknown or ambiguous parent are marked for clarification instead of
«no pair».

Not detected in this version: the §6 exemption «the document explicitly assigns the action to the
current level itself». Such parent functions appear as «Исполнитель не найден» with a note that
they need a check.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from la_rp_peace.cascade.groups import Group, Structure, entity_of
from la_rp_peace.cascade.links import LinkResult
from la_rp_peace.enums import CascadeFindingKind, CascadeFindingReason, CascadeLinkStatus

NO_EXECUTOR = "Исполнитель не найден"
NO_BASIS = "Основание не найдено"
TO_CLARIFY = "Требует уточнения"

LABELS = {
    CascadeFindingKind.PARENT_WITHOUT_CHILDREN: NO_EXECUTOR,
    CascadeFindingKind.CHILD_WITHOUT_PARENT: NO_BASIS,
    CascadeFindingKind.NEEDS_CLARIFICATION: TO_CLARIFY,
}

_CHILD_REASONS = {
    CascadeLinkStatus.NOT_FOUND: CascadeFindingReason.NOT_FOUND,
    CascadeLinkStatus.NOT_CONFIRMED: CascadeFindingReason.NOT_CONFIRMED,
    CascadeLinkStatus.AMBIGUOUS: CascadeFindingReason.AMBIGUOUS,
    CascadeLinkStatus.PENDING: CascadeFindingReason.PENDING,
    CascadeLinkStatus.ERROR: CascadeFindingReason.ERROR,
}
_UNVERIFIED = frozenset({CascadeLinkStatus.PENDING, CascadeLinkStatus.ERROR})
_FINAL_CHILD_REASONS = frozenset({CascadeFindingReason.NOT_FOUND, CascadeFindingReason.NOT_CONFIRMED})
_EXEMPTION_NOTE = (
    "Исключение «документ закрепляет действие лично за текущим уровнем» в этой версии не распознаётся — "
    "требует проверки."
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One sign for review, before it is stored.

    Attributes:
        kind: Parent without children, child without parent, or needs clarification.
        reason: Why; see ``CascadeFindingReason``.
        final: Whether nothing unresolved could still change it.
        record_id: The function the finding is about.
        entity_id: Its entity.
        group_entity_id: Entity of the checked group; None for clarifications.
        message: Human-readable detail.
    """

    kind: CascadeFindingKind
    reason: CascadeFindingReason
    final: bool
    record_id: int
    entity_id: int
    group_entity_id: int | None
    message: str


def _names(group: Group) -> str:
    return ", ".join(f"«{child.name}»" for child in group.children)


def _child_message(link: LinkResult) -> str:
    choice = link.choice
    if link.status is CascadeLinkStatus.NOT_FOUND and choice.similarity is None:
        return (
            f"У «{choice.group.entity.name}» нет задач и функций в документе: сопоставить не с чем, "
            "недостаточно данных для вывода об аномалии"
        )
    score = f"{choice.similarity:.4f}" if choice.similarity is not None else "—"
    messages = {
        CascadeLinkStatus.NOT_FOUND: f"Нет родительской функции со сходством выше 0.50 (лучшее: {score})",
        CascadeLinkStatus.NOT_CONFIRMED: (
            f"LLM отклонила лучшего кандидата (сходство {score}); переход к следующему кандидату не выполняется"
        ),
        CascadeLinkStatus.AMBIGUOUS: (
            f"Равные максимальные оценки ({score}) у функций {list(choice.tied_record_ids)}: родитель не выбран"
        ),
        CascadeLinkStatus.PENDING: f"Верификация не выполнена: {link.error}",
        CascadeLinkStatus.ERROR: f"Верификация не завершена: {link.error}",
    }
    return messages[link.status]


def _child_findings(links: Sequence[LinkResult]) -> list[Finding]:
    findings: list[Finding] = []
    for link in links:
        if link.status is CascadeLinkStatus.ACCEPTED:
            continue
        child = link.choice.child
        reason = _CHILD_REASONS[link.status]
        if link.status is CascadeLinkStatus.NOT_FOUND and link.choice.similarity is None:
            # No candidates because the parent level has no functions in the document: no pair
            # (methodology §3), but incomplete input rather than a final anomaly (§5).
            reason = CascadeFindingReason.NO_PARENT_FUNCTIONS
        findings.append(
            Finding(
                kind=CascadeFindingKind.CHILD_WITHOUT_PARENT,
                reason=reason,
                final=reason in _FINAL_CHILD_REASONS,
                record_id=child.id,
                entity_id=entity_of(child),
                group_entity_id=link.choice.group.entity.id,
                message=_child_message(link),
            ),
        )
    return findings


def _possible_parents(links: Sequence[LinkResult]) -> set[int]:
    """Parent functions an unresolved link could still attach a child to."""
    possible: set[int] = set()
    for link in links:
        if link.status is CascadeLinkStatus.AMBIGUOUS:
            possible.update(link.choice.tied_record_ids)
        elif link.status in _UNVERIFIED and link.choice.parent_record_id is not None:
            possible.add(link.choice.parent_record_id)
    return possible


def _parent_reason(group: Group, record_id: int, possible: set[int]) -> tuple[CascadeFindingReason, str]:
    if not group.child_records:
        return CascadeFindingReason.NO_CHILD_FUNCTIONS, (
            f"У исполнителей {_names(group)} нет задач и функций в документе: недостаточно данных"
        )
    if record_id in possible:
        return CascadeFindingReason.PENDING, "Связь с исполнителем ещё может установить незавершённое решение группы"
    if group.uncertain_entity_ids:
        return CascadeFindingReason.GROUP_INCOMPLETE, (
            f"Состав исполнителей не установлен: родитель объектов {list(group.uncertain_entity_ids)} неоднозначен"
        )
    return CascadeFindingReason.NO_ACCEPTED_CHILD, (
        f"Ни одна функция исполнителей {_names(group)} не связана с этой функцией. {_EXEMPTION_NOTE}"
    )


def _parent_findings(group: Group, links: Sequence[LinkResult]) -> list[Finding]:
    served = {link.choice.parent_record_id for link in links if link.status is CascadeLinkStatus.ACCEPTED}
    possible = _possible_parents(links)
    findings: list[Finding] = []
    for record in group.parent_records:
        if record.id in served:
            continue
        reason, message = _parent_reason(group, record.id, possible)
        findings.append(
            Finding(
                kind=CascadeFindingKind.PARENT_WITHOUT_CHILDREN,
                reason=reason,
                final=reason is CascadeFindingReason.NO_ACCEPTED_CHILD,
                record_id=record.id,
                entity_id=group.entity.id,
                group_entity_id=group.entity.id,
                message=message,
            ),
        )
    return findings


def _clarifications(structure: Structure) -> list[Finding]:
    return [
        Finding(
            kind=CascadeFindingKind.NEEDS_CLARIFICATION,
            reason=item.reason,
            final=False,
            record_id=item.record.id,
            entity_id=item.entity.id,
            group_entity_id=None,
            message=(
                f"Организационный родитель «{item.entity.name}» "
                f"{'не установлен' if item.reason is CascadeFindingReason.PARENT_UNKNOWN else 'неоднозначен'}: "
                "основание функции проверить нельзя, отсутствие пары не объявляется"
            ),
        )
        for item in structure.clarifications
    ]


def find(structure: Structure, links: Sequence[LinkResult]) -> list[Finding]:
    """Run both checks over the links of every group and add the clarifications.

    Args:
        structure: Groups and clarifications of the document.
        links: One decision per child function of every group.

    Returns:
        Findings: per group, children without parent then parents without children; then clarifications.
    """
    findings: list[Finding] = []
    for group in structure.groups:
        own = [link for link in links if link.choice.group.entity.id == group.entity.id]
        findings += _child_findings(own)
        findings += _parent_findings(group, own)
    return findings + _clarifications(structure)
