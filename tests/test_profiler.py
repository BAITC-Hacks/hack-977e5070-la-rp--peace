from types import SimpleNamespace
from typing import Any

import openai
import pytest

from la_rp_peace.config import Settings
from la_rp_peace.ingestion.profiler import OpenAIProfiler, ReasoningEffort
from la_rp_peace.ingestion.prompt import Message


def _captured_request(monkeypatch: pytest.MonkeyPatch, effort: ReasoningEffort | None) -> dict[str, Any]:
    profiler = OpenAIProfiler("sk-test", "test-model", reasoning_effort=effort)
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(profiler._client.chat.completions, "create", create)
    assert profiler.complete([Message("user", "текст")]) == "{}"
    return captured


def test_reasoning_effort_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _captured_request(monkeypatch, "low")

    assert request["reasoning_effort"] == "low"
    assert request["response_format"] == {"type": "json_object"}


def test_reasoning_effort_can_be_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _captured_request(monkeypatch, None)

    assert request["reasoning_effort"] is openai.omit


def test_empty_setting_means_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "")

    assert Settings().openai_reasoning_effort is None
    assert Settings.model_fields["openai_reasoning_effort"].default == "low"
