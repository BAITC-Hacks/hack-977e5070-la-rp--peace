"""Offline helpers for stage 3 tests: parsed editions, entities inserted directly, a scripted model.

The scripted model reads the ``[node <id>] path | text`` lines and the ``E<n> | name`` registry
lines of the user message, so hand-written answers can cite the real node ids of the tree.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from conftest import RecordedProfiler, answer_by_edition, edition_path
from sqlalchemy.orm import Session

from la_rp_peace.activities.prompt import SYSTEM_PROMPT
from la_rp_peace.enums import DocSet, EntitiesStatus
from la_rp_peace.ingestion.pipeline import parse_document, register
from la_rp_peace.llm import Message
from la_rp_peace.models import Document, Entity

_LINE = re.compile(r"^\[node (\d+)\] (\(контекст\) )?.*? \| (.*)$")
_ENTITY = re.compile(r"^(E\d+) \| ([^|]+?) \|")

# name, type, parent name, aliases
ED9_ENTITIES: list[tuple[str, str, str | None, list[str]]] = [
    ("АО «Компания»", "компания", None, ["Общество"]),
    ("Блок внутреннего аудита", "блок", "АО «Компания»", ["БВА"]),
    ("Главный аудитор", "должность", "Блок внутреннего аудита", []),
    ("Работники БВА", "группа работников", "Блок внутреннего аудита", []),
    ("Куратор проверки", "временная роль", None, ["Куратор"]),
    ("Рабочая группа", "временная группа", None, []),
]


def parse_edition(session: Session, edition: int) -> int:
    """Register and parse a test edition with the recorded stage 1 answer; return its id."""
    path = edition_path(edition)
    document = register(session, path.name, path.read_bytes(), DocSet.AFTER)
    parse_document(session, document.id, RecordedProfiler(answer_by_edition), 150_000, 0)
    return document.id


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
    """The block and registry as the model saw them."""

    own: dict[int, str] = field(default_factory=dict)
    context: dict[int, str] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    attempt: int = 1

    def node(self, prefix: str) -> int:
        """Id of the node (own or context) whose text starts with ``prefix``."""
        for node_id, text in {**self.context, **self.own}.items():
            if text.startswith(prefix):
                return node_id
        raise KeyError(prefix)

    def key(self, name: str) -> str:
        """Registry key of the entity called ``name``."""
        return self.keys[name]

    def has_own(self, prefix: str) -> bool:
        """Tell whether a non-context line of the block starts with ``prefix``."""
        return any(text.startswith(prefix) for text in self.own.values())


def read_view(messages: list[Message]) -> BlockView:
    """Parse the opening user message of a stage 3 conversation."""
    view = BlockView(attempt=1 + sum(message.role == "assistant" for message in messages))
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

    Every handler whose key starts a non-context line of the block contributes its records;
    blocks without such lines are answered ``none``. Stage 1 requests get the recorded profile.
    """

    def __init__(self, handlers: Mapping[str, Handler]) -> None:
        """Remember the handlers."""
        self.handlers = handlers
        self.conversations: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        """Return the scripted answer for the conversation."""
        if messages[0].content != SYSTEM_PROMPT:
            return answer_by_edition(messages)
        self.conversations.append(list(messages))
        view = read_view(messages)
        records = [record for key, handler in self.handlers.items() if view.has_own(key) for record in handler(view)]
        return json.dumps({"block_status": "found" if records else "none", "records": records}, ensure_ascii=False)


def source(node_id: int, quote: str, *supports: str) -> dict[str, Any]:
    """A source in the answer format."""
    return {"node_id": node_id, "quote": quote, "supports": list(supports)}


def binding(
    entity: str | None,
    sources: list[dict[str, Any]],
    participation: str = "individual",
    **extra: Any,
) -> dict[str, Any]:
    """A binding in the answer format."""
    return {"entity": entity, "participation": participation, "sources": sources, **extra}
