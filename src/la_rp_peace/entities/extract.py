"""Read one block with the model and add what it found to the document's registry (methodology §2–§3).

Every block gets a mark: ``found``, ``none``, ``needs_clarification`` — or ``failed`` when the
request failed or no answer passed the checks within the retry budget. A failed block is
never recorded as «no objects»: it also raises a blocking issue for the responsible employee.
"""

from dataclasses import dataclass

from la_rp_peace.entities.answers import BlockAnswer
from la_rp_peace.entities.blocks import Block
from la_rp_peace.entities.conversation import converse
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


def extract_block(model: ChatModel, card: DocumentCard, block: Block, registry: Registry, retries: int) -> BlockMark:
    """Read one block and apply the accepted answer to the registry.

    Args:
        model: The chat model.
        card: The current document.
        block: The block to read.
        registry: The document's registry; shown to the model and updated in place.
        retries: Corrected answers to request after the first.

    Returns:
        The block's mark.
    """
    keys = set(registry.entities)
    outcome = converse(
        model,
        block_messages(card, registry.summary(), block),
        BlockAnswer,
        lambda answer: check_block_answer(answer, registry.verifier, keys),
        retries,
    )
    if outcome.request_error is not None:
        return _failed(registry, block, f"ошибка запроса к модели: {outcome.request_error}", outcome.attempts)
    if outcome.answer is None:
        listed = "; ".join(outcome.errors[:_MAX_LISTED_ERRORS])
        return _failed(
            registry, block, f"ответ не прошёл проверку за {outcome.attempts} попыток: {listed}", outcome.attempts
        )
    answer = outcome.answer
    registry.apply_block(answer)
    status = _STATUS[answer.block_status]
    message = "; ".join(item.message for item in answer.unclear) or None
    log.info("entity_block_done", node_id=block.root_id, status=status, mentions=len(answer.mentions))
    return BlockMark(block.root_id, status, message, outcome.attempts)
