"""Split a document tree into blocks for the model (methodology §2).

A block is one content section (a root node and its subtree). Sections longer than the
limit are split at child boundaries; every part repeats the heading and intro texts of its
ancestors as context. Service text before the first section (approval stamp, title) forms
one block of its own: it may confirm the organisation and the approving body, but never
subordination. Table-of-contents entries and page numbers are not sent at all.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from la_rp_peace.enums import NodeType
from la_rp_peace.models import DocumentNode
from la_rp_peace.navigation import NodePlace


@dataclass(frozen=True, slots=True)
class BlockLine:
    """One node shown to the model."""

    node_id: int
    path: str
    text: str
    context: bool


@dataclass(frozen=True, slots=True)
class Block:
    """One request's worth of document text; ``root_id`` is the node the mark is stored for."""

    root_id: int
    lines: tuple[BlockLine, ...]

    def render(self) -> str:
        """Show the block as ``[node <id>] <path> | <text>`` lines; context lines are marked."""
        return "\n".join(
            f"[node {line.node_id}] {'(контекст) ' if line.context else ''}{line.path} | {line.text}"
            for line in self.lines
        )


class _Tree:
    def __init__(self, nodes: Sequence[DocumentNode], places: dict[int, NodePlace]) -> None:
        self.nodes = {node.id: node for node in nodes}
        self.places = places
        self.children: dict[int | None, list[DocumentNode]] = {}
        for node in sorted(nodes, key=lambda item: item.id):
            self.children.setdefault(node.parent_id, []).append(node)

    def is_noise(self, node: DocumentNode) -> bool:
        """Page numbers inside content, and nodes without own text, carry nothing to read."""
        return (node.node_type == NodeType.SERVICE and node.text.isdigit()) or not node.text.strip()

    def line(self, node: DocumentNode, context: bool = False) -> BlockLine:
        return BlockLine(node.id, self.places[node.id].path, node.text, context)

    def subtree(self, node: DocumentNode) -> list[BlockLine]:
        lines = [] if self.is_noise(node) else [self.line(node)]
        for child in self.children.get(node.id, []):
            lines += self.subtree(child)
        return lines

    def size(self, lines: list[BlockLine]) -> int:
        return sum(len(line.path) + len(line.text) + 16 for line in lines)


def _split(tree: _Tree, node: DocumentNode, context: list[BlockLine], max_chars: int) -> list[Block]:
    """Blocks for ``node``'s subtree, each prefixed with ``context``."""
    whole = tree.subtree(node)
    children = tree.children.get(node.id, [])
    if tree.size(context + whole) <= max_chars or not children:
        return [Block(node.id, tuple(context + whole))]
    own = [] if tree.is_noise(node) else [tree.line(node, context=True)]
    inner_context = context + own
    blocks: list[Block] = []
    group: list[DocumentNode] = []

    def flush() -> None:
        if group:
            lines = [line for child in group for line in tree.subtree(child)]
            if lines:
                blocks.append(Block(group[0].id, tuple(inner_context + lines)))
        group.clear()

    for child in children:
        child_size = tree.size(tree.subtree(child))
        if tree.size(inner_context) + child_size > max_chars:
            flush()
            blocks += _split(tree, child, inner_context, max_chars)
            continue
        candidate = [line for item in [*group, child] for line in tree.subtree(item)]
        if group and tree.size(inner_context + candidate) > max_chars:
            flush()
        group.append(child)
    flush()
    return blocks


def plan_blocks(nodes: Sequence[DocumentNode], places: dict[int, NodePlace], max_chars: int) -> list[Block]:
    """Plan the requests for one document.

    Args:
        nodes: All nodes of the document.
        places: Paths of the nodes, from ``navigation.describe``.
        max_chars: Size limit of one block's rendered text.

    Returns:
        Blocks in document order.
    """
    tree = _Tree(nodes, places)
    blocks: list[Block] = []
    front_matter: list[BlockLine] = []
    seen_content = False
    for root in tree.children.get(None, []):
        if root.node_type == NodeType.SERVICE:
            if not seen_content and not tree.children.get(root.id) and not tree.is_noise(root):
                front_matter.append(tree.line(root))
            continue
        seen_content = True
        blocks += _split(tree, root, [], max_chars)
    if front_matter:
        blocks.insert(0, Block(front_matter[0].node_id, tuple(front_matter)))
    return blocks
