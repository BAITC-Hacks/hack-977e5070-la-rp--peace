"""Best parent candidate of every child function (methodology 4.2 §2–§3).

Each child function is scored against ALL parent functions of its group and only the maximum
counts. Thresholds are applied to the raw cosine, before any rounding for display: above 0.85
the link is accepted automatically, above 0.50 up to 0.85 inclusive it goes to one LLM question,
0.50 and below (or no candidates) means no pair. An exact tie of the maximal scores leaves the
parent undecided (``ambiguous``). The second-best candidate is never used.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from la_rp_peace.cascade.groups import Group
from la_rp_peace.embeddings import Matrix
from la_rp_peace.models import ActivityRecord

AUTO_ABOVE = 0.85
VERIFY_ABOVE = 0.50


@dataclass(frozen=True, slots=True)
class Choice:
    """The best candidate of one child function in its group.

    Attributes:
        group: The group the child function was compared in.
        child: The child function.
        parent_record_id: The single best parent function; None without candidates. On a tie it
            is None and ``tied_record_ids`` lists every candidate with the maximal score.
        similarity: The raw maximal cosine; None without candidates.
        tied_record_ids: All parent functions sharing the maximal score, when there are several.
    """

    group: Group
    child: ActivityRecord
    parent_record_id: int | None
    similarity: float | None
    tied_record_ids: tuple[int, ...] = ()

    @property
    def tied(self) -> bool:
        """Whether several candidates share the maximal score."""
        return len(self.tied_record_ids) > 1

    @property
    def auto_accepted(self) -> bool:
        """Whether the link is accepted without the LLM (single best above 0.85)."""
        return not self.tied and self.similarity is not None and self.similarity > AUTO_ABOVE

    @property
    def needs_question(self) -> bool:
        """Whether the single best candidate goes to the LLM (above 0.50, up to 0.85 inclusive)."""
        return not self.tied and self.similarity is not None and VERIFY_ABOVE < self.similarity <= AUTO_ABOVE


def choose(group: Group, scores: Matrix) -> list[Choice]:
    """Pick the best parent candidate of every child function of a group.

    Args:
        group: The group.
        scores: Cosine of every child function (rows, ``group.child_records`` order) with every
            parent function (columns, ``group.parent_records`` order).

    Returns:
        One choice per child function, in ``group.child_records`` order.
    """
    parents = [record.id for record in group.parent_records]
    return [_best(group, child, parents, scores[row]) for row, child in enumerate(group.child_records)]


def _best(group: Group, child: ActivityRecord, parents: Sequence[int], row: Matrix) -> Choice:
    if not parents:
        return Choice(group, child, None, None)
    best = float(np.max(row))
    tied = tuple(parent for parent, score in zip(parents, row, strict=True) if float(score) == best)
    if len(tied) > 1:
        return Choice(group, child, None, best, tied)
    return Choice(group, child, tied[0], best)
