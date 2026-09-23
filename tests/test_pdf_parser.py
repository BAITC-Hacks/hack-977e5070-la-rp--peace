from pathlib import Path

import pymupdf
import pytest

from la_rp_peace.enums import ClauseKind
from la_rp_peace.ingestion.service import parse_upload
from la_rp_peace.ingestion.types import ParsedDocument

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"
EDITIONS = [
    "Положение_о_внутреннем_аудите_редакция_8_обезличено",
    "Положение_о_внутреннем_аудите_редакция_9_обезличено",
]


def _signature(document: ParsedDocument) -> list[tuple[ClauseKind, str, str, int | None]]:
    return [(clause.kind, clause.anchor, clause.text, clause.parent) for clause in document.clauses]


@pytest.mark.parametrize("edition", EDITIONS)
def test_word_exported_pdf_slices_exactly_like_the_docx(edition: str) -> None:
    docx_path = TEST_DATA / f"{edition}.docx"
    pdf_path = TEST_DATA / "converted" / f"{edition}.pdf"

    from_docx = parse_upload(docx_path.name, docx_path.read_bytes())
    from_pdf = parse_upload(pdf_path.name, pdf_path.read_bytes())

    assert from_pdf.title == from_docx.title
    assert _signature(from_pdf) == _signature(from_docx)


def test_pdf_clause_pages_follow_the_document() -> None:
    pdf_path = TEST_DATA / "converted" / f"{EDITIONS[1]}.pdf"

    document = parse_upload(pdf_path.name, pdf_path.read_bytes())
    pages = {
        clause.number: clause.location.page
        for clause in document.clauses
        if clause.number is not None and clause.location.page is not None
    }

    assert pages["1"] == 1
    assert pages["3.4"] < pages["5.3"] < pages["14"]


def _synthetic_pdf() -> bytes:
    pdf = pymupdf.open()
    first = pdf.new_page()
    first.insert_text((72, 72), "1. General provisions", fontname="hebo", fontsize=12)
    first.insert_text((72, 100), "1.1. The unit prepares the cost-", fontsize=11)
    first.insert_text((72, 114), "benefit plan", fontsize=11)
    first.insert_text((72, 128), "- a dash that only wrapped", fontsize=11)
    first.insert_text((300, 770), "1", fontsize=9)
    second = pdf.new_page()
    second.insert_text((72, 72), "and continues on the next page.", fontsize=11)
    second.insert_text((72, 100), "1.2. Second clause.", fontsize=11)
    second.insert_text((72, 114), "- a real dash item;", fontsize=11)
    second.insert_text((72, 150), "2. Rights and", fontname="hebo", fontsize=12)
    second.insert_text((72, 164), "duties", fontname="hebo", fontsize=12)
    second.insert_text((72, 200), "Separate bold heading", fontname="hebo", fontsize=12)
    data: bytes = pdf.tobytes()
    return data


def test_pdf_lines_are_rebuilt_into_paragraphs() -> None:
    document = parse_upload("synthetic.pdf", _synthetic_pdf())

    assert [(clause.kind, clause.text, clause.location.page) for clause in document.clauses] == [
        (ClauseKind.HEADING, "1. General provisions", 1),
        (
            ClauseKind.CLAUSE,
            "1.1. The unit prepares the cost-benefit plan - a dash that only wrapped and continues on the next page.",
            1,
        ),
        (ClauseKind.CLAUSE, "1.2. Second clause.", 2),
        (ClauseKind.ITEM, "- a real dash item;", 2),
        (ClauseKind.HEADING, "2. Rights and duties", 2),
        (ClauseKind.HEADING, "Separate bold heading", 2),
    ]
