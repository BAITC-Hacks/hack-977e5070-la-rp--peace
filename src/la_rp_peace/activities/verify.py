"""Code-side checks of a stage 3 answer (methodology §6) and expansion into one record per entity.

Structure, required fields, registry keys and node ids of the current document, verbatim quotes,
and support: every provision needs sources for its formulation and type, for every filled
condition, deadline and periodicity, for a participation other than individual and for a
specificity other than specific; every participant with an entity needs a source for it (and
for its group membership when included through a group); a participant without an entity needs
its designation and a note. Problems are returned as messages for the model.

A provision passing its checks becomes one record per participant with the provision's shared
sources plus the participant's own, and the ids of the other known participants. A provision is
kept only if all of its checks pass, so an answer that still has errors after the last retry
keeps its correct provisions and drops the rest.
"""

import re
from dataclasses import dataclass

from la_rp_peace.activities.answers import (
    PARTICIPANT_SUPPORTS,
    PROVISION_SUPPORTS,
    SUPPORT_CONDITION,
    SUPPORT_DEADLINE,
    SUPPORT_ENTITY,
    SUPPORT_FORMULATION,
    SUPPORT_MEMBERSHIP,
    SUPPORT_PARTICIPATION,
    SUPPORT_PERIODICITY,
    SUPPORT_SPECIFICITY,
    SUPPORT_TYPE,
    BlockAnswer,
    ParticipantIn,
    ProvisionIn,
)
from la_rp_peace.entities.answers import SourceIn
from la_rp_peace.entities.verify import SourceVerifier, VerifiedSource
from la_rp_peace.enums import ActivityType, Participation, Specificity

_HAS_WORD = re.compile(r"\w")
_SHARED = (Participation.EACH, Participation.JOINT, Participation.ALTERNATIVE)


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """An entity of the current document as shown to the model."""

    entity_id: int
    name: str


@dataclass(frozen=True, slots=True)
class BlockScope:
    """What an answer for one block may refer to.

    Attributes:
        verifier: Quote resolver over all nodes of the current document.
        registry: Entities of the current document by key ``E<entity_id>``.
        own_nodes: Nodes of the block that are not context lines; a formulation must rest on one.
    """

    verifier: SourceVerifier
    registry: dict[str, RegistryEntry]
    own_nodes: frozenset[int]


