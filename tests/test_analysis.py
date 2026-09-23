import copy
import json
from typing import Any

import pytest
from conftest import RecordedProfiler, edition_path, recorded_answer

from la_rp_peace.enums import DocFormat, IssueType, ParseStatus
from la_rp_peace.ingestion.analysis import analyse
from la_rp_peace.ingestion.extract import detect_format, extract
from la_rp_peace.ingestion.extract.types import Extraction, TextBuilder
from la_rp_peace.ingestion.profiler import ProfilerError
from la_rp_peace.ingestion.prompt import Message

ED9 = edition_path(9)
EXTRACTION = extract(detect_format(ED9.name, ED9.read_bytes()), ED9.read_bytes())


def _broken_answer() -> dict[str, Any]:
    answer = copy.deepcopy(recorded_answer(9))
    answer["parsing_profile"]["patterns"][0]["regex"] = "^(?P<marker>\\d+"
    return answer


def _run(replies: list[dict[str, Any] | str], retries: int = 2) -> tuple[Any, RecordedProfiler]:
    texts = [reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False) for reply in replies]
    profiler = RecordedProfiler(texts)
    return analyse(EXTRACTION, profiler, max_chars=150_000, retries=retries), profiler


def test_good_first_answer_is_validated() -> None:
    result, profiler = _run([recorded_answer(9)])

    assert result.status is ParseStatus.VALIDATED
    assert len(profiler.conversations) == 1
    assert result.profile["attempts"] == 1
    assert result.profile["studied_ranges"] == [(0, len(EXTRACTION.original_text))]


def test_failed_answer_is_retried_with_feedback() -> None:
    result, profiler = _run([_broken_answer(), recorded_answer(9)])

    assert result.status is ParseStatus.VALIDATED
    retry = profiler.conversations[1]
    assert [message.role for message in retry] == ["system", "user", "assistant", "user"]
    assert "decimal_clause: регулярное выражение не компилируется" in retry[-1].content


def test_exhausted_retries_need_review() -> None:
    result, profiler = _run(["not json", _broken_answer()], retries=1)

    assert result.status is ParseStatus.NEEDS_REVIEW
    assert len(profiler.conversations) == 2
    assert any(issue.is_blocking and issue.issue_type is IssueType.OTHER for issue in result.issues)


def test_metadata_problems_are_fed_back_but_do_not_block() -> None:
    answer = copy.deepcopy(recorded_answer(9))
    answer["metadata"]["approval_number"]["quotes"] = ["Протокол No 99"]

    result, profiler = _run([answer, answer], retries=1)

    assert result.status is ParseStatus.VALIDATED
    assert "Протокол No 99" in profiler.conversations[1][-1].content
    assert result.metadata is not None
    assert result.metadata.card["approval_number"] is None


def test_profiler_failure_propagates() -> None:
    class Unreachable:
        def complete(self, messages: list[Message]) -> str:
            raise ProfilerError(f"нет сети, сообщений: {len(messages)}")

    with pytest.raises(ProfilerError):
        analyse(EXTRACTION, Unreachable(), max_chars=150_000, retries=2)


def test_large_documents_are_sampled_with_gaps_marked() -> None:
    profiler = RecordedProfiler([json.dumps(recorded_answer(9), ensure_ascii=False)])

    result = analyse(EXTRACTION, profiler, max_chars=20_000, retries=0)

    shown = profiler.conversations[0][1].content
    assert shown.splitlines()[1].startswith("@0 [RegApproval] УТВЕРЖДЕНО")
    assert "... пропущено блоков:" in shown
    assert result.profile is not None
    assert len(result.profile["studied_ranges"]) > 1
    assert result.status is ParseStatus.VALIDATED


ED8 = edition_path(8)
ED8_EXTRACTION = extract(detect_format(ED8.name, ED8.read_bytes()), ED8.read_bytes())


def test_numbering_gaps_are_sent_back_and_fixed() -> None:
    without_inline = copy.deepcopy(recorded_answer(8))
    without_inline["parsing_profile"]["patterns"] = [
        pattern for pattern in without_inline["parsing_profile"]["patterns"] if pattern["apply_to"] != "inline"
    ]
    profiler = RecordedProfiler(
        [json.dumps(answer, ensure_ascii=False) for answer in (without_inline, recorded_answer(8))]
    )

    result = analyse(ED8_EXTRACTION, profiler, max_chars=150_000, retries=2)

    assert len(profiler.conversations) == 2
    feedback = profiler.conversations[1][-1].content
    assert "После 9.60 идёт 10.1" in feedback
    assert "склеен" in feedback
    assert [node.marker for node in result.nodes if node.node_type.value == "section"][9] == "10"


def _synthetic_answer() -> str:
    answer = copy.deepcopy(recorded_answer(9))
    for name, value in answer["metadata"].items():
        if name != "extra":
            value.update(status="not_found", value=None, quotes=[])
    answer["metadata"]["extra"] = []
    return json.dumps(answer, ensure_ascii=False)


def test_genuine_gap_is_accepted_after_one_confirmation() -> None:
    builder = TextBuilder()
    for index, text in enumerate(["1. Общие положения", "1.1. Первый.", "1.3. Третий."]):
        builder.add(text, {"paragraph": index})
    extraction = Extraction(DocFormat.DOCX, builder.text(), builder.blocks, builder.source_map)
    profiler = RecordedProfiler([_synthetic_answer()] * 3)

    result = analyse(extraction, profiler, max_chars=150_000, retries=2)

    assert len(profiler.conversations) == 2
    assert result.status is ParseStatus.VALIDATED
    assert [issue.issue_type for issue in result.issues] == [IssueType.NUMBERING_GAP]
