from io import BytesIO
from pathlib import Path

import openpyxl
import pymupdf
import pytest

from la_rp_peace.enums import ClauseKind, DocFormat, DocType
from la_rp_peace.ingestion.service import DocumentParseError, UnsupportedFormatError, parse_upload
from la_rp_peace.ingestion.types import ParsedDocument

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"
EDITION_8 = TEST_DATA / "Положение_о_внутреннем_аудите_редакция_8_обезличено.docx"
EDITION_9 = TEST_DATA / "Положение_о_внутреннем_аудите_редакция_9_обезличено.docx"


def _parse(path: Path) -> ParsedDocument:
    return parse_upload(path.name, path.read_bytes())


def _texts_under(document: ParsedDocument, number: str) -> list[str]:
    index = next(i for i, clause in enumerate(document.clauses) if clause.number == number)
    return [clause.text for clause in document.clauses if clause.parent == index]


def test_docx_edition_8_structure() -> None:
    document = _parse(EDITION_8)

    assert document.format is DocFormat.DOCX
    assert document.doc_type is DocType.UNIT_REGULATION
    assert document.title == "ПОЛОЖЕНИЕ О ВНУТРЕННЕМ АУДИТЕ АО «Компания»"
    assert _texts_under(document, "3.4") == [
        "а. Департамент непрерывного мониторинга системы внутреннего контроля (ДНМ).",
        "б. Департамент контроля качества аудита и методологии (ДККМ).",
    ]
    numbers = [clause.number for clause in document.clauses]
    assert numbers.index("3.10") == numbers.index("3.9") + 1


def test_docx_edition_9_has_new_departments() -> None:
    departments = _texts_under(_parse(EDITION_9), "3.4")

    assert len(departments) == 4
    assert departments[0] == "а. Департамент ИТ-аудита и анализа данных (ДИТААД)."
    assert departments[1] == "б. Департамент операционного аудита (ДОА)."


@pytest.mark.parametrize("path", [EDITION_8, EDITION_9])
def test_docx_sections_and_no_table_of_contents(path: Path) -> None:
    document = _parse(path)
    sections = [clause.number for clause in document.clauses if clause.kind is ClauseKind.HEADING and clause.number]

    assert sections == [str(n) for n in range(1, 15)]
    assert not any(clause.text.endswith("ПРИЛОЖЕНИЯ 38") for clause in document.clauses)


def test_docx_letter_item_anchor() -> None:
    document = _parse(EDITION_9)

    assert any(
        clause.anchor == "п. 5.3.2 «а»" and clause.text.startswith("а. аудит ИТ систем") for clause in document.clauses
    )


def test_pdf_blocks_keep_page_numbers() -> None:
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "1. General provisions")
    second = pdf.new_page()
    second.insert_text((72, 72), "1.1. The unit performs audits.")
    data = pdf.tobytes()

    document = parse_upload("regulation.pdf", data)

    assert document.format is DocFormat.PDF
    assert [(clause.number, clause.location.page) for clause in document.clauses] == [("1", 1), ("1.1", 2)]
    assert document.clauses[1].parent == 0


def test_xlsx_rows_become_row_clauses() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Оргструктура"
    sheet.append(["Подразделение", "Руководитель"])
    sheet.append([None, None])
    sheet.append(["ДИТААД", "Директор ДИТААД"])
    buffer = BytesIO()
    workbook.save(buffer)

    document = parse_upload("structure.xlsx", buffer.getvalue())

    assert document.doc_type is DocType.ORG_STRUCTURE
    assert [clause.anchor for clause in document.clauses] == [
        "лист «Оргструктура», стр. 1",
        "лист «Оргструктура», стр. 3",
    ]
    assert document.clauses[1].text == "ДИТААД | Директор ДИТААД"
    assert document.clauses[1].kind is ClauseKind.ROW


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("old.doc", b"\xd0\xcf\x11\xe0", "пересохраните файл как .docx"),
        ("notes.txt", b"hello", "Поддерживаются только"),
        ("fake.pdf", b"PK\x03\x04", "не соответствует формату"),
    ],
)
def test_unsupported_files_are_rejected(filename: str, data: bytes, message: str) -> None:
    with pytest.raises(UnsupportedFormatError, match=message):
        parse_upload(filename, data)


def test_corrupt_docx_raises_parse_error() -> None:
    with pytest.raises(DocumentParseError, match="повреждён"):
        parse_upload("broken.docx", b"PK\x03\x04garbage")


def test_pdf_without_text_raises_parse_error() -> None:
    pdf = pymupdf.open()
    pdf.new_page()

    with pytest.raises(DocumentParseError, match="не найден текст"):
        parse_upload("scan.pdf", pdf.tobytes())
