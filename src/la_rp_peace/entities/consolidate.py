"""Whole-document review of the registry after all blocks were read (methodology §4).

The model sees every entity with its sources and the text of every cited node, and may merge
entries that are the same object (with a ``same_entity`` source), settle parents with
evidence, or leave doubts for the responsible employee. The answer goes through the same
check-and-feedback loop as the blocks; if none passes, a blocking issue is recorded and the
registry stays as the blocks built it.
"""

from la_rp_peace.entities.answers import ConsolidationAnswer
from la_rp_peace.entities.conversation import converse
from la_rp_peace.entities.prompt import DocumentCard, consolidation_messages
from la_rp_peace.entities.registry import RegisteredEntity, Registry, RegistryIssue
from la_rp_peace.entities.verify import check_consolidation
from la_rp_peace.enums import EntityIssueType
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger
from la_rp_peace.navigation import NodePlace

log = get_logger(__name__)

_MAX_LISTED_ERRORS = 5


def _entity_review(registry: Registry, entity: RegisteredEntity) -> list[str]:
    aliases = f" (также: {'; '.join(entity.aliases)})" if entity.aliases else ""
    attributes = [f"тип: {entity.entity_type}"]
    attributes += [f"тип позиции: {entity.position_type}"] if entity.position_type else []
    attributes += [f"уровень: {entity.level}"] if entity.level else []
    attributes += [f"роль: {role['role']}" + (f" ({role['scope']})" if role["scope"] else "") for role in entity.roles]
    lines = [f"{entity.key}: {entity.name}{aliases}; {'; '.join(attributes)}; родитель: {registry.parent_text(entity)}"]
    lines += [
        f"  - [node {source.node_id}] «{source.quote}» ({', '.join(source.supports)})"
        for source in dict.fromkeys(entity.sources)
    ]
    return lines


def registry_review(registry: Registry) -> str:
    """Every entity with its attributes and sources, then the relations."""
    lines = [line for entity in registry.entities.values() for line in _entity_review(registry, entity)]
    if registry.relations:
        lines.append("Связи:")
        lines += [
            f"  {relation.from_key} → {relation.to_key}: {relation.relation_type.value}"
            + (f" ({relation.conditions})" if relation.conditions else "")
            for relation in registry.relations
        ]
    return "\n".join(lines)


def cited_nodes(registry: Registry, places: dict[int, NodePlace], node_texts: dict[int, str]) -> str:
    """The nodes the registry cites, in document order, as ``[node <id>] <path> | <text>`` lines."""
    ids = {source.node_id for entity in registry.entities.values() for source in entity.sources}
    ids |= {source.node_id for relation in registry.relations for source in relation.sources}
    return "\n".join(f"[node {node_id}] {places[node_id].path} | {node_texts[node_id]}" for node_id in sorted(ids))


def consolidate(
    model: ChatModel,
    card: DocumentCard,
    registry: Registry,
    places: dict[int, NodePlace],
    node_texts: dict[int, str],
    retries: int,
) -> None:
    """Review the registry once and apply the accepted corrections.

    Args:
        model: The chat model.
        card: The current document.
        registry: The document's registry, updated in place.
        places: Paths of the document's nodes.
        node_texts: Own texts of the document's nodes.
        retries: Corrected answers to request after the first.
    """
    if not registry.entities:
        return
    keys = set(registry.entities)
    outcome = converse(
        model,
        consolidation_messages(card, registry_review(registry), cited_nodes(registry, places, node_texts)),
        ConsolidationAnswer,
        lambda answer: check_consolidation(answer, registry.verifier, keys),
        retries,
    )
    if outcome.answer is None:
        reason = outcome.request_error or "; ".join(outcome.errors[:_MAX_LISTED_ERRORS])
        message = f"Сверка реестра объектов по всему документу не выполнена: {reason}"
        registry.add_issue(RegistryIssue(EntityIssueType.OTHER, message, True))
        log.warning("entity_consolidation_failed", attempts=outcome.attempts, reason=reason)
        return
    registry.apply_consolidation(outcome.answer)
    log.info(
        "entity_consolidation_done",
        merges=len(outcome.answer.merges),
        parent_updates=len(outcome.answer.parent_updates),
        entities=len(registry.entities),
    )
