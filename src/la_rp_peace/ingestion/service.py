"""Entry point that turns an uploaded file into a ParsedDocument."""

import zipfile
from pathlib import PurePath

from la_rp_peace.enums import DocFormat
from la_rp_peace.ingestion.classify import classify
from la_rp_peace.ingestion.docx_parser import read_docx
from la_rp_peace.ingestion.numbering import build_clauses
from la_rp_peace.ingestion.pdf_parser import read_pdf
from la_rp_peace.ingestion.types import ParsedClause, ParsedDocument
from la_rp_peace.ingestion.xlsx_parser import read_xlsx
from la_rp_peace.logging_config import get_logger

log = get_logger(__name__)

MEDIA_TYPES: dict[DocFormat, str] = {
    DocFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocFormat.PDF: "application/pdf",
    DocFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_MAGIC: dict[DocFormat, bytes] = {
    DocFormat.DOCX: b"PK\x03\x04",
    DocFormat.PDF: b"%PDF",
    DocFormat.XLSX: b"PK\x03\x04",
}
_LEGACY_EXTENSIONS = {".doc": ".docx", ".xls": ".xlsx"}
_OPENING_CHARS = 400


class UnsupportedFormatError(ValueError):
    """The file is not a .docx, .pdf or .xlsx document."""


class DocumentParseError(ValueError):
    """The file has a supported format but no text could be extracted from it."""


def detect_format(filename: str, data: bytes) -> DocFormat:
    """Validate the extension and the file signature.

    Args:
        filename: Original file name.
        data: Raw file bytes.

    Returns:
        The detected format.

    Raises:
        UnsupportedFormatError: For unknown or legacy extensions, or a signature mismatch.
    """
    extension = PurePath(filename).suffix.lower()
    if extension in _LEGACY_EXTENSIONS:
        modern = _LEGACY_EXTENSIONS[extension]
        raise UnsupportedFormatError(f"Формат {extension} не поддерживается: пересохраните файл как {modern}")
    try:
        doc_format = DocFormat(extension.removeprefix("."))
    except ValueError as exc:
        raise UnsupportedFormatError(f"Поддерживаются только .docx, .pdf и .xlsx, получен «{filename}»") from exc
    if not data.startswith(_MAGIC[doc_format]):
        raise UnsupportedFormatError(f"Содержимое «{filename}» не соответствует формату {extension}")
    return doc_format


def _extract(doc_format: DocFormat, data: bytes) -> tuple[list[ParsedClause], str | None]:
    if doc_format is DocFormat.XLSX:
        return read_xlsx(data), None
    if doc_format is DocFormat.PDF:
        return build_clauses(read_pdf(data)), None
    blocks, title = read_docx(data)
    return build_clauses(blocks), title


def parse_upload(filename: str, data: bytes) -> ParsedDocument:
    """Detect the format, extract the clause tree and classify the document.

    Args:
        filename: Original file name.
        data: Raw file bytes.

    Returns:
        The parsed document.

    Raises:
        UnsupportedFormatError: See ``detect_format``.
        DocumentParseError: If the file is corrupt or contains no text.
    """
    doc_format = detect_format(filename, data)
    try:
        clauses, title = _extract(doc_format, data)
    except (zipfile.BadZipFile, KeyError, ValueError, RuntimeError, OSError) as exc:
        log.warning("document_parse_failed", filename=filename, format=doc_format, error=str(exc))
        raise DocumentParseError(f"Не удалось прочитать «{filename}»: файл повреждён") from exc
    if not clauses:
        raise DocumentParseError(f"В «{filename}» не найден текст (скан без текстового слоя?)")
    opening = " ".join(clause.text for clause in clauses[:10])[:_OPENING_CHARS]
    doc_type = classify(filename, title, opening, doc_format)
    log.info("document_parsed", filename=filename, format=doc_format, doc_type=doc_type, clauses=len(clauses))
    return ParsedDocument(format=doc_format, doc_type=doc_type, title=title, clauses=clauses)
