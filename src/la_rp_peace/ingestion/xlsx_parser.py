"""Extract rows from Excel (.xlsx) workbooks."""

from io import BytesIO

import openpyxl

from la_rp_peace.enums import ClauseKind
from la_rp_peace.ingestion.numbering import normalize_text
from la_rp_peace.ingestion.types import Location, ParsedClause


def read_xlsx(data: bytes) -> list[ParsedClause]:
    """Turn every non-empty row of every sheet into a row clause.

    Org-structure workbooks have no common layout, so rows are kept flat and
    interpreting the columns is left to the analysis stages.

    Args:
        data: Raw file bytes.

    Returns:
        Row clauses in sheet order, cells joined with « | ».
    """
    workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    clauses: list[ParsedClause] = []
    try:
        for sheet in workbook.worksheets:
            for row_number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
                cells = [normalize_text(str(value)) for value in values if value is not None]
                text = " | ".join(cell for cell in cells if cell)
                if text:
                    clauses.append(
                        ParsedClause(
                            kind=ClauseKind.ROW,
                            text=text,
                            anchor=f"лист «{sheet.title}», стр. {row_number}",
                            location=Location(sheet=sheet.title, row=row_number),
                        ),
                    )
    finally:
        workbook.close()
    return clauses