@dataclass(frozen=True, slots=True)
class CheckedRecord:
    """A verified record: one provision for one participant.

    ``entity_id`` None is an unresolved role or undisclosed group remainder; ``note`` says why.
    ``participant_entity_ids`` are the other known participants of the same provision.
    """

    record_type: ActivityType
    type_unclear: bool
    formulation: str
    specificity: Specificity
    participation: Participation
    participant_designation: str
    entity_id: int | None
    designation: str
    participant_entity_ids: tuple[int, ...]
    condition: str | None
    deadline: str | None
    periodicity: str | None
    note: str | None
    sources: tuple[VerifiedSource, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Participant:
    entity_id: int | None
    designation: str
    condition: str | None
    note: str | None
    sources: tuple[VerifiedSource, ...]


def _clean(value: str | None) -> str | None:
    """Strip free text; blank means absent."""
    return (value.strip() or None) if value is not None else None


def _supported(sources: list[SourceIn], claim: str) -> bool:
    return any(claim in source.supports for source in sources)


def _check_sources(
    sources: list[SourceIn], allowed: frozenset[str], owner: str, scope: BlockScope, errors: list[str]
) -> list[VerifiedSource]:
    for source in sources:
        unknown = sorted(set(source.supports) - allowed)
        if unknown:
            errors.append(f"{owner}: недопустимые значения supports {unknown}, разрешены {sorted(allowed)}")
        if not _HAS_WORD.search(source.quote):
            errors.append(f"{owner}: цитата «{source.quote}» не содержит слов и ничего не подтверждает")
    return scope.verifier.verify_all(sources, owner, errors)


def _check_fields(provision: ProvisionIn, owner: str, scope: BlockScope, errors: list[str]) -> None:
    fields = {
        SUPPORT_FORMULATION: provision.formulation,
        SUPPORT_TYPE: provision.type.value,
        SUPPORT_CONDITION: provision.condition,
        SUPPORT_DEADLINE: provision.deadline,
        SUPPORT_PERIODICITY: provision.periodicity,
        SUPPORT_PARTICIPATION: None if provision.participation is Participation.INDIVIDUAL else "set",
        SUPPORT_SPECIFICITY: None if provision.specificity is Specificity.SPECIFIC else "set",
    }
    for claim, value in fields.items():
        if value is not None and not value.strip():
            errors.append(f"{owner}: поле {claim} пустое — укажите null, если в тексте его нет")
        elif value is not None and not _supported(provision.sources, claim):
            errors.append(f"{owner}: поле {claim} не подтверждено источником (supports: {claim})")
    anchored = any(
        SUPPORT_FORMULATION in source.supports and source.node_id in scope.own_nodes for source in provision.sources
    )
    if not anchored:
        errors.append(
            f"{owner}: формулировка должна подтверждаться узлом этого блока, а не только строками «(контекст)» "
            "или узлами вне блока — контекст повторно не извлекается",
        )


def _check_participation(provision: ProvisionIn, owner: str, errors: list[str]) -> None:
    keys = [participant.entity for participant in provision.participants if participant.entity is not None]
    if len(keys) != len(set(keys)):
        errors.append(f"{owner}: один объект указан среди участников несколько раз")
    count = len(provision.participants)
    if provision.participation is Participation.INDIVIDUAL and count != 1:
        errors.append(f"{owner}: participation «individual» — ровно один участник; для нескольких укажите характер")
    if provision.participation in _SHARED and count < 2:
        errors.append(f"{owner}: участие «{provision.participation}» требует минимум двух участников")
    noted = provision.notes or any(_clean(participant.note) for participant in provision.participants)
    if provision.participation is Participation.UNCLEAR and not noted:
        errors.append(f"{owner}: для неустановленного характера участия нужно пояснение (notes)")


def _check_participant(
    participant: ParticipantIn, owner: str, scope: BlockScope, errors: list[str]
) -> _Participant | None:
    before = len(errors)
    entry = scope.registry.get(participant.entity) if participant.entity is not None else None
    designation, condition, note = (
        _clean(participant.designation),
        _clean(participant.condition),
        _clean(participant.note),
    )
    if participant.entity is not None and entry is None:
        errors.append(f"{owner}: объекта {participant.entity} нет в реестре текущего документа")
    if participant.entity is not None and not _supported(participant.sources, SUPPORT_ENTITY):
        errors.append(f"{owner}: участник {participant.entity} не подтверждён источником (supports: entity)")
    if _clean(participant.group) and not _supported(participant.sources, SUPPORT_MEMBERSHIP):
        errors.append(f"{owner}: принадлежность к группе «{participant.group}» не подтверждена (supports: membership)")
    if participant.entity is None and (designation is None or note is None):
        errors.append(f"{owner}: для участника вне реестра нужны исходное обозначение (designation) и пояснение (note)")
    if condition is not None and not _supported(participant.sources, SUPPORT_CONDITION):
        errors.append(f"{owner}: условие участника не подтверждено источником (supports: condition)")
    sources = _check_sources(participant.sources, PARTICIPANT_SUPPORTS, owner, scope, errors)
    if len(errors) > before:
        return None
    name = entry.name if entry is not None else ""
    entity_id = entry.entity_id if entry is not None else None
    return _Participant(entity_id, designation or name, condition, note, tuple(sources))


def _expand(
    provision: ProvisionIn, participants: list[_Participant], sources: list[VerifiedSource]
) -> list[CheckedRecord]:
    known = [participant.entity_id for participant in participants if participant.entity_id is not None]
    records = []
    for participant in participants:
        conditions = [text for text in (_clean(provision.condition), participant.condition) if text]
        records.append(
            CheckedRecord(
                record_type=provision.type,
                type_unclear=provision.type_unclear,
                formulation=provision.formulation.strip(),
                specificity=provision.specificity,
                participation=provision.participation,
                participant_designation=provision.participant_designation.strip(),
                entity_id=participant.entity_id,
                designation=participant.designation,
                participant_entity_ids=tuple(sorted(set(known) - {participant.entity_id})),
                condition="; ".join(conditions) or None,
                deadline=provision.deadline,
                periodicity=provision.periodicity,
                note=participant.note,
                sources=tuple(sources) + participant.sources,
                notes=tuple(note.strip() for note in provision.notes if note.strip()),
            ),
        )
    return records


def check_provision(provision: ProvisionIn, owner: str, scope: BlockScope) -> tuple[list[CheckedRecord], list[str]]:
    """Check one provision and expand it into one record per participant.

    Args:
        provision: The provision as answered.
        owner: Label of the provision for messages.
        scope: What the answer may refer to.

    Returns:
        The records (empty if any check failed) and the problems found.
    """
    errors: list[str] = []
    if not provision.participant_designation.strip():
        errors.append(f"{owner}: participant_designation пустое — укажите исходное обозначение участников")
    _check_fields(provision, owner, scope, errors)
    _check_participation(provision, owner, errors)
    sources = _check_sources(provision.sources, PROVISION_SUPPORTS, owner, scope, errors)
    participants = [
        _check_participant(participant, f"{owner}, участник {number}", scope, errors)
        for number, participant in enumerate(provision.participants, start=1)
    ]
    if errors:
        return [], errors
    return _expand(provision, [item for item in participants if item is not None], sources), errors


def _check_block_status(answer: BlockAnswer, errors: list[str]) -> None:
    if answer.block_status == "none" and answer.provisions:
        errors.append("block_status «none», но положения перечислены")
    if answer.block_status == "found" and not answer.provisions:
        errors.append("block_status «found», но положений нет — используйте «none»")
    flagged = answer.unclear or any(provision.notes or provision.type_unclear for provision in answer.provisions)
    if answer.block_status == "needs_clarification" and not flagged:
        errors.append("block_status «needs_clarification» без замечаний — опишите неясность в unclear")


def check_answer(answer: BlockAnswer, scope: BlockScope) -> tuple[list[CheckedRecord], list[str]]:
    """Check a whole block answer.

    Args:
        answer: Parsed answer.
        scope: What the answer may refer to.

    Returns:
        The records of the provisions that passed their checks, and every problem for the model.
    """
    errors: list[str] = []
    _check_block_status(answer, errors)
    for unclear in answer.unclear:
        errors += [
            f"замечание: узел {node} не относится к текущему документу"
            for node in unclear.node_ids
            if not scope.verifier.has_node(node)
        ]
    records: list[CheckedRecord] = []
    for number, provision in enumerate(answer.provisions, start=1):
        checked, problems = check_provision(provision, f"положение {number} «{provision.formulation[:60]}»", scope)
        errors += problems
        records += checked
    return records, errors
