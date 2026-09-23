"""Code-side checks of a stage 3 answer (methodology §6).

Structure, required fields, entity keys of the current document's registry, node ids of the
current document, verbatim quotes, and support: every record needs sources for its
formulation and type, every filled condition, deadline and periodicity needs its own source,
every binding to an entity needs a source for the binding, and a binding without an entity
needs the original designation and a note. Problems are returned as messages for the model.

A record is kept only if all of its own checks pass, so an answer that still has errors after
the last retry keeps its correct records and drops the rest.
"""

import re
from dataclasses import dataclass

from la_rp_peace.activities.answers import (
    BINDING_SUPPORTS,
    RECORD_SUPPORTS,
    SUPPORT_BINDING,
    SUPPORT_CONDITION,
    SUPPORT_DEADLINE,
    SUPPORT_FORMULATION,
    SUPPORT_PERIODICITY,
    SUPPORT_TYPE,
    BindingIn,
    BlockAnswer,
    RecordIn,
)
from la_rp_peace.entities.answers import SourceIn
from la_rp_peace.entities.verify import SourceVerifier, VerifiedSource
from la_rp_peace.enums import ActivityType, Participation

_HAS_WORD = re.compile(r"\w")
_SHARED_PARTICIPATION = (Participation.JOINT, Participation.ALTERNATIVE)


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
class CheckedBinding:
    """A verified binding; ``entity_id`` None means the executor is not in the registry."""

    entity_id: int | None
    designation: str
    participation: Participation
    condition: str | None
    note: str | None
    sources: tuple[VerifiedSource, ...]


@dataclass(frozen=True, slots=True)
class CheckedRecord:
    """A verified record with its bindings and sources."""

    record_type: ActivityType
    type_unclear: bool
    formulation: str
    condition: str | None
    deadline: str | None
    periodicity: str | None
    bindings: tuple[CheckedBinding, ...]
    sources: tuple[VerifiedSource, ...]
    notes: tuple[str, ...]


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


def _check_fields(record: RecordIn, owner: str, scope: BlockScope, errors: list[str]) -> None:
    fields = {
        SUPPORT_FORMULATION: record.formulation,
        SUPPORT_TYPE: record.type.value,
        SUPPORT_CONDITION: record.condition,
        SUPPORT_DEADLINE: record.deadline,
        SUPPORT_PERIODICITY: record.periodicity,
    }
    for claim, value in fields.items():
        if value is not None and not value.strip():
            errors.append(f"{owner}: поле {claim} пустое — укажите null, если в тексте его нет")
        elif value is not None and not _supported(record.sources, claim):
            errors.append(f"{owner}: поле {claim} не подтверждено источником (supports: {claim})")
    anchored = any(
        SUPPORT_FORMULATION in source.supports and source.node_id in scope.own_nodes for source in record.sources
    )
    if not anchored:
        errors.append(
            f"{owner}: формулировка должна подтверждаться узлом этого блока, а не только строками «(контекст)» "
            "или узлами вне блока — контекст повторно не извлекается",
        )


def _check_binding(binding: BindingIn, owner: str, scope: BlockScope, errors: list[str]) -> CheckedBinding | None:
    before = len(errors)
    entry = scope.registry.get(binding.entity) if binding.entity is not None else None
    designation, condition, note = _clean(binding.designation), _clean(binding.condition), _clean(binding.note)
    if binding.entity is not None and entry is None:
        errors.append(f"{owner}: объекта {binding.entity} нет в реестре текущего документа")
    if binding.entity is not None and not _supported(binding.sources, SUPPORT_BINDING):
        errors.append(f"{owner}: привязка к {binding.entity} не подтверждена источником (supports: binding)")
    if binding.entity is None and designation is None:
        errors.append(f"{owner}: для исполнителя вне реестра нужно исходное обозначение (designation)")
    if binding.entity is None and note is None:
        errors.append(f"{owner}: для исполнителя вне реестра нужно пояснение для проверки (note)")
    if condition is not None and not _supported(binding.sources, SUPPORT_CONDITION):
        errors.append(f"{owner}: условие участия не подтверждено источником (supports: condition)")
    sources = _check_sources(binding.sources, BINDING_SUPPORTS, owner, scope, errors)
    if len(errors) > before:
        return None
    return CheckedBinding(
        entity_id=entry.entity_id if entry is not None else None,
        designation=designation or (entry.name if entry is not None else ""),
        participation=binding.participation,
        condition=condition,
        note=note,
        sources=tuple(sources),
    )


def _check_participation(record: RecordIn, owner: str, errors: list[str]) -> None:
    keys = [binding.entity for binding in record.bindings if binding.entity is not None]
    if len(keys) != len(set(keys)):
        errors.append(f"{owner}: один объект привязан к записи несколько раз")
    shared = [binding for binding in record.bindings if binding.participation in _SHARED_PARTICIPATION]
    if shared and len(record.bindings) < 2:
        errors.append(f"{owner}: совместное или альтернативное участие требует минимум двух привязок")


def check_record(record: RecordIn, owner: str, scope: BlockScope) -> tuple[CheckedRecord | None, list[str]]:
    """Check one record of an answer.

    Args:
        record: The record as answered.
        owner: Label of the record for messages.
        scope: What the answer may refer to.

    Returns:
        The verified record (None if any check failed) and the problems found.
    """
    errors: list[str] = []
    _check_fields(record, owner, scope, errors)
    _check_participation(record, owner, errors)
    sources = _check_sources(record.sources, RECORD_SUPPORTS, owner, scope, errors)
    bindings = [
        _check_binding(binding, f"{owner}, привязка {number}", scope, errors)
        for number, binding in enumerate(record.bindings, start=1)
    ]
    if errors:
        return None, errors
    checked = CheckedRecord(
        record_type=record.type,
        type_unclear=record.type_unclear,
        formulation=record.formulation.strip(),
        condition=record.condition,
        deadline=record.deadline,
        periodicity=record.periodicity,
        bindings=tuple(binding for binding in bindings if binding is not None),
        sources=tuple(sources),
        notes=tuple(note for note in record.notes if note.strip()),
    )
    return checked, errors


def _check_block_status(answer: BlockAnswer, errors: list[str]) -> None:
    if answer.block_status == "none" and answer.records:
        errors.append("block_status «none», но записи перечислены")
    if answer.block_status == "found" and not answer.records:
        errors.append("block_status «found», но записей нет — используйте «none»")
    flagged = answer.unclear or any(record.notes or record.type_unclear for record in answer.records)
    if answer.block_status == "needs_clarification" and not flagged:
        errors.append("block_status «needs_clarification» без замечаний — опишите неясность в unclear")


def check_answer(answer: BlockAnswer, scope: BlockScope) -> tuple[list[CheckedRecord], list[str]]:
    """Check a whole block answer.

    Args:
        answer: Parsed answer.
        scope: What the answer may refer to.

    Returns:
        The records that passed their checks, and every problem for the model.
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
    for number, record in enumerate(answer.records, start=1):
        checked, problems = check_record(record, f"запись {number} «{record.formulation[:60]}»", scope)
        errors += problems
        if checked is not None:
            records.append(checked)
    return records, errors
