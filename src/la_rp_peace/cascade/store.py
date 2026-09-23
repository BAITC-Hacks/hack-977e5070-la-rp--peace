"""Saving stage 4.2: a run replaces every previous cascade row of the document in one transaction."""

import json
from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from la_rp_peace.cascade.findings import Finding
from la_rp_peace.cascade.groups import Structure, entity_of
from la_rp_peace.cascade.links import LinkResult
from la_rp_peace.embeddings import METRIC, TEXT_FORMAT
from la_rp_peace.enums import CascadeFindingKind
from la_rp_peace.models import CascadeFinding, CascadeGroup, CascadeLink


def clear_cascade(session: Session, document_id: int) -> None:
    """Delete the document's cascade rows (the caller commits)."""
    for model in (CascadeFinding, CascadeLink, CascadeGroup):
        session.execute(delete(model).where(model.document_id == document_id))


def _link_row(document_id: int, group_id: int, link: LinkResult, embedding_model: str) -> CascadeLink:
    choice = link.choice
    return CascadeLink(
        document_id=document_id,
        group_id=group_id,
        child_entity_id=entity_of(choice.child),
        child_record_id=choice.child.id,
        parent_record_id=choice.parent_record_id,
        best_similarity=choice.similarity,
        decision=link.decision.value,
        verdict=link.verdict.value if link.verdict is not None else None,
        explanation=link.explanation,
        status=link.status.value,
        error=link.error,
        attempts=link.attempts,
        tied_record_ids=json.dumps(list(choice.tied_record_ids)),
        embedding_model=embedding_model,
        metric=METRIC,
        text_format=TEXT_FORMAT,
    )


def save_cascade(
    session: Session,
    document_id: int,
    structure: Structure,
    links: Sequence[LinkResult],
    findings: Sequence[Finding],
    embedding_model: str,
) -> None:
    """Replace the document's groups, links and findings (the caller commits).

    Args:
        session: Database session.
        document_id: The document.
        structure: Its groups.
        links: One decision per child function.
        findings: The signs for review.
        embedding_model: Model of the similarity scores, stored with every link.
    """
    clear_cascade(session, document_id)
    group_ids: dict[int, int] = {}
    for group in structure.groups:
        row = CascadeGroup(
            document_id=document_id,
            entity_id=group.entity.id,
            child_entity_ids=json.dumps([child.id for child in group.children]),
            parent_record_ids=json.dumps([record.id for record in group.parent_records]),
            child_record_ids=json.dumps([record.id for record in group.child_records]),
            uncertain_entity_ids=json.dumps(list(group.uncertain_entity_ids)),
        )
        session.add(row)
        session.flush()
        group_ids[group.entity.id] = row.id
    link_ids: dict[int, int] = {}
    for link in links:
        link_row = _link_row(document_id, group_ids[link.choice.group.entity.id], link, embedding_model)
        session.add(link_row)
        session.flush()
        link_ids[link.choice.child.id] = link_row.id
    session.add_all(
        CascadeFinding(
            document_id=document_id,
            kind=finding.kind.value,
            reason=finding.reason.value,
            final=int(finding.final),
            record_id=finding.record_id,
            entity_id=finding.entity_id,
            group_id=group_ids[finding.group_entity_id] if finding.group_entity_id is not None else None,
            link_id=link_ids[finding.record_id] if finding.kind is CascadeFindingKind.CHILD_WITHOUT_PARENT else None,
            message=finding.message,
        )
        for finding in findings
    )
