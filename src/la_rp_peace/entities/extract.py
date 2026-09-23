"""Read one block with the model and add what it found to the document's registry (methodology §2–§3).

Asking (``ask_block``) only reads a snapshot of the registry, so several blocks can be asked
at once; applying (``apply_block``) updates the registry and must run in document order.

Every block gets a mark: ``found``, ``none``, ``needs_clarification`` — or ``failed`` when the
request failed or no answer passed the checks within the retry budget. A failed block is
never recorded as «no objects»: it also raises a blocking issue for the responsible employee.
"""

from dataclasses import dataclass

from la_rp_peace.entities.answers import BlockAnswer
from la_rp_peace.entities.blocks import Block
from la_rp_peace.entities.conversation import Outcome, converse
from la_rp_peace.entities.prompt import DocumentCard, block_messages
from la_rp_peace.entities.registry import Registry, RegistryIssue
from la_rp_peace.entities.verify import check_block_answer
from la_rp_peace.enums import BlockStatus, EntityIssueType
from la_rp_peace.llm import ChatModel
from la_rp_peace.logging_config import get_logger

log = get_logger(__name__)

_MAX_LISTED_ERRORS = 5
_STATUS = {
    "found": BlockStatus.FOUND,
    "none": BlockStatus.NONE,
    "needs_clarification": BlockStatus.NEEDS_CLARIFICATION,
}


@dataclass(frozen=True, slots=True)
class BlockMark:
    """Processing mark of one block, stored for its root node."""

    node_id: int
    status: BlockStatus
    message: str | None
    attempts: int


def block_path(block: Block) -> str:
    """Path of the first own (non-context) line of the block, for messages."""
    own = [line for line in block.lines if not line.context] or list(block.lines)
    return own[0].path if own else f"узел {block.root_id}"


def _failed(registry: Registry, block: Block, reason: str, attempts: int) -> BlockMark:
    message = f"Блок «{block_path(block)}» не обработан: {reason}"
    registry.add_issue(RegistryIssue(EntityIssueType.BLOCK_FAILED, message, True))
    log.warning("entity_block_failed", node_id=block.root_id, attempts=attempts, reason=reason)
    return BlockMark(block.root_id, BlockStatus.FAILED, message, attempts)


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """What a block request may see of the registry: its summary and its keys at one moment."""

    summary: str
    keys: frozenset[str]

    @classmethod
    def of(cls, registry: Registry) -> "RegistrySnapshot":
        """Take a snapshot of the registry as it is now."""
        return cls(registry.summary(), frozenset(registry.entities))


def ask_block(
    model: ChatModel,
    card: DocumentCard,
    block: Block,
    registry: Registry,
    snapshot: RegistrySnapshot,
    retries: int,
) -> Outcome[BlockAnswer]:
    """Ask the model about one block against a registry snapshot; does not change the registry.

    Keys in the snapshot stay valid later: the registry only grows until consolidation.
    """
    return converse(
        model,
        block_messages(card, snapshot.summary, block),
        BlockAnswer,
        lambda answer: check_block_answer(answer, registry.verifier, set(snapshot.keys)),
        retries,
    )


def apply_block(registry: Registry, block: Block, outcome: Outcome[BlockAnswer]) -> BlockMark:
    """Apply a block's accepted answer to the registry and return its mark."""
    if outcome.request_error is not None:
        return _failed(registry, block, f"ошибка запроса к модели: {outcome.request_error}", outcome.attempts)
    if outcome.answer is None:
        listed = "; ".join(outcome.errors[:_MAX_LISTED_ERRORS])
        return _failed(
            registry, block, f"ответ не прошёл проверку за {outcome.attempts} попыток: {listed}", outcome.attempts
        )
    answer = outcome.answer
    registry.apply_block(answer, block.root_id)
    status = _STATUS[answer.block_status]
    message = "; ".join(item.message for item in answer.unclear) or None
    log.info("entity_block_done", node_id=block.root_id, status=status, mentions=len(answer.mentions))
    return BlockMark(block.root_id, status, message, outcome.attempts)


def extract_block(model: ChatModel, card: DocumentCard, block: Block, registry: Registry, retries: int) -> BlockMark:
    """Read one block and apply the accepted answer to the registry (sequential use).

    Args:
        model: The chat model.
        card: The current document.
        block: The block to read.
        registry: The document's registry; shown to the model and updated in place.
        retries: Corrected answers to request after the first.

    Returns:
        The block's mark.
    """
    return apply_block(registry, block, ask_block(model, card, block, registry, RegistrySnapshot.of(registry), retries))
