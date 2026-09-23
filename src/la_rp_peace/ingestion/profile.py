"""The AI parsing profile: schema, compilation and self-checks.

The model proposes regular expressions and nesting rules (methodology §2); this module
validates their shape, compiles them with the ``regex`` engine (every match is time-limited,
no model-supplied code is ever executed) and runs the model's own positive and negative
examples. Anything wrong is reported as a list of messages that is fed back to the model.
"""

from dataclasses import dataclass
from typing import Literal

import regex
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REGEX_TIMEOUT_SECONDS = 0.05
MARKER_GROUP = "marker"

Hierarchy = Literal["marker_depth", "fixed_level", "list"]
ServiceKind = Literal["front_matter", "toc", "page_number", "other"]
_FLAGS = {"IGNORECASE": regex.IGNORECASE}


class PatternRule(BaseModel):
    """A structural marker the document uses (clause numbers, list letters, articles…)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    node_type: Literal["clause", "list_item"]
    regex: str = Field(min_length=1)
    flags: list[Literal["IGNORECASE"]] = []
    apply_to: Literal["block_start", "inline"]
    hierarchy: Hierarchy
    level: int | None = Field(default=None, ge=1)
    priority: int = 0
    positive_examples: list[str] = Field(min_length=1)
    negative_examples: list[str] = []


class ServiceRule(BaseModel):
    """Text that is not content: approval stamp and title, table of contents, page numbers."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: ServiceKind
    start_regex: str | None = None
    entry_regex: str | None = None
    flags: list[Literal["IGNORECASE"]] = []


class ParsingProfile(BaseModel):
    """Parser configuration proposed by the model for one document."""

    model_config = ConfigDict(extra="forbid")

    profile_version: Literal[1]
    regex_engine: Literal["python_re"]
    strategy: Literal["numbering", "formatting", "table", "mixed"]
    patterns: list[PatternRule] = []
    heading_styles: list[str] = []
    service_rules: list[ServiceRule] = []
    unresolved: list[str] = []


class ProfileError(ValueError):
    """The profile is malformed or fails its own checks; ``errors`` are fed back to the model."""

    def __init__(self, errors: list[str]) -> None:
        """Keep the individual messages."""
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class CompiledPattern:
    """A pattern rule with its compiled expression."""

    rule: PatternRule
    compiled: regex.Pattern[str]

    def match_start(self, text: str) -> regex.Match[str] | None:
        """Match at the start of a block."""
        return self.compiled.match(text, timeout=REGEX_TIMEOUT_SECONDS)

    def find_inline(self, text: str) -> list[regex.Match[str]]:
        """Find occurrences inside a block."""
        return list(self.compiled.finditer(text, timeout=REGEX_TIMEOUT_SECONDS))


@dataclass(frozen=True, slots=True)
class CompiledService:
    """A service rule with its compiled expressions."""

    rule: ServiceRule
    start: regex.Pattern[str] | None
    entry: regex.Pattern[str] | None

    def starts(self, text: str) -> bool:
        """Tell whether a block opens (or is) this service block."""
        return self.start is not None and self.start.search(text, timeout=REGEX_TIMEOUT_SECONDS) is not None

    def continues(self, text: str) -> bool:
        """Tell whether a block is an entry of an open service block (e.g. a TOC line)."""
        return self.entry is not None and self.entry.search(text, timeout=REGEX_TIMEOUT_SECONDS) is not None


@dataclass(frozen=True, slots=True)
class CompiledProfile:
    """A validated profile ready for the tree engine."""

    profile: ParsingProfile
    block_patterns: tuple[CompiledPattern, ...]
    inline_patterns: tuple[CompiledPattern, ...]
    services: tuple[CompiledService, ...]
    heading_styles: frozenset[str]

    def service(self, kind: ServiceKind) -> tuple[CompiledService, ...]:
        """Return the service rules of one kind."""
        return tuple(service for service in self.services if service.rule.kind == kind)


def _compile(
    expression: str, flags: list[Literal["IGNORECASE"]], owner: str, errors: list[str]
) -> regex.Pattern[str] | None:
    combined = 0
    for flag in flags:
        combined |= _FLAGS[flag]
    try:
        return regex.compile(expression, combined)
    except regex.error as exc:
        errors.append(f"{owner}: регулярное выражение не компилируется ({exc})")
        return None


def _check_examples(pattern: CompiledPattern, errors: list[str]) -> None:
    rule = pattern.rule

    def hits(example: str) -> bool:
        if rule.apply_to == "block_start":
            return pattern.match_start(example) is not None
        return bool(pattern.find_inline(example))

    errors.extend(f"{rule.id}: положительный пример не совпал: «{ex}»" for ex in rule.positive_examples if not hits(ex))
    errors.extend(f"{rule.id}: отрицательный пример совпал: «{ex}»" for ex in rule.negative_examples if hits(ex))


def _compile_pattern(rule: PatternRule, errors: list[str]) -> CompiledPattern | None:
    compiled = _compile(rule.regex, rule.flags, rule.id, errors)
    if compiled is None:
        return None
    if MARKER_GROUP not in compiled.groupindex:
        errors.append(f"{rule.id}: нет именованной группы (?P<{MARKER_GROUP}>…)")
        return None
    if rule.hierarchy == "fixed_level" and rule.level is None:
        errors.append(f"{rule.id}: для fixed_level нужен level")
    pattern = CompiledPattern(rule, compiled)
    try:
        _check_examples(pattern, errors)
    except TimeoutError:
        errors.append(f"{rule.id}: регулярное выражение работает слишком долго")
    return pattern


def _compile_service(rule: ServiceRule, errors: list[str]) -> CompiledService:
    if rule.kind in ("toc", "page_number", "other") and rule.start_regex is None:
        errors.append(f"{rule.id}: для {rule.kind} нужен start_regex")
    start = _compile(rule.start_regex, rule.flags, rule.id, errors) if rule.start_regex else None
    entry = _compile(rule.entry_regex, rule.flags, rule.id, errors) if rule.entry_regex else None
    return CompiledService(rule, start, entry)


def compile_profile(raw: object) -> CompiledProfile:
    """Validate and compile a profile returned by the model.

    Args:
        raw: The ``parsing_profile`` JSON object.

    Returns:
        The compiled profile.

    Raises:
        ProfileError: With every problem found, for feedback to the model.
    """
    try:
        profile = ParsingProfile.model_validate(raw)
    except ValidationError as exc:
        raise ProfileError([f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()]) from exc
    errors: list[str] = []
    ordered = sorted(profile.patterns, key=lambda rule: -rule.priority)
    patterns = [compiled for rule in ordered if (compiled := _compile_pattern(rule, errors)) is not None]
    services = tuple(_compile_service(rule, errors) for rule in profile.service_rules)
    if errors:
        raise ProfileError(errors)
    return CompiledProfile(
        profile=profile,
        block_patterns=tuple(p for p in patterns if p.rule.apply_to == "block_start"),
        inline_patterns=tuple(p for p in patterns if p.rule.apply_to == "inline"),
        services=services,
        heading_styles=frozenset(style.casefold() for style in profile.heading_styles),
    )
