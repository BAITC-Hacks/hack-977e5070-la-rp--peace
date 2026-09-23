"""Offline stage 2 helpers: a scripted chat model that reads the real node ids from each block.

The scripted model answers stage 1 with the recorded profiles (``answer_by_edition``) and
stage 2 with hand-written answers built from what the prompt shows: node lines
``[node <id>] <path> | <text>`` and registry lines ``E<n>: <name> …``. Answers therefore cite
the real node ids of whatever database the test uses.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from conftest import RecordedProfiler, answer_by_edition, edition_path
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.db import make_engine
from la_rp_peace.entities.prompt import BLOCK_SYSTEM_PROMPT, CONSOLIDATION_SYSTEM_PROMPT
from la_rp_peace.enums import DocSet
from la_rp_peace.ingestion.pipeline import parse_document, register
from la_rp_peace.llm import Message
from la_rp_peace.models import create_schema

_NODE_LINE = re.compile(r"^\[node (\d+)\] (?:\(контекст\) )?(.*?) \| (.*)$")
_REGISTRY_LINE = re.compile(r"^(E\d+): (.+?)(?: \(также: .*?\))? — ")

Answer = dict[str, Any]
CATEGORY_BY_TYPE = {
    "блок": "block",
    "департамент": "department",
    "должность": "position",
    "орган управления": "governing_body",
    "группа работников": "collective",
}


@dataclass
class View:
    """What one stage 2 conversation shows: nodes, registry keys, feedback so far."""

    nodes: dict[int, str]
    paths: dict[int, str]
    registry: dict[str, str]
    feedback: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, messages: list[Message]) -> Self:
        nodes: dict[int, str] = {}
        paths: dict[int, str] = {}
        registry: dict[str, str] = {}
        for line in messages[1].content.splitlines():
            if match := _NODE_LINE.match(line):
                nodes[int(match.group(1))] = match.group(3)
                paths[int(match.group(1))] = match.group(2)
            elif match := _REGISTRY_LINE.match(line):
                registry[match.group(1)] = match.group(2)
        feedback = [message.content for message in messages[2:] if message.role == "user"]
        return cls(nodes, paths, registry, feedback)

    def has(self, prefix: str) -> bool:
        return any(text.startswith(prefix) for text in self.nodes.values())

    def node(self, prefix: str, occurrence: int = 0) -> int:
        matches = [node_id for node_id, text in self.nodes.items() if text.startswith(prefix)]
        return matches[occurrence]

    def key(self, name: str) -> str:
        return next(key for key, value in self.registry.items() if value == name)


def src(node_id: int, quote: str, *supports: str) -> dict[str, Any]:
    """One source of an answer."""
    return {"node_id": node_id, "quote": quote, "supports": list(supports)}


def mention(
    ref: str,
    name: str,
    entity_type: str,
    sources: list[dict[str, Any]],
    parent: dict[str, Any] | None = None,
    **extra: Any,
) -> Answer:
    """One mention of an answer; the parent defaults to unknown, the category follows the type."""
    return {
        "ref": ref,
        "name": name,
        "type": entity_type,
        "category": extra.pop("category", CATEGORY_BY_TYPE[entity_type]),
        "sources": sources,
        "parent": parent or {"status": "unknown"},
        **extra,
    }


def resolved(ref: str, *sources: dict[str, Any]) -> dict[str, Any]:
    """A resolved parent."""
    return {"status": "resolved", "ref": ref, "sources": list(sources)}


def relation(from_ref: str, to_ref: str, relation_type: str, *sources: dict[str, Any], **extra: Any) -> Answer:
    """One relation of an answer."""
    return {"from": from_ref, "to": to_ref, "type": relation_type, "sources": list(sources), **extra}


NONE: Answer = {"block_status": "none"}
EMPTY_REVIEW: Answer = {"merges": [], "parent_updates": [], "unresolved": []}

Rule = Callable[[View], Answer | None]


class ScriptedModel:
    """Stage 1 from recordings; stage 2 blocks by the first matching rule, reviews by ``review``."""

    def __init__(self, rules: list[Rule], review: Callable[[View], Answer] | None = None) -> None:
        self.rules = rules
        self.review = review or (lambda _view: EMPTY_REVIEW)
        self.conversations: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        self.conversations.append(list(messages))
        system = messages[0].content
        if system == BLOCK_SYSTEM_PROMPT:
            view = View.of(messages)
            answer = next((found for rule in self.rules if (found := rule(view)) is not None), NONE)
            return json.dumps(answer, ensure_ascii=False)
        if system == CONSOLIDATION_SYSTEM_PROMPT:
            return json.dumps(self.review(View.of(messages)), ensure_ascii=False)
        return answer_by_edition(messages)

    def stage2_conversations(self) -> list[list[Message]]:
        return [c for c in self.conversations if c[0].content in (BLOCK_SYSTEM_PROMPT, CONSOLIDATION_SYSTEM_PROMPT)]


def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'entities.sqlite3').as_posix()}")
    create_schema(engine)
    return sessionmaker(engine, expire_on_commit=False)


def parsed_document(factory: sessionmaker[Session], edition: int) -> int:
    """Register and parse a test edition with the recorded stage 1 answer; return its id."""
    with factory() as session:
        path = edition_path(edition)
        document = register(session, path.name, path.read_bytes(), DocSet.AFTER)
        parse_document(session, document.id, RecordedProfiler(answer_by_edition), 150_000, 0)
        return document.id


# -- control answers for the test editions --------------------------------------------------


def ed9_general(view: View) -> Answer | None:
    """Ed. 9 п. 1.1–1.5: БВА, Главный аудитор, Совет директоров."""
    if not view.has("1.4. Руководство БВА"):
        return None
    intro, head, board = view.node("1.1."), view.node("1.4."), view.node("1.5.")
    return {
        "block_status": "found",
        "mentions": [
            mention(
                "n1",
                "Блок внутреннего аудита",
                "блок",
                [src(intro, "Блока внутреннего аудита Общества (далее - БВА)", "name", "type", "category")],
                aliases=["БВА"],
            ),
            mention(
                "n2",
                "Главный аудитор",
                "должность",
                [src(head, "Главный аудитор", "name", "type", "category")],
                resolved("n1", src(head, "Руководство БВА осуществляет Главный аудитор", "parent")),
            ),
            mention(
                "n3",
                "Совет директоров",
                "орган управления",
                [src(board, "Совета директоров", "name", "type", "category")],
            ),
        ],
        "relations": [
            relation(
                "n2",
                "n3",
                "functional_subordination",
                src(board, "Главный аудитор находится в функциональном подчинении Совета директоров", "relation"),
            ),
        ],
    }


def _ed9_staff(view: View, clause: str, unit: str, director: str) -> list[Answer]:
    intro = view.node(clause)
    auditor = next(node for node, text in view.nodes.items() if node > intro and text == "в. Аудитор.")
    return [
        mention(
            f"a_{unit}",
            "Аудитор",
            "должность",
            [src(auditor, "Аудитор", "name", "type", "category")],
            resolved(unit, src(intro, f"работники {unit} в соответствии со штатным расписанием", "parent")),
        ),
        relation(f"a_{unit}", director, "reports_to", src(intro, f"Директору {unit} подчиняются", "relation")),
    ]


def ed9_structure(view: View) -> Answer | None:
    """Ed. 9 п. 3.4–3.7: departments from 3.4; their positions from the intro phrases of 3.6 and 3.7."""
    if not view.has("3.4. БВА состоит"):
        return None
    bva, chief = view.key("Блок внутреннего аудита"), view.key("Главный аудитор")
    listing, subordinates = view.node("3.4."), view.node("3.5.")
    in_bva = src(listing, "БВА состоит из следующих структурных подразделений", "parent")
    departments = [
        ("ДИТААД", "Департамент ИТ-аудита и анализа данных", "а. Департамент ИТ"),
        ("ДОА", "Департамент операционного аудита", "б. Департамент операционного"),
    ]
    mentions = [
        mention(
            bva,
            "Блок внутреннего аудита",
            "блок",
            [src(listing, "БВА", "name", "type", "category")],
            aliases=["БВА"],
        ),
        mention(
            "workers",
            "работники БВА",
            "группа работников",
            [src(subordinates, "работники БВА", "name", "type", "category")],
        ),
    ]
    relations = []
    for abbreviation, name, prefix in departments:
        item = view.node(prefix)
        director = f"d_{abbreviation}"
        mentions += [
            mention(
                abbreviation,
                name,
                "департамент",
                [src(item, f"{name} ({abbreviation})", "name", "type", "category")],
                resolved(bva, in_bva),
                aliases=[abbreviation],
            ),
            mention(
                director,
                f"Директор {abbreviation}",
                "должность",
                [
                    src(
                        view.node(f"{prefix[:2]} Директор {abbreviation}"),
                        f"Директор {abbreviation}",
                        "name",
                        "type",
                        "category",
                    )
                ],
                resolved(abbreviation, src(view.node(f"{prefix[:2]} Директор {abbreviation}"), abbreviation, "parent")),
            ),
        ]
        relations.append(relation(director, chief, "reports_to", src(subordinates, "Главному аудитору", "relation")))
    for clause, abbreviation in (("3.6.", "ДИТААД"), ("3.7.", "ДОА")):
        auditor, reports = _ed9_staff(view, clause, abbreviation, f"d_{abbreviation}")
        mentions.append(auditor)
        relations.append(reports)
    return {"block_status": "found", "mentions": mentions, "relations": relations}


def ed8_structure(view: View) -> Answer | None:
    """Ed. 8 п. 3.4–3.8: «Директор проектов ДККМ» is one position with a parent and a functional relation."""
    if not view.has("3.6. Директору направления внутреннего аудита"):
        return None
    functional, staff = view.node("3.6."), view.node("3.8.")
    listed = [node for node, text in view.nodes.items() if text.endswith("Директор проектов ДККМ.")]
    return {
        "block_status": "found",
        "mentions": [
            mention(
                "dkkm",
                "Департамент контроля качества аудита и методологии",
                "департамент",
                [
                    src(
                        view.node("б. Департамент контроля"),
                        "Департамент контроля качества аудита и методологии (ДККМ)",
                        "name",
                        "type",
                        "category",
                    )
                ],
                aliases=["ДККМ"],
            ),
            mention(
                "dnva",
                "Директор направления внутреннего аудита",
                "должность",
                [
                    src(
                        view.node("а. Директор направления внутреннего"),
                        "Директор направления внутреннего аудита",
                        "name",
                        "type",
                        "category",
                    )
                ],
            ),
            mention(
                "dp",
                "Директор проектов ДККМ",
                "должность",
                [src(node, "Директор проектов ДККМ", "name", "type", "category") for node in listed],
                resolved("dkkm", src(staff, "работники ДККМ в соответствии со штатным расписанием", "parent")),
            ),
        ],
        "relations": [
            relation(
                "dp",
                "dnva",
                "functional_subordination",
                src(functional, "подчиняются работники БВА функционально в рамках Плана работ БВА", "relation"),
                conditions="функционально в рамках Плана работ БВА",
            ),
        ],
    }
