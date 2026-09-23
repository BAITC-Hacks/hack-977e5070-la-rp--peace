"""Look up cited clauses and verify quotes against the original text."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from la_rp_peace.api.deps import SessionDep
from la_rp_peace.sources import ClauseNotFoundError, QuoteNotFoundError, SourceRef, resolve_source

router = APIRouter(prefix="/api", tags=["sources"])


class Citation(BaseModel):
    """A citation as produced by the analysis: clause id plus the exact cited words."""

    clause_id: str
    quote: str


def _resolve(session: SessionDep, clause_id: str, quote: str | None) -> SourceRef:
    try:
        return resolve_source(session, clause_id, quote)
    except ClauseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/clauses/{clause_id}", response_model=SourceRef)
def get_clause_source(session: SessionDep, clause_id: str) -> SourceRef:
    """Return a clause as a source reference quoting its whole text."""
    return _resolve(session, clause_id, None)


@router.post("/sources/resolve", response_model=SourceRef)
def resolve_citation(session: SessionDep, citation: Citation) -> SourceRef:
    """Verify that the quote occurs in the clause and return where to find it."""
    return _resolve(session, citation.clause_id, citation.quote)
