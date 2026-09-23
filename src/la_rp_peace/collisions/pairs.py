"""Pairs of sides allowed by the two search paths, and selection by similarity (4.1 §1, §3, §4).

Local path: two participants that are different children of the same resolved organisational
parent (any categories; the parent itself is not a child). Category path: two different
participants of the same category, independent of parents; ``unclear`` and ``other`` are not a
level and never give this basis. For a view the participants' parents and categories are used,
and every combination that gives a basis is kept so the question can say which participant gave
it. A pair is unordered and found once, with both bases when both paths find it.

Never paired: a side with itself, two records of the same entity (a repeated function of one
object is not an inter-object collision), and a view with one of its own source records.

Every allowed pair whose raw cosine similarity is STRICTLY above ``THRESHOLD`` is selected;
there is no top-k and no rounding.
"""

from dataclasses import dataclass
from typing import Any

from la_rp_peace.collisions.sides import Party, Side
from la_rp_peace.embeddings import Matrix
from la_rp_peace.enums import CollisionSideKind, EntityCategory, SearchBasis

THRESHOLD = 0.75
NO_LEVEL = frozenset({EntityCategory.UNCLEAR.value, EntityCategory.OTHER.value})


@dataclass(frozen=True, slots=True)
class BasisDetail:
    """Which participants of the two sides gave a search basis, and what they share."""

    basis: SearchBasis
    a_entity_id: int
    b_entity_id: int
    shared: str

    def as_json(self) -> dict[str, Any]:
        """JSON form stored with the pair."""
        return {
            "basis": self.basis.value,
            "a_entity_id": self.a_entity_id,
            "b_entity_id": self.b_entity_id,
            "shared": self.shared,
        }


@dataclass(frozen=True, slots=True)
class Candidate:
    """An allowed unordered pair; ``a`` has the smaller key."""

    a: Side
    b: Side
    details: tuple[BasisDetail, ...]

    @property
    def key(self) -> str:
        """Pair key, identical whichever way round the sides are given."""
        return f"{self.a.key}|{self.b.key}"

    @property
    def bases(self) -> tuple[SearchBasis, ...]:
        """Search paths that found the pair (local first)."""
        found = {detail.basis for detail in self.details}
        return tuple(basis for basis in SearchBasis if basis in found)


@dataclass(frozen=True, slots=True)
class ScoredPair:
    """A candidate with its raw similarity."""

    candidate: Candidate
    similarity: float


@dataclass(frozen=True, slots=True)
class Selection:
    """Pairs sent to verification and the coverage of both search paths."""

    pairs: tuple[ScoredPair, ...]
    local_pairs: int
    local_above: int
    category_pairs: int
    category_above: int


def _comparable(a: Side, b: Side) -> bool:
    if a.key == b.key or set(a.record_ids) & set(b.record_ids):
        return False
    both_records = a.kind is CollisionSideKind.RECORD and b.kind is CollisionSideKind.RECORD
    return not (both_records and a.entity_ids == b.entity_ids)


def _party_bases(x: Party, y: Party) -> list[BasisDetail]:
    if x.entity_id == y.entity_id:
        return []
    found: list[BasisDetail] = []
    if x.parent_id is not None and x.parent_id == y.parent_id:
        found.append(BasisDetail(SearchBasis.LOCAL, x.entity_id, y.entity_id, str(x.parent_id)))
    if x.category == y.category and x.category not in NO_LEVEL:
        found.append(BasisDetail(SearchBasis.CATEGORY, x.entity_id, y.entity_id, x.category))
    return found


def basis_details(a: Side, b: Side) -> tuple[BasisDetail, ...]:
    """Every search basis between two sides; empty when the pair is not allowed."""
    if not _comparable(a, b):
        return ()
    return tuple(detail for x in a.parties for y in b.parties for detail in _party_bases(x, y))


def candidate_pairs(sides: tuple[Side, ...]) -> list[Candidate]:
    """All allowed unordered pairs of sides, each once."""
    ordered = sorted(sides, key=lambda side: side.key)
    candidates: list[Candidate] = []
    for index, a in enumerate(ordered):
        for b in ordered[index + 1 :]:
            details = basis_details(a, b)
            if details:
                candidates.append(Candidate(a, b, details))
    return candidates


def select_pairs(candidates: list[Candidate], scores: Matrix, index: dict[str, int]) -> Selection:
    """Keep the candidates strictly above ``THRESHOLD`` and count coverage per search path.

    Args:
        candidates: Allowed pairs.
        scores: Similarity matrix of the embedded sides.
        index: Row of each side key in ``scores``.

    Returns:
        The selected pairs (in candidate order) and per-path counts of allowed and selected pairs.
    """
    selected: list[ScoredPair] = []
    counts = {basis: [0, 0] for basis in SearchBasis}
    for candidate in candidates:
        similarity = float(scores[index[candidate.a.key], index[candidate.b.key]])
        above = similarity > THRESHOLD
        for basis in candidate.bases:
            counts[basis][0] += 1
            counts[basis][1] += int(above)
        if above:
            selected.append(ScoredPair(candidate, similarity))
    local, category = counts[SearchBasis.LOCAL], counts[SearchBasis.CATEGORY]
    return Selection(tuple(selected), local[0], local[1], category[0], category[1])
