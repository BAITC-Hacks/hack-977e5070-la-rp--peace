import pytest

from la_rp_peace.ingestion.numbering import is_successor, leading_number, normalize_text, parse_number, split_glued


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1. Общие положения", (1,)),
        ("5.3.2. организует работу", (5, 3, 2)),
        ("3.10.Рабочие места", (3, 10)),
        ("12.1 Главный аудитор", (12, 1)),
        ("2021 года", None),
        ("25 июня", None),
        ("3.10.2021 утверждено", None),
        ("а. пункт", None),
    ],
)
def test_leading_number(text: str, expected: tuple[int, ...] | None) -> None:
    assert leading_number(text) == expected


@pytest.mark.parametrize(
    ("candidate", "last", "expected"),
    [
        ((1,), None, True),
        ((2,), None, False),
        ((3, 10), (3, 9), True),
        ((3, 9, 1), (3, 9), True),
        ((4,), (3, 9), True),
        ((10,), (9, 60), True),
        ((11,), (3, 9), False),
        ((3, 11), (3, 9), False),
    ],
)
def test_is_successor(candidate: tuple[int, ...], last: tuple[int, ...] | None, expected: bool) -> None:
    assert is_successor(candidate, last) is expected


def test_normalize_text_collapses_nbsp_and_newlines() -> None:
    assert normalize_text(" 1.1.\xa0Текст\n  дальше ") == "1.1. Текст дальше"


def test_split_glued_follows_the_numbering() -> None:
    pieces, last = split_glued("3.9. Рабочие места в филиалах. 3.10.Работники вне офиса. 3.11.По вопросам.", (3, 8))

    assert pieces == ["3.9. Рабочие места в филиалах.", "3.10.Работники вне офиса.", "3.11.По вопросам."]
    assert last == (3, 11)


def test_split_glued_keeps_references() -> None:
    pieces, _ = split_glued("5.10.6. оказывать содействие согласно п.11 Положения. 11.Оценка", (5, 10, 5))

    assert pieces == ["5.10.6. оказывать содействие согласно п.11 Положения. 11.Оценка"]


@pytest.mark.parametrize(("marker", "expected"), [("5.3.2", (5, 3, 2)), ("10.", (10,)), ("а", None), ("II", None)])
def test_parse_number(marker: str, expected: tuple[int, ...] | None) -> None:
    assert parse_number(marker) == expected
