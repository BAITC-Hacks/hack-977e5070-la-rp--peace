"""Turn the model's metadata answer into the document card (methodology §0).

A card field is filled only when the model reports it as extracted, every supporting quote
occurs verbatim in ``original_text``, and dates are valid ``YYYY-MM-DD``. Everything else
stays NULL; ``metadata_evidence`` records the status, the quotes with their ranges, or the
reason a value was rejected.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from la_rp_peace.enums import IssueType
from la_rp_peace.ingestion.tree import IssueDraft
from la_rp_peace.quotes import find_quote

CARD_FIELDS = (
    "title",
    "document_type",
    "organization",
    "revision",
    "approved_by",
    "approval_document_type",
    "approval_number",
    "document_created_on",
    "approved_on",
    "effective_from",
)
DATE_FIELDS = frozenset({"document_created_on", "approved_on", "effective_from"})


class MetadataValue(BaseModel):
    """One card field as reported by the model."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["extracted", "not_found", "ambiguous"]
    value: str | None = None
    quotes: list[str] = []
    reason: str | None = None


class ExtraMetadata(BaseModel):
    """A document attribute outside the card, e.g. the condition for entering into force."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    quotes: list[str] = Field(min_length=1)


class DocumentMetadata(BaseModel):
    """The model's metadata answer: every card field must be reported."""

    model_config = ConfigDict(extra="forbid")

    title: MetadataValue
    document_type: MetadataValue
    organization: MetadataValue
    revision: MetadataValue
    approved_by: MetadataValue
    approval_document_type: MetadataValue
    approval_number: MetadataValue
    document_created_on: MetadataValue
    approved_on: MetadataValue
    effective_from: MetadataValue
    extra: list[ExtraMetadata] = []


@dataclass(frozen=True, slots=True)
class MetadataResult:
    """Card values, their evidence and the problems found."""

    card: dict[str, str | None]
    evidence: dict[str, Any]
    issues: list[IssueDraft]


def _valid_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _locate(original_text: str, quotes: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    located, missing = [], []
    for quote in quotes:
        found = find_quote(original_text, quote)
        if found is None:
            missing.append(quote)
        else:
            located.append({"text": original_text[found[0] : found[1]], "start": found[0], "end": found[1]})
    return located, missing


def _field(name: str, reported: MetadataValue, original_text: str) -> tuple[str | None, dict[str, Any], str | None]:
    """Return the card value, the evidence entry and a rejection reason (None if accepted)."""
    located, missing = _locate(original_text, reported.quotes)
    evidence: dict[str, Any] = {"status": reported.status, "value": reported.value, "quotes": located}
    if reported.reason:
        evidence["reason"] = reported.reason
    if reported.status != "extracted":
        return None, evidence, None
    problem = None
    if not reported.value:
        problem = "значение не указано"
    elif not reported.quotes:
        problem = "нет подтверждающей цитаты"
    elif missing:
        problem = "цитата не найдена в тексте: " + "; ".join(f"«{quote}»" for quote in missing)
    elif name in DATE_FIELDS and not _valid_date(reported.value):
        problem = f"дата «{reported.value}» не в формате YYYY-MM-DD"
    if problem is not None:
        evidence.update(status="ambiguous", reason=problem, rejected_quotes=missing)
        return None, evidence, problem
    return reported.value, evidence, None


def apply_metadata(metadata: DocumentMetadata, original_text: str) -> MetadataResult:
    """Verify the model's metadata against the document text.

    Args:
        metadata: Validated metadata answer.
        original_text: The document's extracted text.

    Returns:
        Card values (NULL unless verified), evidence per field, and non-blocking issues for
        every rejected value.
    """
    card: dict[str, str | None] = {}
    evidence: dict[str, Any] = {}
    issues: list[IssueDraft] = []
    for name in CARD_FIELDS:
        value, entry, problem = _field(name, getattr(metadata, name), original_text)
        card[name] = value
        evidence[name] = entry
        if problem is not None:
            issues.append(IssueDraft(IssueType.OTHER, f"Реквизит {name} не принят: {problem}", False))
    extras = []
    for extra in metadata.extra:
        located, missing = _locate(original_text, extra.quotes)
        if missing:
            issues.append(
                IssueDraft(IssueType.OTHER, f"Дополнительный реквизит «{extra.name}» без подтверждения", False)
            )
            continue
        extras.append({"name": extra.name, "value": extra.value, "quotes": located})
    if extras:
        evidence["extra"] = extras
    return MetadataResult(card=card, evidence=evidence, issues=issues)
