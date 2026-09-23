"""Stage 5.1: conservative text correspondence and exact, source-addressed diffs."""

import hashlib
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from la_rp_peace.models import Document, DocumentNode
from la_rp_peace.navigation import describe

VERSION = "document-diff-v1"
LIMITATIONS = [
    "Автоматическая проверка ИИ, поиск по смыслу и определение пары редакций ещё не подключены.",
    "Несопоставленный фрагмент требует проверки: это не подтверждённое добавление или удаление.",
    "Сравнивается извлечённый текст; изображения и оформление не сравниваются.",
]


def normalized(text: str, marker: str | None = None) -> str:
    """Remove only a recognized leading marker and technical whitespace."""
    if marker:
        text = re.sub(r"^\s*" + re.escape(marker) + r"(?=$|[.)\s])(?:[.)]?\s*)", "", text, count=1)
    return " ".join(text.split())


def fingerprint(document: Document, nodes: list[DocumentNode]) -> str:
    """Identify the exact extraction, including node identities and metadata."""
    payload = {
        "text": document.original_text,
        "profile": document.parsing_profile,
        "sources": document.source_map,
        "metadata": [document.title, document.revision, document.approved_on, document.effective_from],
        "nodes": [
            [n.id, n.parent_id, n.position, n.node_type, n.marker, n.text, n.source_start, n.source_end] for n in nodes
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _context(node: DocumentNode, by_id: dict[int, DocumentNode]) -> list[DocumentNode]:
    ancestors: list[DocumentNode] = []
    seen = {node.id}
    parent = node.parent_id
    while parent is not None:
        if parent in seen or parent not in by_id:
            raise ValueError("Повреждено дерево документа: цикл или отсутствующий родитель")
        seen.add(parent)
        item = by_id[parent]
        ancestors.append(item)
        parent = item.parent_id
    return list(reversed(ancestors))


def prepare(session: Session, document_id: int) -> dict[str, Any]:
    """Read stage 1 without changing it; retain uncovered source ranges."""
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError(f"Документ {document_id} не найден")
    if not document.original_text:
        raise ValueError(f"Документ {document_id}: текст ещё не извлечён")
    nodes = list(session.scalars(select(DocumentNode).where(DocumentNode.document_id == document_id)))
    by_id = {node.id: node for node in nodes}
    contexts = {node.id: _context(node, by_id) for node in nodes}
    places = describe(nodes, json.loads(document.source_map))
    fragments: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor = 0
    original = document.original_text
    for node in sorted(nodes, key=lambda item: (item.source_start, item.id)):
        if not node.text:
            continue
        start, end = node.source_start, node.source_start + len(node.text)
        if start < cursor or original[start:end] != node.text:
            warnings.append(f"Узел {node.id}: нет надёжного собственного диапазона")
            continue
        if start > cursor:
            fragments.append(_fragment(document_id, cursor, start, original, None))
        part = _fragment(document_id, start, end, original, node)
        part.update(
            path=places[node.id].path,
            location=places[node.id].location,
            context=[
                {"node_id": p.id, "text": p.text, "normalized": normalized(p.text, p.marker)} for p in contexts[node.id]
            ],
        )
        fragments.append(part)
        cursor = end
    if cursor < len(original):
        fragments.append(_fragment(document_id, cursor, len(original), original, None))
    if any(f["node_id"] is None and f["text"].strip() for f in fragments):
        warnings.append("Часть текста сравнивается по исходным диапазонам без структуры")
    if document.parse_status != "validated":
        warnings.append(f"Статус парсинга: {document.parse_status}; полнота извлечения требует проверки")
    return {
        "document_id": document.id,
        "name": document.file_name,
        "title": document.title,
        "revision": document.revision,
        "approved_on": document.approved_on,
        "effective_from": document.effective_from,
        "metadata_evidence": json.loads(document.metadata_evidence),
        "fingerprint": fingerprint(document, nodes),
        "original_text": original,
        "fragments": fragments,
        "warnings": warnings,
    }


def _fragment(doc_id: int, start: int, end: int, text: str, node: DocumentNode | None) -> dict[str, Any]:
    return {
        "id": f"{doc_id}:{start}:{end}",
        "document_id": doc_id,
        "node_id": node.id if node is not None else None,
        "start": start,
        "end": end,
        "text": text[start:end],
        "marker": node.marker if node is not None else None,
        "normalized": normalized(text[start:end], node.marker if node is not None else None),
        "path": "Исходный диапазон",
        "location": {},
        "context": [],
    }


def _context_key(fragment: dict[str, Any]) -> tuple[str, ...]:
    return tuple(item["normalized"] for item in fragment["context"] if item["normalized"])


def _indices(parts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for part in parts:
        if part["normalized"]:
            result[part["normalized"]].append(part)
    return result


def _segments(parts: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    spans = []
    offset = 0
    for part in parts:
        low, high = max(start, offset), min(end, offset + len(part["text"]))
        if high > low:
            spans.append(
                {
                    "fragment_id": part["id"],
                    "document_id": part["document_id"],
                    "node_id": part["node_id"],
                    "start": part["start"] + low - offset,
                    "end": part["start"] + high - offset,
                    "text": part["text"][low - offset : high - offset],
                }
            )
        offset += len(part["text"])
    return spans


def _text_diff(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    left = "".join(part["text"] for part in before)
    right = "".join(part["text"] for part in after)
    # Word/punctuation/whitespace tokens keep exact text and avoid quadratic character diffs.
    a, b = re.findall(r"\w+|[^\w\s]|\s+", left), re.findall(r"\w+|[^\w\s]|\s+", right)
    offsets_a, offsets_b = [0], [0]
    for token in a:
        offsets_a.append(offsets_a[-1] + len(token))
    for token in b:
        offsets_b.append(offsets_b[-1] + len(token))
    return [
        {
            "operation": kind,
            "before": _segments(before, offsets_a[i], offsets_a[j]),
            "after": _segments(after, offsets_b[k], offsets_b[stop]),
        }
        for kind, i, j, k, stop in SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    ]


def _block(before: list[dict[str, Any]], after: list[dict[str, Any]], method: str, reason: str) -> dict[str, Any]:
    flags: list[str] = []
    if len(before) == 1 and len(after) > 1:
        flags.append("split")
    elif len(before) > 1 and len(after) == 1:
        flags.append("merged")
    elif len(before) > 1 and len(after) > 1:
        flags.append("reworked")
    if before and after:
        left = " ".join(p["normalized"] for p in before)
        right = " ".join(p["normalized"] for p in after)
        if left != right:
            flags.append("modified")
        if [p["marker"] for p in before] != [p["marker"] for p in after]:
            flags.append("renumbered")
        if [p["text"] for p in before] != [p["text"] for p in after] and not flags:
            flags.append("modified")
    else:
        flags.append("added" if after else "deleted")
    return {
        "before": before,
        "after": after,
        "flags": flags or ["unchanged"],
        "review_status": "accepted",
        "method": method,
        "reason": reason,
        "diff": _text_diff(before, after),
        "candidates": [],
    }


def _manual_groups(
    groups: list[dict[str, Any]], before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    blocks: list[dict[str, Any]] = []
    used_before: set[str] = set()
    used_after: set[str] = set()
    for group in groups:
        a, b = group["before"], group["after"]
        if not a and not b:
            raise ValueError("Пустая группа соответствия")
        if len(set(a)) != len(a) or len(set(b)) != len(b):
            raise ValueError("Повтор диапазона внутри группы")
        if not set(a) <= before.keys() or not set(b) <= after.keys():
            raise ValueError("Диапазон не принадлежит выбранной стороне")
        if used_before.intersection(a) or used_after.intersection(b):
            raise ValueError("Противоречащие соответствия: диапазон используется повторно")
        used_before.update(a)
        used_after.update(b)
        left = sorted((before[key] for key in a), key=lambda p: p["start"])
        right = sorted((after[key] for key in b), key=lambda p: p["start"])
        blocks.append(_block(left, right, "user_confirmed", group["reason"]))
    return blocks, used_before, used_after


def _movements(blocks: list[dict[str, Any]]) -> None:
    paired = [b for b in blocks if len(b["before"]) == len(b["after"]) == 1]
    before = sorted(paired, key=lambda b: b["before"][0]["start"])
    after = sorted(paired, key=lambda b: b["after"][0]["start"])
    a, b = [id(item) for item in before], [id(item) for item in after]
    stable = {
        a[i]
        for match in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
        for i in range(match.a, match.a + match.size)
    }
    moved = [
        item
        for item in paired
        if id(item) not in stable or _context_key(item["before"][0]) != _context_key(item["after"][0])
    ]
    moved_nodes = {item["before"][0]["node_id"] for item in moved}
    for item in moved:
        ancestors = {p["node_id"] for p in item["before"][0]["context"]}
        flag = "moved_with_parent" if ancestors.intersection(moved_nodes) else "moved"
        item["flags"] = [f for f in item["flags"] if f != "unchanged"] + [flag]


def compare(before: dict[str, Any], after: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Accept unique contextual matches or user-reviewed groups; keep the rest unresolved."""
    left = {p["id"]: p for p in before["fragments"] if p["text"].strip()}
    right = {p["id"]: p for p in after["fragments"] if p["text"].strip()}
    blocks, used_left, used_right = _manual_groups(groups, left, right)
    indices_a, indices_b = _indices(list(left.values())), _indices(list(right.values()))
    for text, candidates in indices_a.items():
        others = indices_b.get(text, [])
        if len(candidates) != 1 or len(others) != 1:
            continue
        a, b = candidates[0], others[0]
        if a["id"] in used_left or b["id"] in used_right or _context_key(a) != _context_key(b):
            continue
        blocks.append(_block([a], [b], "exact_context", "Единственный точный текст с одинаковым вводным контекстом"))
        used_left.add(a["id"])
        used_right.add(b["id"])
    for own, opposite, used, side in ((left, right, used_left, "before"), (right, left, used_right, "after")):
        for key, part in own.items():
            if key not in used:
                blocks.append(_unresolved(part, list(opposite.values()), side))
    _movements(blocks)
    for number, block in enumerate(blocks, 1):
        block["change_id"] = str(number)
    return {
        "status": "needs_review"
        if any(b["review_status"] != "accepted" for b in blocks) or before["warnings"] or after["warnings"]
        else "done",
        "method_version": VERSION,
        "metric": "difflib.SequenceMatcher token ratio; candidate ranking only",
        "before": before,
        "after": after,
        "blocks": blocks,
        "block_count": len(blocks),
        "limitations": LIMITATIONS,
        "offset_unit": "unicode_code_points",
        "complete_semantic_search": False,
    }


def _unresolved(part: dict[str, Any], opposite: list[dict[str, Any]], side: str) -> dict[str, Any]:
    tokens = part["normalized"].split()
    scored = sorted(
        ((SequenceMatcher(None, tokens, p["normalized"].split(), autojunk=False).ratio(), p) for p in opposite),
        key=lambda item: (-item[0], item[1]["start"]),
    )[:5]
    return {
        "before": [part] if side == "before" else [],
        "after": [part] if side == "after" else [],
        "flags": [],
        "review_status": "needs_review",
        "method": "candidate_search",
        "reason": "Нужна проверка переноса, переформулировки, разделения или объединения",
        "diff": [],
        "candidates": [{"fragment_id": p["id"], "score": score} for score, p in scored],
    }
