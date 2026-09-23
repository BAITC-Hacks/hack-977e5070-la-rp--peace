"""Persisted stage 5.1 comparisons, separate from each document's extracted data."""

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from la_rp_peace.api.deps import SessionDep
from la_rp_peace.document_diff import compare, prepare
from la_rp_peace.models import utc_timestamp

router = APIRouter(prefix="/api/document-diffs", tags=["document-diffs"])
_DDL = """CREATE TABLE IF NOT EXISTS document_diffs (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
    before_document_id INTEGER NOT NULL, after_document_id INTEGER NOT NULL,
    result TEXT NOT NULL CHECK(json_valid(result))
)"""


class ConfirmedGroup(BaseModel):
    """Explicitly reviewed fragment group; IDs come from an earlier comparison."""

    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=2000)


class DiffRequest(BaseModel):
    """An explicit, user-confirmed pair and optional confirmed fragment groups."""

    before_document_id: int
    after_document_id: int
    confirmed: bool = False
    reason: str = Field(default="Пара и порядок выбраны пользователем", min_length=1, max_length=2000)
    groups: list[ConfirmedGroup] = Field(default_factory=list)
    before_fingerprint: str | None = None
    after_fingerprint: str | None = None


@router.post("", status_code=201)
def create_diff(session: SessionDep, request: DiffRequest) -> dict[str, Any]:
    """Save a new immutable comparison; a rerun never overwrites the previous result."""
    if not request.confirmed:
        raise HTTPException(409, "Подтвердите пару и порядок редакций: confirmed=true")
    if request.before_document_id == request.after_document_id:
        raise HTTPException(422, "Нужны два разных документа")
    try:
        before = prepare(session, request.before_document_id)
        after = prepare(session, request.after_document_id)
        if request.groups and (
            request.before_fingerprint != before["fingerprint"] or request.after_fingerprint != after["fingerprint"]
        ):
            raise HTTPException(409, "Для подтверждения групп нужны актуальные fingerprint обеих редакций")
        result = compare(before, after, [group.model_dump() for group in request.groups])
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result.update(
        comparison_id=str(uuid4()),
        created_at=utc_timestamp(),
        pair_selection={"confirmed": True, "method": "user", "reason": request.reason},
    )
    session.execute(text(_DDL))
    session.execute(
        text("INSERT INTO document_diffs VALUES (:id, :created, :before, :after, :result)"),
        {
            "id": result["comparison_id"],
            "created": result["created_at"],
            "before": request.before_document_id,
            "after": request.after_document_id,
            "result": json.dumps(result, ensure_ascii=False),
        },
    )
    session.commit()
    return result


@router.get("/{comparison_id}")
def get_diff(session: SessionDep, comparison_id: str) -> dict[str, Any]:
    """Return saved text and mark results stale when their extraction changes."""
    session.execute(text(_DDL))
    stored = session.execute(
        text("SELECT result FROM document_diffs WHERE id=:id"), {"id": comparison_id}
    ).scalar_one_or_none()
    if stored is None:
        raise HTTPException(404, "Сравнение не найдено")
    result: dict[str, Any] = json.loads(stored)
    result["stale"] = False
    for side in ("before", "after"):
        try:
            current = prepare(session, result[side]["document_id"])
            if current["fingerprint"] != result[side]["fingerprint"]:
                result["stale"] = True
        except (LookupError, ValueError):
            result["stale"] = True
    if result["stale"]:
        result["status"] = "stale"
    return result
