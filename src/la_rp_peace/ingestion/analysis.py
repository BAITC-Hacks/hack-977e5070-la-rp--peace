"""Profile a document with the model, verify the answer against the text, retry with feedback.

One attempt = model answer → metadata schema → profile compilation and self-checks → tree
built on the whole document → tree checks → metadata quotes verified. Problems are sent back
to the model (methodology §2: targeted refinement) until the answer passes or the retry
budget is spent; the best attempt is kept and its remaining problems become issues.

Numbering gaps are advisories: usually a clause glued into the previous paragraph that the
profile did not split (e.g. «…мероприятий. 10.Контроль качества»), but documents may skip
numbers for real. They are sent back once; if the next answer shows the same gaps, they are
accepted as genuine instead of spending the remaining retries.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from la_rp_peace.enums import IssueType, ParseStatus
from la_rp_peace.ingestion.checks import check_tree
from la_rp_peace.ingestion.extract.types import Extraction
from la_rp_peace.ingestion.metadata import DocumentMetadata, MetadataResult, apply_metadata
from la_rp_peace.ingestion.profile import CompiledProfile, ProfileError, compile_profile
from la_rp_peace.ingestion.profiler import Profiler
from la_rp_peace.ingestion.prompt import Message, document_view, feedback_message, initial_messages
from la_rp_peace.ingestion.tree import IssueDraft, ParsedNode, ProfileRuntimeError, build_tree
from la_rp_peace.logging_config import get_logger

log = get_logger(__name__)

_GAP_ADVICE = (
    " — возможно, пункт склеен с предыдущим текстом и не распознан (проверьте inline-шаблоны"
    " и одноуровневые номера вроде «10.Текст»); если в документе номер действительно пропущен,"
    " оставьте профиль как есть"
)


@dataclass(slots=True)
class Attempt:
    """Everything produced from one model answer."""

    errors: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    profile: dict[str, Any] | None = None
    nodes: list[ParsedNode] = field(default_factory=list)
    tree_issues: list[IssueDraft] = field(default_factory=list)
    metadata: MetadataResult | None = None


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """The accepted (or best) attempt with its final status and issues."""

    profile: dict[str, Any] | None
    nodes: list[ParsedNode]
    issues: list[IssueDraft]
    metadata: MetadataResult | None
    status: ParseStatus


def _decode(content: str) -> dict[str, Any]:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProfileError([f"Ответ не является JSON: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise ProfileError(["Ответ должен быть JSON-объектом"])
    return raw


def _metadata(raw: dict[str, Any], attempt: Attempt, original_text: str) -> None:
    try:
        metadata = DocumentMetadata.model_validate(raw.get("metadata"))
    except ValidationError as exc:
        attempt.errors += [f"metadata.{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()]
        return
    attempt.metadata = apply_metadata(metadata, original_text)
    attempt.errors += [issue.message for issue in attempt.metadata.issues]


def _tree(compiled: CompiledProfile, attempt: Attempt, extraction: Extraction) -> None:
    try:
        attempt.nodes = build_tree(extraction, compiled)
    except ProfileRuntimeError as exc:
        attempt.errors.append(str(exc))
        return
    attempt.tree_issues = check_tree(extraction, attempt.nodes, compiled.profile.strategy)
    attempt.errors += [issue.message for issue in attempt.tree_issues if issue.is_blocking]
    attempt.advisories = [
        issue.message + _GAP_ADVICE for issue in attempt.tree_issues if issue.issue_type is IssueType.NUMBERING_GAP
    ]


def evaluate(content: str, extraction: Extraction) -> Attempt:
    """Check one model answer against the document.

    Args:
        content: The model's reply.
        extraction: The document it describes.

    Returns:
        The attempt; ``errors`` is empty when the answer is fully acceptable.
    """
    attempt = Attempt()
    try:
        raw = _decode(content)
        compiled = compile_profile(raw.get("parsing_profile"))
    except ProfileError as exc:
        attempt.errors = exc.errors
        return attempt
    attempt.profile = compiled.profile.model_dump(mode="json")
    _tree(compiled, attempt, extraction)
    _metadata(raw, attempt, extraction.original_text)
    return attempt


def _result(attempt: Attempt, attempts: int, studied: list[tuple[int, int]]) -> AnalysisResult:
    issues = list(attempt.tree_issues) + (attempt.metadata.issues if attempt.metadata else [])
    if attempt.profile is None or not attempt.nodes:
        summary = "; ".join(attempt.errors[:5])
        issues.append(IssueDraft(IssueType.OTHER, f"Профиль не прошёл проверку за {attempts} попыток: {summary}", True))
    profile = None
    if attempt.profile is not None:
        profile = {**attempt.profile, "studied_ranges": studied, "attempts": attempts}
    blocking = any(issue.is_blocking for issue in issues)
    status = ParseStatus.NEEDS_REVIEW if blocking else ParseStatus.VALIDATED
    return AnalysisResult(profile, attempt.nodes, issues, attempt.metadata, status)


def _rank(attempt: Attempt) -> tuple[bool, int, int]:
    """Prefer an answer that produced a tree, then fewer errors, then fewer advisories."""
    return bool(attempt.nodes), -len(attempt.errors), -len(attempt.advisories)


def _accepted(attempt: Attempt, previous: Attempt | None) -> bool:
    if attempt.errors:
        return False
    return not attempt.advisories or (previous is not None and attempt.advisories == previous.advisories)


def analyse(extraction: Extraction, profiler: Profiler, max_chars: int, retries: int) -> AnalysisResult:
    """Profile, parse and verify one document.

    Args:
        extraction: The extracted document.
        profiler: The model client.
        max_chars: Size limit of the text shown to the model.
        retries: How many corrected answers to request after the first.

    Returns:
        The best attempt with its status.

    Raises:
        ProfilerError: If the model cannot be reached.
    """
    view = document_view(extraction, max_chars)
    messages: list[Message] = initial_messages(view)
    best: Attempt | None = None
    previous: Attempt | None = None
    for number in range(1, retries + 2):
        content = profiler.complete(messages)
        attempt = evaluate(content, extraction)
        log.info("profile_attempt", attempt=number, errors=len(attempt.errors), advisories=len(attempt.advisories))
        if best is None or _rank(attempt) >= _rank(best):
            best = attempt
        if _accepted(attempt, previous):
            return _result(attempt, number, view.studied_ranges)
        messages += [Message("assistant", content), feedback_message(attempt.errors + attempt.advisories)]
        previous = attempt
    if best is None:
        raise ValueError("retries must not be negative")
    return _result(best, retries + 1, view.studied_ranges)
