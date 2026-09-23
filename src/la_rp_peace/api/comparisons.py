"""Stage 5.2 over HTTP: start a before -> after comparison and read its JobResult."""

import json
import threading
from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from la_rp_peace.api.deps import SessionDep, SettingsDep
from la_rp_peace.comparison.job import comparison_job
from la_rp_peace.models import Comparison, Document

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


class ComparisonIn(BaseModel):
    """Documents of both sides (one or more each)."""

    before_ids: list[int] = Field(min_length=1)
    after_ids: list[int] = Field(min_length=1)


class ComparisonOut(BaseModel):
    """A comparison run; ``result`` is the frontend JobResult once done."""

    id: int
    before_ids: list[int]
    after_ids: list[int]
    status: str
    error: str | None
    created_at: str
    result: dict[str, Any] | None


def _out(row: Comparison) -> ComparisonOut:
    return ComparisonOut(
        id=row.id,
        before_ids=json.loads(row.before_ids),
        after_ids=json.loads(row.after_ids),
        status=row.status,
        error=row.error,
        created_at=row.created_at,
        result=json.loads(row.result) if row.result else None,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ComparisonOut)
def start_comparison(request: Request, session: SessionDep, settings: SettingsDep, body: ComparisonIn) -> ComparisonOut:
    """Start a comparison once both sides are analysed; poll GET /{id} until status is done / needs_review / failed."""
    queue = request.app.state.parsing_queue
    embedder = request.app.state.embedder
    model = request.app.state.chat_model
    if queue is None or embedder is None or model is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Сравнение недоступно: не заданы OPENAI_API_KEY и OPENAI_MODEL"
        )
    for document_id in [*body.before_ids, *body.after_ids]:
        if session.get(Document, document_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Документ {document_id} не найден")
    row = Comparison(before_ids=json.dumps(body.before_ids), after_ids=json.dumps(body.after_ids), status="pending")
    session.add(row)
    session.commit()
    factory = request.app.state.session_factory
    # Own thread, not the parsing workers: the job waits for the documents' chains on those workers.
    job = partial(comparison_job, factory, row.id, model, embedder, settings.analysis_retries)
    threading.Thread(target=job, name=f"comparison-{row.id}", daemon=True).start()
    return _out(row)


@router.get("", response_model=list[ComparisonOut])
def list_comparisons(session: SessionDep) -> list[ComparisonOut]:
    """All comparisons, newest first (results included)."""
    rows = session.query(Comparison).order_by(Comparison.id.desc()).all()
    return [_out(row) for row in rows]


@router.get("/{comparison_id}", response_model=ComparisonOut)
def get_comparison(session: SessionDep, comparison_id: int) -> ComparisonOut:
    """Status and, when finished, the JobResult."""
    row = session.get(Comparison, comparison_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сравнение не найдено")
    return _out(row)
