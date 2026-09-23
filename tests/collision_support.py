"""Offline helpers for stage 4.1 tests: a small document built through the ORM, scripted vectors
and a scripted verifying model.

``CollisionDoc`` inserts nodes, entities and stage 3 records with verbatim sources directly.
``ScriptedEmbedder`` returns the vector registered for the formulation of each embedded text, so
tests control the exact cosine scores. ``ScriptedVerifier`` reads the questions of each request
and answers every question with a decision function of (question id, question text).
"""

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from la_rp_peace.collisions.prompt import SYSTEM_PROMPT
from la_rp_peace.llm import Message
from la_rp_peace.models import ActivityRecord, ActivitySource, Document, DocumentNode, Entity

EXACT_075 = [0.75, 0.6614378277661477]  # cosine with [1, 0] is exactly 0.75 in float64
_FORMULATION = re.compile(r"^Формулировка: (.*)$", re.MULTILINE)
_QUESTION = re.compile(r"^### question_id: (\S+)\n", re.MULTILINE)
_SOURCE = re.compile(r"\[node (\d+)\] [^|]*\| «(.*?)» \(запись")

GOOD_EXPLANATION = (
    "Обе стороны независимо обязаны готовить один и тот же квартальный отчёт о проверках для правления, "
    "документ не распределяет между ними части этой работы и не предусматривает совместного выполнения."
)


class ScriptedEmbedder:
    """Returns the vector registered for the formulation of each text."""

    model = "fake-embedding"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        """Remember vectors by formulation."""
        self.vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Look every text's formulation up."""
        self.calls.append(list(texts))
        result = []
        for text in texts:
            match = _FORMULATION.search(text)
            assert match is not None, text
            result.append(self.vectors[match.group(1)])
        return result

    def embedded_formulations(self) -> list[str]:
        """Formulations of every text embedded so far."""
        return [m.group(1) for call in self.calls for text in call if (m := _FORMULATION.search(text))]


@dataclass(frozen=True)
class SideView:
    """What a question says about one side: its first stage 3 source."""

    node_id: int
    quote: str


def sides_of(text: str) -> tuple[SideView, SideView]:
    """First stage 3 source of side A and of side B in a rendered question."""
    part_a, part_b = text.split("\nСторона B", 1)
    a = _SOURCE.search(part_a)
    b = _SOURCE.search(part_b)
    assert a is not None, text
    assert b is not None, text
    return SideView(int(a.group(1)), a.group(2)), SideView(int(b.group(1)), b.group(2))


def collision_answer(question_id: str, text: str) -> dict[str, Any]:
    """A valid collision answer citing both sides."""
    a, b = sides_of(text)
    return {
        "question_id": question_id,
        "verdict": "collision",
        "explanation": GOOD_EXPLANATION,
        "sources": [
            {"node_id": a.node_id, "quote": a.quote, "supports": ["side_a"]},
            {"node_id": b.node_id, "quote": b.quote, "supports": ["side_b"]},
        ],
    }


Decide = Callable[[str, str, int], dict[str, Any] | None]


@dataclass
class ScriptedVerifier:
    """Answers stage 4.1 batches; ``decide`` returns an answer or None (no answer) per question."""

    decide: Decide = field(default=lambda qid, text, _attempt: collision_answer(qid, text))
    requests: list[list[Message]] = field(default_factory=list)
    questions: dict[str, str] = field(default_factory=dict)

    def complete(self, messages: list[Message]) -> str:
        """Answer the questions of the last user message."""
        assert messages[0].content == SYSTEM_PROMPT
        self.requests.append(list(messages))
        attempt = 1 + sum(message.role == "assistant" for message in messages)
        content = messages[-1].content
        heads = list(_QUESTION.finditer(content))
        answers = []
        for index, head in enumerate(heads):
            end = heads[index + 1].start() if index + 1 < len(heads) else len(content)
            text = content[head.end() : end]
            self.questions.setdefault(head.group(1), text)
            answer = self.decide(head.group(1), text, attempt)
            if answer is not None:
                answers.append(answer)
        return json.dumps({"answers": answers}, ensure_ascii=False)


class CollisionDoc:
    """A document with nodes, entities and stage 3 records inserted directly."""

    def __init__(self, session: Session, name: str = "doc.docx") -> None:
        """Create a parsed document with stages 2 and 3 done."""
        self.session = session
        self.document = Document(
            file_name=name,
            source_format="docx",
            file_size_bytes=1,
            content_sha256=hashlib.sha256(name.encode()).hexdigest(),
            parse_status="validated",
            original_text="-",
            entities_status="done",
            activities_status="done",
        )
        session.add(self.document)
        session.flush()
        self.id = self.document.id
        self._offset = 0
        self._position = 0
        self._keys = 0

    def node(self, text: str) -> int:
        """Add a top-level clause node."""
        row = DocumentNode(
            document_id=self.id,
            position=self._position,
            node_type="clause",
            marker=f"{self._position + 1}.",
            text=text,
            source_start=self._offset,
            source_end=self._offset + len(text),
        )
        self.session.add(row)
        self.session.flush()
        self._position += 1
        self._offset += len(text) + 1
        return row.id

    def entity(self, name: str, category: str, parent: int | None = None) -> int:
        """Add an entity; a parent makes it ``resolved``, otherwise ``unknown``."""
        row = Entity(
            document_id=self.id,
            parent_id=parent,
            parent_status="resolved" if parent is not None else "unknown",
            name=name,
            entity_type=category,
            category=category,
            review_status="checked",
        )
        self.session.add(row)
        self.session.flush()
        return row.id

    def provision_key(self) -> str:
        """A fresh provision key."""
        self._keys += 1
        return f"{self._keys:016x}"

    def record(self, entity: int | None, formulation: str, **fields: Any) -> int:
        """Add a record with one verbatim source in a new node that states the formulation.

        Keyword fields override the record's columns; ``node`` reuses an existing node whose
        text contains the formulation.
        """
        node = fields.pop("node", None)
        if node is None:
            node = self.node(f"Работник обязан: {formulation}.")
        values: dict[str, Any] = {
            "record_type": "function",
            "specificity": "specific",
            "participation": "individual",
            "participant_designation": "исполнитель",
            "designation": "исполнитель",
            "provision_key": fields.pop("provision_key", None) or self.provision_key(),
            "note": None if entity is not None else "не установлен",
        }
        values.update(fields)
        row = ActivityRecord(
            document_id=self.id, block_node_id=node, entity_id=entity, formulation=formulation, **values
        )
        self.session.add(row)
        self.session.flush()
        text = self.session.get(DocumentNode, node)
        assert text is not None
        start = text.text.index(formulation)
        self.session.add(
            ActivitySource(
                document_id=self.id,
                record_id=row.id,
                node_id=node,
                quote=formulation,
                quote_start=start,
                quote_end=start + len(formulation),
                supports=json.dumps(["formulation"]),
            ),
        )
        self.session.flush()
        return row.id
