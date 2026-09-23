import copy
import json
from typing import Any

import pytest
from conftest import RecordedProfiler, edition_path, recorded_answer

from la_rp_peace.enums import IssueType, ParseStatus
from la_rp_peace.ingestion.analysis import analyse
from la_rp_peace.ingestion.extract import detect_format, extract
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
