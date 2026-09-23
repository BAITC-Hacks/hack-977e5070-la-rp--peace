"""Chains «задача департамента → функция отдела → действие исполнителя» from accepted links (methodology 4.2 §7).

Accepted links form a forest over function records (one parent per child function). A chain is a
path from a function that is nobody's accepted child down to a function without accepted
children; functions without any accepted link are not chains.
"""

from collections.abc import Iterable


def build_chains(links: Iterable[tuple[int, int]]) -> list[list[int]]:
    """Return every root-to-leaf path of record ids over accepted ``(parent, child)`` links.

    Args:
        links: Accepted links as ``(parent_record_id, child_record_id)``.

    Returns:
        Chains of at least two record ids, ordered by their record ids.
    """
    children: dict[int, list[int]] = {}
    has_parent: set[int] = set()
    for parent, child in links:
        children.setdefault(parent, []).append(child)
        has_parent.add(child)
    chains: list[list[int]] = []
    stack = [[root] for root in sorted(set(children) - has_parent, reverse=True)]
    while stack:
        path = stack.pop()
        following = [child for child in sorted(children.get(path[-1], []), reverse=True) if child not in path]
        if not following:
            chains.append(path)
        stack += [[*path, child] for child in following]
    return chains
