"""Look up cited nodes and verify quotes against the original text."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from la_rp_peace.api.deps import SessionDep
from la_rp_peace.quotes import QuoteNotFoundError
from la_rp_peace.sources import NodeNotFoundError, SourceRef, resolve_source

router = APIRouter(prefix="/api", tags=["sources"])


class Citation(BaseModel):
    """A citation as produced by the analysis: node id plus the exact cited words."""

    node_id: int
    quote: str


def _resolve(session: SessionDep, node_id: int, quote: str | None) -> SourceRef:
    try:
        return resolve_source(session, node_id, quote)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/nodes/{node_id}", response_model=SourceRef)
def get_node_source(session: SessionDep, node_id: int) -> SourceRef:
    """Return a node as a source reference quoting its whole own text."""
    return _resolve(session, node_id, None)


@router.post("/sources/resolve", response_model=SourceRef)
def resolve_citation(session: SessionDep, citation: Citation) -> SourceRef:
    """Verify that the quote occurs in the node and return where to find it."""
    return _resolve(session, citation.node_id, citation.quote)
