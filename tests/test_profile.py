import copy
from typing import Any

import pytest
from conftest import load_fixture

from la_rp_peace.ingestion.profile import ProfileError, compile_profile


def _profile() -> dict[str, Any]:
    profile: dict[str, Any] = copy.deepcopy(load_fixture("parsing_profile.json"))
    return profile


def _errors(profile: dict[str, Any]) -> list[str]:
    with pytest.raises(ProfileError) as caught:
        compile_profile(profile)
    return caught.value.errors


def test_recorded_profile_compiles() -> None:
    compiled = compile_profile(_profile())

    assert [p.rule.id for p in compiled.block_patterns] == [
        "decimal_clause",
        "decimal_section",
        "letter_item",
        "dash_item",
    ]
    assert [p.rule.id for p in compiled.inline_patterns] == ["glued_clause"]
    assert "regheading1" in compiled.heading_styles


def test_unknown_fields_and_values_are_reported() -> None:
    profile = _profile()
    profile["patterns"][0]["hierarchy"] = "by_indent"
    profile["surprise"] = True

    errors = _errors(profile)

    assert any(error.startswith("patterns.0.hierarchy") for error in errors)
    assert any(error.startswith("surprise") for error in errors)


def test_regex_that_does_not_compile() -> None:
    profile = _profile()
    profile["patterns"][0]["regex"] = "^(?P<marker>\\d+"

    assert any("не компилируется" in error for error in _errors(profile))


def test_pattern_needs_marker_group() -> None:
    profile = _profile()
    profile["patterns"][3]["regex"] = "^[а-я]\\.\\s+"

    assert any("именованной группы" in error for error in _errors(profile))


def test_examples_are_checked() -> None:
    profile = _profile()
    profile["patterns"][1]["positive_examples"].append("Статья 5. Права")
    profile["patterns"][1]["negative_examples"].append("5. Права и обязанности")

    errors = _errors(profile)

    assert "decimal_section: положительный пример не совпал: «Статья 5. Права»" in errors
    assert "decimal_section: отрицательный пример совпал: «5. Права и обязанности»" in errors


def test_catastrophic_regex_is_stopped_by_timeout() -> None:
    profile = _profile()
    profile["patterns"][1]["regex"] = "(?P<marker>(?:(\\d+)\\2?)+$)"
    profile["patterns"][1]["positive_examples"] = ["1" * 5000 + "x"]

    assert any("слишком долго" in error for error in _errors(profile))


def test_service_rule_needs_its_regex() -> None:
    profile = _profile()
    profile["service_rules"].append({"id": "toc2", "kind": "toc"})

    assert "toc2: для toc нужен start_regex" in _errors(profile)
