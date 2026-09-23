import pytest

from la_rp_peace.enums import ClauseKind
from la_rp_peace.ingestion.numbering import build_clauses, is_successor, leading_number, normalize_text
from la_rp_peace.ingestion.types import Block, Location, ParsedClause


def _blocks(*texts: str, style: str | None = None) -> list[Block]:
    return [Block(text=text, location=Location(paragraph_index=i), style=style) for i, text in enumerate(texts)]


def _by_anchor(clauses: list[ParsedClause]) -> dict[str, ParsedClause]:
    return {clause.anchor: clause for clause in clauses}


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


def test_glued_clauses_are_split_in_sequence() -> None:
    clauses = build_clauses(
        _blocks(
            "3. Структура", "3.9. Рабочие места в филиалах. 3.10.Работники вне офиса. 3.11.По вопросам дисциплины."
        ),
    )

    assert [clause.number for clause in clauses] == ["3", "3.9", "3.10", "3.11"]
    assert clauses[2].text == "3.10.Работники вне офиса."
    assert clauses[2].parent == 0


def test_glued_section_heading_after_letter_item() -> None:
    clauses = build_clauses(_blocks("9. Проверки", "9.60. Факторы:", "д. период времени. 10.Контроль качества"))

    heading = clauses[-1]
    assert heading.kind is ClauseKind.HEADING
    assert heading.anchor == "разд. 10"
    assert clauses[-2].text == "д. период времени."


def test_in_text_reference_is_not_split() -> None:
    clauses = build_clauses(
        _blocks("5. Права", "5.10.6. оказывать содействие в соответствии с п.11 Положения. 11.Оценка")
    )

    assert [clause.number for clause in clauses] == ["5", "5.10.6"]


def test_letter_and_dash_items_attach_to_last_clause() -> None:
    clauses = build_clauses(_blocks("3. Структура", "3.4. БВА состоит из:", "а. ДНМ.", "б. ДККМ.", "– прочее"))
    anchors = _by_anchor(clauses)

    assert anchors["п. 3.4 «а»"].parent == 1
    assert anchors["п. 3.4 «б»"].kind is ClauseKind.ITEM
    assert anchors["п. 3.4, подп. 3"].text == "– прочее"


def test_unnumbered_heading_collects_following_paragraphs() -> None:
    blocks = [
        *_blocks("1. Общие положения"),
        Block(text="Дополнительные требования:", location=Location(paragraph_index=1), style="RegHeading2"),
        Block(text="- английский язык", location=Location(paragraph_index=2)),
    ]
    clauses = build_clauses(blocks)

    assert clauses[1].kind is ClauseKind.HEADING
    assert clauses[1].parent == 0
    assert clauses[2].parent == 1


def test_preamble_paragraphs_have_no_parent() -> None:
    clauses = build_clauses(_blocks("УТВЕРЖДЕНО", "Советом директоров", "1. Общие положения"))

    assert clauses[0].anchor == "вводная часть, абз. 1"
    assert clauses[1].parent is None


def test_table_of_contents_is_skipped() -> None:
    clauses = build_clauses(
        _blocks("1. Общие положения", "1.1. Текст.", "Оглавление", "1. ОБЩИЕ ПОЛОЖЕНИЯ 1", "2. ЦЕЛИ 3", "Приложения"),
    )

    assert [clause.text for clause in clauses] == ["1. Общие положения", "1.1. Текст.", "Приложения"]
