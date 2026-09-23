"""Offline helpers for stage 3 tests: parsed editions, entities inserted directly, a scripted model.

The scripted model reads the ``[node <id>] path | text`` lines and the ``E<n> | name`` registry
lines of the user message, so hand-written answers can cite the real node ids of the tree. It can
also be given all node texts of the document, for sources outside the block (e.g. membership).
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from conftest import RecordedProfiler, answer_by_edition, edition_path
from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.activities.prompt import SYSTEM_PROMPT
from la_rp_peace.enums import DocSet, EntitiesStatus
from la_rp_peace.ingestion.pipeline import parse_document, register
from la_rp_peace.llm import Message
from la_rp_peace.models import Document, DocumentNode, Entity

_LINE = re.compile(r"^\[node (\d+)\] (\(контекст\) )?.*? \| (.*)$")
_ENTITY = re.compile(r"^(E\d+) \| ([^|]+?) \|")

# name, type, parent name, aliases. «Работники БВА» is a group, not an entity: its members are
# the directors listed in п. 3.5 of edition 9.
ED9_ENTITIES: list[tuple[str, str, str | None, list[str]]] = [
    ("АО «Компания»", "компания", None, ["Общество"]),
    ("Блок внутреннего аудита", "блок", "АО «Компания»", ["БВА"]),
    ("Главный аудитор", "должность", "Блок внутреннего аудита", []),
    ("Директор ДИТААД", "должность", "Блок внутреннего аудита", []),
    ("Директор ДОА", "должность", "Блок внутреннего аудита", []),
    ("Куратор проверки", "временная роль", None, ["Куратор"]),
    ("Рабочая группа", "временная группа", None, []),
]


def parse_edition(session: Session, edition: int) -> int:
    """Register and parse a test edition with the recorded stage 1 answer; return its id."""
    path = edition_path(edition)
    document = register(session, path.name, path.read_bytes(), DocSet.AFTER)
    parse_document(session, document.id, RecordedProfiler(answer_by_edition), 150_000, 0)
    return document.id


def node_texts(session: Session, document_id: int) -> dict[int, str]:
    """All node texts of a document by id."""
    rows = session.execute(select(DocumentNode.id, DocumentNode.text).where(DocumentNode.document_id == document_id))
    return dict(rows.tuples().all())


def add_entities(
    session: Session,
    document_id: int,
    entities: list[tuple[str, str, str | None, list[str]]],
    status: EntitiesStatus = EntitiesStatus.DONE,
) -> dict[str, int]:
    """Insert a stage 2 registry directly and set ``entities_status``; return ids by name."""
    ids: dict[str, int] = {}
    for name, entity_type, parent, aliases in entities:
        row = Entity(
            document_id=document_id,
            parent_id=ids[parent] if parent else None,
            parent_status="resolved" if parent else "unknown",
            name=name,
            aliases=json.dumps(aliases, ensure_ascii=False),
            entity_type=entity_type,
            review_status="checked",
        )
        session.add(row)
        session.flush()
        ids[name] = row.id
    document = session.get(Document, document_id)
    assert document is not None
    document.entities_status = status.value
    session.commit()
    return ids


@dataclass
class BlockView:
    """The block and registry as the model saw them, plus the document's nodes if given."""

    own: dict[int, str] = field(default_factory=dict)
    context: dict[int, str] = field(default_factory=dict)
    document: dict[int, str] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    attempt: int = 1

    def node(self, prefix: str) -> int:
        """Id of the node whose text starts with ``prefix``: block lines first, then the document."""
        for texts in ({**self.context, **self.own}, self.document):
            for node_id, text in texts.items():
                if text.startswith(prefix):
                    return node_id
        raise KeyError(prefix)

    def key(self, name: str) -> str:
        """Registry key of the entity called ``name``."""
        return self.keys[name]

    def has_own(self, prefix: str) -> bool:
        """Tell whether a non-context line of the block starts with ``prefix``."""
        return any(text.startswith(prefix) for text in self.own.values())


def read_view(messages: list[Message], document: dict[int, str]) -> BlockView:
    """Parse the opening user message of a stage 3 conversation."""
    view = BlockView(document=document, attempt=1 + sum(message.role == "assistant" for message in messages))
    for line in messages[1].content.splitlines():
        if match := _LINE.match(line):
            target = view.context if match.group(2) else view.own
            target[int(match.group(1))] = match.group(3)
        elif match := _ENTITY.match(line):
            view.keys[match.group(2).strip()] = match.group(1)
    return view


Handler = Callable[[BlockView], list[dict[str, Any]]]


class ScriptedModel:
    """Answers stage 3 blocks from handlers keyed by the clause text they react to.

    Every handler whose key starts a non-context line of the block contributes its provisions;
    blocks without such lines are answered ``none``. Stage 1 requests get the recorded profile.
    """

    def __init__(self, handlers: Mapping[str, Handler], document: dict[int, str] | None = None) -> None:
        """Remember the handlers and, optionally, all node texts of the document."""
        self.handlers = handlers
        self.document = document or {}
        self.conversations: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        """Return the scripted answer for the conversation."""
        if messages[0].content != SYSTEM_PROMPT:
            return answer_by_edition(messages)
        self.conversations.append(list(messages))
        view = read_view(messages, self.document)
        found = [item for key, handler in self.handlers.items() if view.has_own(key) for item in handler(view)]
        return json.dumps({"block_status": "found" if found else "none", "provisions": found}, ensure_ascii=False)


def source(node_id: int, quote: str, *supports: str) -> dict[str, Any]:
    """A source in the answer format."""
    return {"node_id": node_id, "quote": quote, "supports": list(supports)}


def participant(entity: str | None, sources: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """A participant in the answer format."""
    return {"entity": entity, "sources": sources, **extra}


def provision(
    record_type: str,
    formulation: str,
    participants: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    participation: str = "individual",
    designation: str = "Главный аудитор",
    **extra: Any,
) -> dict[str, Any]:
    """A provision in the answer format."""
    return {
        "type": record_type,
        "formulation": formulation,
        "participation": participation,
        "participant_designation": designation,
        "participants": participants,
        "sources": sources,
        **extra,
    }
