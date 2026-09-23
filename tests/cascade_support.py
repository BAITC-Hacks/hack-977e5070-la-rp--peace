"""Stage 4.2 test helpers: documents built through the ORM, scripted embeddings and verdicts."""

import json
import math
import re
from collections.abc import Mapping, Sequence
from itertools import count

import numpy as np
from sqlalchemy.orm import Session

from la_rp_peace.embeddings import cosine_matrix
from la_rp_peace.llm import Message
from la_rp_peace.models import ActivityRecord, ActivitySource, Document, DocumentNode, Entity

DIMENSIONS = 40
FILLER = DIMENSIONS - 1
TITLE = "Положение о департаменте\n"
_SERIAL = count(1)
_QUESTION = re.compile(r"^### question_id: (\S+)$", re.MULTILINE)
_FORMULATION = re.compile(r"^Формулировка: (.*)$", re.MULTILINE)


def basis(dim: int) -> list[float]:
    """A unit vector along ``dim``: parent functions that are orthogonal to each other."""
    vector = [0.0] * DIMENSIONS
    vector[dim] = 1.0
    return vector


def exact_child(scores: Mapping[int, float]) -> list[float]:
    """A unit vector whose cosine with ``basis(dim)`` is exactly ``scores[dim]`` (no float drift).

    The filler dimension is nudged ulp by ulp until the normalised vector reproduces the scores
    bit for bit, so thresholds such as 0.85 and 0.50 are hit exactly.
    """
    vector = np.zeros(DIMENSIONS)
    for dim, score in scores.items():
        vector[dim] = score
    filler = math.sqrt(max(0.0, 1.0 - sum(score * score for score in scores.values())))
    parents = np.array([basis(dim) for dim in scores])
    target = np.array(list(scores.values()))
    for step in range(-64, 65):
        vector[FILLER] = filler + step * math.ulp(filler or 1.0)
        if np.array_equal(cosine_matrix(vector[np.newaxis, :], parents)[0], target):
            return [float(value) for value in vector]
    raise AssertionError(f"No exact vector for {scores}")


def solved_child(parents: Sequence[Sequence[float]], scores: Sequence[float]) -> list[float]:
    """A unit vector with (approximately) the given cosines to non-orthogonal unit ``parents``."""
    matrix = np.array(parents)
    weights = np.linalg.solve(matrix @ matrix.T, np.array(scores))
    vector = matrix.T @ weights
    vector[FILLER] = math.sqrt(1.0 - float(weights @ np.array(scores)))
    return [float(value) for value in vector]


def unit(vector: Sequence[float]) -> list[float]:
    """Normalise a vector (padded to ``DIMENSIONS``)."""
    array = np.zeros(DIMENSIONS)
    array[: len(vector)] = vector
    return [float(value) for value in array / np.linalg.norm(array)]


class FakeEmbedder:
    """Returns a scripted vector for each record formulation found in the embedded text."""

    model = "fake-embedding-v1"

    def __init__(self, vectors: Mapping[str, Sequence[float]]) -> None:
        """Script the vectors by formulation."""
        self.vectors = dict(vectors)
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return the scripted vector of every text."""
        self.calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            match = _FORMULATION.search(text)
            assert match is not None, text
            vectors.append(list(self.vectors[match.group(1)]))
        return vectors


class ScriptedVerifier:
    """Answers verification questions with scripted verdicts; ``None`` leaves a question unanswered."""

    def __init__(self, verdicts: Mapping[str, str | None] | None = None, default: str | None = "confirmed") -> None:
        """Script verdicts by question id; others get ``default``."""
        self.verdicts = dict(verdicts or {})
        self.default = default
        self.calls: list[list[str]] = []
        self.conversations: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        """Answer the questions listed in the last user message."""
        ids = _QUESTION.findall(messages[-1].content)
        self.calls.append(ids)
        self.conversations.append(list(messages))
        answers = [
            {"question_id": question_id, "verdict": verdict}
            for question_id in ids
            if (verdict := self.verdicts.get(question_id, self.default)) is not None
        ]
        return json.dumps({"answers": answers})


class DocumentBuilder:
    """Inserts one document with its stage 2 entities and stage 3 records through the ORM."""

    def __init__(self, session: Session, *, entities_status: str = "done", activities_status: str = "done") -> None:
        """Create the document (flushed, not committed)."""
        self.session = session
        self.document = Document(
            file_name="положение.docx",
            source_format="docx",
            file_size_bytes=1,
            content_sha256=f"{next(_SERIAL):064x}",
            original_text=TITLE,
            parse_status="validated",
            entities_status=entities_status,
            activities_status=activities_status,
        )
        session.add(self.document)
        session.flush()
        self._offset = len(TITLE)
        self._position = 0

    @property
    def id(self) -> int:
        """The document id."""
        return self.document.id

    def entity(
        self,
        name: str,
        parent: Entity | None = None,
        *,
        status: str | None = None,
        candidates: Sequence[Entity] = (),
        category: str = "department",
    ) -> Entity:
        """Add an entity; resolved under ``parent`` if given, else ``root`` (or ``status``)."""
        entity = Entity(
            document_id=self.id,
            parent_id=parent.id if parent is not None else None,
            parent_status=status or ("resolved" if parent is not None else "root"),
            parent_candidates=json.dumps([candidate.id for candidate in candidates]),
            name=name,
            entity_type=name.split()[0].lower(),
            category=category,
            review_status="checked",
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def record(self, entity: Entity | None, formulation: str, record_type: str = "function") -> ActivityRecord:
        """Add a record in a clause node of its own, with its formulation quoted verbatim."""
        marker = f"{self._position + 1}."
        text = f"{marker} {formulation}"
        node = DocumentNode(
            document_id=self.id,
            position=self._position,
            node_type="clause",
            marker=marker,
            text=text,
            source_start=self._offset,
            source_end=self._offset + len(text),
        )
        self.session.add(node)
        self.session.flush()
        record = ActivityRecord(
            document_id=self.id,
            block_node_id=node.id,
            provision_key=f"{self._position:016x}",
            entity_id=entity.id if entity is not None else None,
            designation=entity.name if entity is not None else "уполномоченный работник",
            record_type=record_type,
            formulation=formulation,
            specificity="specific",
            participation="individual",
            participant_designation=entity.name if entity is not None else "уполномоченный работник",
            note=None if entity is not None else "Роль не найдена в реестре объектов",
            review_status="checked",
        )
        self.session.add(record)
        self.session.flush()
        start = len(marker) + 1
        self.session.add(
            ActivitySource(
                document_id=self.id,
                record_id=record.id,
                node_id=node.id,
                quote=formulation,
                quote_start=start,
                quote_end=start + len(formulation),
                supports=json.dumps(["formulation", "type"]),
            ),
        )
        self.session.flush()
        self.document.original_text = f"{self.document.original_text}{text}\n"
        self._offset += len(text) + 1
        self._position += 1
        return record
