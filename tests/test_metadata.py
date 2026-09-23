import copy
from typing import Any

from conftest import edition_path, load_fixture

from la_rp_peace.ingestion.extract import detect_format, extract
from la_rp_peace.ingestion.metadata import DocumentMetadata, apply_metadata
from la_rp_peace.quotes import find_quote

ED8 = edition_path(8)
TEXT = extract(detect_format(ED8.name, ED8.read_bytes()), ED8.read_bytes()).original_text


def _answer() -> dict[str, Any]:
    answer: dict[str, Any] = copy.deepcopy(load_fixture("metadata_ed8.json"))
    return answer


def test_card_is_filled_from_verified_quotes() -> None:
    result = apply_metadata(DocumentMetadata.model_validate(_answer()), TEXT)

    assert result.card["approved_on"] == "2021-06-25"
    assert result.card["approval_number"] == "13"
    assert result.card["revision"] == "8"
    assert result.card["approved_by"] == "Совет директоров АО «Компания»"
    assert result.card["effective_from"] is None
    assert result.issues == []


def test_evidence_points_at_the_exact_text() -> None:
    result = apply_metadata(DocumentMetadata.model_validate(_answer()), TEXT)

    (quote,) = result.evidence["approved_on"]["quotes"]
    approved_by = result.evidence["approved_by"]["quotes"][0]

    assert TEXT[quote["start"] : quote["end"]] == "от «25» июня 2021 года"
    assert TEXT[approved_by["start"] : approved_by["end"]] == "УТВЕРЖДЕНО\nСоветом директоров\nАО «Компания»"
    assert result.evidence["effective_from"]["status"] == "not_found"
    assert result.evidence["extra"][0]["name"] == "условие вступления в силу"


def test_invented_quote_leaves_the_field_empty() -> None:
    answer = _answer()
    answer["approval_number"]["quotes"] = ["Протокол No 42"]

    result = apply_metadata(DocumentMetadata.model_validate(answer), TEXT)

    assert result.card["approval_number"] is None
    assert result.evidence["approval_number"]["status"] == "ambiguous"
    assert "Протокол No 42" in result.issues[0].message
    assert not result.issues[0].is_blocking


def test_date_must_be_iso() -> None:
    answer = _answer()
    answer["approved_on"]["value"] = "25.06.2021"

    result = apply_metadata(DocumentMetadata.model_validate(answer), TEXT)

    assert result.card["approved_on"] is None
    assert "YYYY-MM-DD" in result.evidence["approved_on"]["reason"]


def test_quotes_match_across_line_breaks_but_not_paraphrases() -> None:
    assert find_quote("УТВЕРЖДЕНО\nСоветом  директоров", "УТВЕРЖДЕНО Советом директоров") == (0, 30)
    assert find_quote("Советом директоров", "Совет директоров") is None
    assert find_quote("текст", "   ") is None
