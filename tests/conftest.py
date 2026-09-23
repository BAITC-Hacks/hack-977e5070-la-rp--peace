"""Shared test helpers: the organiser's documents and a recorded profiler."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from la_rp_peace.llm import Message

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "profiles"
EDITION_NAME = "Положение_о_внутреннем_аудите_редакция_{}_обезличено"


def edition_path(edition: int, suffix: str = ".docx") -> Path:
    """Return the path of a test edition (8 or 9) as .docx, or as the converted .pdf."""
    folder = TEST_DATA if suffix == ".docx" else TEST_DATA / "converted"
    return folder / f"{EDITION_NAME.format(edition)}{suffix}"


def load_fixture(name: str) -> Any:
    """Read a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def recorded_answer(edition: int) -> dict[str, Any]:
    """The profiling answer for an edition: shared parsing profile plus its metadata."""
    return {
        "metadata": load_fixture(f"metadata_ed{edition}.json"),
        "parsing_profile": load_fixture("parsing_profile.json"),
    }


class RecordedProfiler:
    """Answers with prepared replies in order, recording the conversations it saw."""

    def __init__(self, replies: list[str] | Callable[[list[Message]], str]) -> None:
        """Use a fixed list of replies, or a function of the conversation."""
        self._replies = replies
        self.conversations: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        """Return the next prepared reply."""
        self.conversations.append(list(messages))
        if callable(self._replies):
            return self._replies(messages)
        return self._replies[len(self.conversations) - 1]


def answer_by_edition(messages: list[Message]) -> str:
    """Reply with the recorded answer of whichever edition the conversation shows."""
    edition = 8 if "(редакция No8)" in messages[1].content else 9
    return json.dumps(recorded_answer(edition), ensure_ascii=False)


@pytest.fixture
def edition_profiler() -> RecordedProfiler:
    """A profiler that recognises the test editions and answers correctly."""
    return RecordedProfiler(answer_by_edition)
