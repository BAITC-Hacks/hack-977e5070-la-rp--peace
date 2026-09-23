"""Embeddings for the analysis stages (methodology 4.1 §4, 4.2 §2).

Similarity thresholds only mean something for one fixed model, metric and text format, so all
three are named here and must be stored with every result that uses a score. Vectors are cached
by model, text format and the SHA-256 of the exact embedded text: re-runs and consolidated views
reuse them, and a changed text is embedded again.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import openai
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from la_rp_peace.models import EmbeddingCache

METRIC = "cosine"
TEXT_FORMAT = "activity-v1"
_BATCH = 64

type Matrix = NDArray[np.float64]


class EmbeddingError(RuntimeError):
    """The embedding service could not be reached or returned an unusable answer."""


class Embedder(Protocol):
    """Turns texts into vectors with one fixed model."""

    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per text, in order."""
        ...


class OpenAIEmbedder:
    """Embedder backed by the OpenAI embeddings API."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout_seconds: float = 120) -> None:
        """Create the client.

        Args:
            api_key: OpenAI API key.
            model: Embedding model, e.g. ``text-embedding-3-large``.
            base_url: Alternative OpenAI-compatible endpoint, if any.
            timeout_seconds: Per-request timeout.
        """
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=6)
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in batches.

        Raises:
            EmbeddingError: On API errors or a reply of the wrong length.
        """
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            batch = list(texts[start : start + _BATCH])
            try:
                response = self._client.embeddings.create(model=self.model, input=batch)
            except openai.OpenAIError as exc:
                raise EmbeddingError(f"Ошибка обращения к модели эмбеддингов: {exc}") from exc
            if len(response.data) != len(batch):
                raise EmbeddingError("Модель эмбеддингов вернула не столько векторов, сколько текстов")
            vectors += [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        return vectors


@dataclass(frozen=True, slots=True)
class ActivityText:
    """The fields of an activity record (or consolidated view) that go into its embedding."""

    entity: str
    category: str
    record_type: str
    formulation: str
    participation: str
    participants: str
    condition: str | None = None
    deadline: str | None = None
    periodicity: str | None = None


def activity_text(item: ActivityText) -> str:
    """Render the text that is embedded (format ``TEXT_FORMAT``); quotes are kept separately."""
    lines = [
        f"Объект: {item.entity} ({item.category})",
        f"Вид положения: {item.record_type}",
        f"Формулировка: {item.formulation}",
        f"Участие: {item.participation}; участники: {item.participants}",
    ]
    lines += [f"{label}: {value}" for label, value in _optional(item) if value]
    return "\n".join(lines)


def _optional(item: ActivityText) -> list[tuple[str, str | None]]:
    return [("Условие", item.condition), ("Срок", item.deadline), ("Периодичность", item.periodicity)]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_texts(session: Session, embedder: Embedder, texts: Sequence[str]) -> Matrix:
    """Embed texts, reusing cached vectors of the same model, format and exact text.

    New vectors are added to the session (the caller commits).

    Args:
        session: Database session.
        embedder: The embedding model.
        texts: Texts rendered with ``activity_text`` (or another ``TEXT_FORMAT``-stable renderer).

    Returns:
        A ``len(texts) x dimensions`` matrix in the order of ``texts``.

    Raises:
        EmbeddingError: If new vectors cannot be obtained.
    """
    if not texts:
        return np.zeros((0, 0))
    hashes = [_sha256(text) for text in texts]
    rows = session.scalars(
        select(EmbeddingCache).where(
            EmbeddingCache.model == embedder.model,
            EmbeddingCache.text_format == TEXT_FORMAT,
            EmbeddingCache.text_sha256.in_(set(hashes)),
        ),
    ).all()
    cached = {row.text_sha256: np.frombuffer(row.vector, dtype=np.float64) for row in rows}
    missing = list(dict.fromkeys(digest for digest in hashes if digest not in cached))
    if missing:
        first_text = dict(zip(hashes, texts, strict=True))
        fresh = embedder.embed([first_text[digest] for digest in missing])
        rows_to_add = []
        for digest, vector in zip(missing, fresh, strict=True):
            array = np.asarray(vector, dtype=np.float64)
            cached[digest] = array
            rows_to_add.append(
                {
                    "model": embedder.model,
                    "text_format": TEXT_FORMAT,
                    "text_sha256": digest,
                    "dimensions": int(array.shape[0]),
                    "vector": array.tobytes(),
                }
            )
        # Stages running side by side may embed the same text; the first stored vector wins.
        session.execute(sqlite_insert(EmbeddingCache).values(rows_to_add).on_conflict_do_nothing())
    return np.vstack([cached[digest] for digest in hashes])


def cosine_matrix(left: Matrix, right: Matrix) -> Matrix:
    """Cosine similarity of every row of ``left`` with every row of ``right``.

    Scores are exact (no rounding); compare them with thresholds as they are.
    """
    if left.size == 0 or right.size == 0:
        return np.zeros((left.shape[0], right.shape[0]))
    left_norm = left / np.linalg.norm(left, axis=1, keepdims=True)
    right_norm = right / np.linalg.norm(right, axis=1, keepdims=True)
    scores: Matrix = left_norm @ right_norm.T
    return scores
