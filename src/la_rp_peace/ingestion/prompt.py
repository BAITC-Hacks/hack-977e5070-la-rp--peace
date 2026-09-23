"""Messages for the profiling call (methodology §2).

The document is shown block by block as ``@<offset> [<style>] <text>`` so the model sees
formatting cues. Documents above the size limit are sampled — beginning, middle, end and
examples of every style — with the skipped ranges marked, so the model never mistakes a
sample for continuous text.
"""

from dataclasses import dataclass

from la_rp_peace.ingestion.extract.types import Extraction, TextBlock
from la_rp_peace.llm import Message

_HEAD_BLOCKS = 80
_TAIL_BLOCKS = 40
_MIDDLE_BLOCKS = 40
_EXAMPLES_PER_STYLE = 3

SYSTEM_PROMPT = """\
You configure a document parser. You receive the extracted text of ONE organisational
document (regulation, job description, order, org structure…), one block per line:
`@<offset> [<style>] <text>`. <offset> is the block's position in the text, <style> is the
Word paragraph style, `bold` (bold PDF line), `page_number` (PDF page number), `table` (row,
cells separated by TAB) or `-`. Answer with ONE JSON object:
{"metadata": {...}, "parsing_profile": {...}}. Do not summarise the document.

parsing_profile:
{
 "profile_version": 1, "regex_engine": "python_re",
 "strategy": "numbering" | "formatting" | "table" | "mixed",
 "patterns": [{
   "id": str, "node_type": "clause" | "list_item",
   "regex": str,            # Python regex with a named group (?P<marker>...)
   "flags": ["IGNORECASE"]?,
   "apply_to": "block_start" | "inline",
   "hierarchy": "marker_depth" | "fixed_level" | "list",
   "level": int?,           # fixed_level only: 1 = section, 2 = clause, ...
   "priority": int,         # higher is tried first
   "positive_examples": [str, ...],   # copied from the document, at least one
   "negative_examples": [str, ...]    # text that must NOT match (dates, references…)
 }],
 "heading_styles": [str],   # styles of unnumbered headings, e.g. "Heading 2", "bold"
 "service_rules": [{
   "id": str, "kind": "front_matter" | "toc" | "page_number" | "other",
   "start_regex": str?, "entry_regex": str?, "flags": ["IGNORECASE"]?
 }],
 "unresolved": [str]        # questions you could not settle
}

How the parser uses it:
- block_start patterns are matched at the start of each block; the marker group is the
  number or letter ("5.3.2", "а", "–"). marker_depth markers are decimal ("5.3.2" has depth
  3, depth 1 is a section); the parent is found by prefix. fixed_level markers
  ("Статья 5", "Глава II") get the given level.
- inline patterns find markers glued into the middle of a block (e.g. "…Общества. 3.10.Текст");
  the block is split at the marker group. Decimal inline markers are accepted only if they
  continue the numbering, so references like "п. 3" stay text — still keep inline patterns
  narrow (e.g. require a sentence end before and a capital letter after).
- list_item patterns build lists under the current clause; a list restarts at "а"/"a"/"1".
- front_matter (no regex): every block before the first clause (approval stamp, title) is
  service text. toc: start_regex matches the TOC heading block, entry_regex its entries.
  page_number: start_regex matches whole page-number blocks. other: start_regex matches other
  service blocks.
- Blocks matching nothing become text of the current clause, or headings if their style is
  in heading_styles. A date or a reference inside a sentence must never start a clause.

metadata: every key below is required, each as
{"status": "extracted" | "not_found" | "ambiguous", "value": str|null, "quotes": [str], "reason": str?}
keys: title, document_type, organization, revision, approved_by, approval_document_type,
approval_number, document_created_on, approved_on, effective_from; plus
"extra": [{"name": str, "value": str, "quotes": [str]}].
- quotes are copied VERBATIM from the document text (without the @offset/[style] prefix);
  they are checked mechanically and rejected if not found.
- dates are YYYY-MM-DD. approved_on only from approval details; effective_from only if an
  explicit calendar date is given. Never use dates of referenced laws or standards. A protocol
  number is not a revision.
- If a value is absent use "not_found"; if unclear use "ambiguous" with a reason.
"""


@dataclass(frozen=True, slots=True)
class DocumentView:
    """What the model is shown, and which text ranges that covers."""

    text: str
    studied_ranges: list[tuple[int, int]]


def _render(block: TextBlock) -> str:
    return f"@{block.start} [{block.style or '-'}] {block.text}"


def _sample_indices(blocks: list[TextBlock]) -> list[int]:
    count = len(blocks)
    middle = max(0, count // 2 - _MIDDLE_BLOCKS // 2)
    chosen = set(range(min(_HEAD_BLOCKS, count)))
    chosen |= set(range(max(0, count - _TAIL_BLOCKS), count))
    chosen |= set(range(middle, min(count, middle + _MIDDLE_BLOCKS)))
    per_style: dict[str | None, int] = {}
    for index, block in enumerate(blocks):
        if per_style.get(block.style, 0) < _EXAMPLES_PER_STYLE:
            per_style[block.style] = per_style.get(block.style, 0) + 1
            chosen.add(index)
    return sorted(chosen)


def document_view(extraction: Extraction, max_chars: int) -> DocumentView:
    """Render the document, sampling it when it is longer than ``max_chars``.

    Args:
        extraction: The extracted document.
        max_chars: Size limit of the rendered text.

    Returns:
        The text for the model and the ``original_text`` ranges it contains.
    """
    blocks = extraction.blocks
    full = "\n".join(_render(block) for block in blocks)
    if len(full) <= max_chars:
        return DocumentView(full, [(0, len(extraction.original_text))])
    lines: list[str] = []
    ranges: list[tuple[int, int]] = []
    previous = -1
    for index in _sample_indices(blocks):
        if index != previous + 1:
            skipped = blocks[previous + 1 : index]
            lines.append(f"... пропущено блоков: {len(skipped)} (@{skipped[0].start}–@{skipped[-1].end}) ...")
        lines.append(_render(blocks[index]))
        if ranges and ranges[-1][1] + 1 >= blocks[index].start:
            ranges[-1] = (ranges[-1][0], blocks[index].end)
        else:
            ranges.append((blocks[index].start, blocks[index].end))
        previous = index
    return DocumentView("\n".join(lines), ranges)


def initial_messages(view: DocumentView) -> list[Message]:
    """Build the first request for a document."""
    return [
        Message("system", SYSTEM_PROMPT),
        Message("user", f"Document ({len(view.studied_ranges)} range(s) shown):\n{view.text}"),
    ]


def feedback_message(errors: list[str]) -> Message:
    """Ask the model to fix its previous answer."""
    listed = "\n".join(f"- {error}" for error in errors)
    return Message(
        "user",
        "Your answer failed validation against the document. Fix every problem and return the "
        f"complete corrected JSON object:\n{listed}",
    )
