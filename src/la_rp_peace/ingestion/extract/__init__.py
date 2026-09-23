"""Format adapters: turn an uploaded file into ``original_text`` with a source map."""

import zipfile
from pathlib import PurePath

from la_rp_peace.enums import DocFormat
from la_rp_peace.ingestion.extract.docx import extract_docx
from la_rp_peace.ingestion.extract.pdf import extract_pdf
from la_rp_peace.ingestion.extract.types import Extraction
from la_rp_peace.ingestion.extract.xlsx import extract_xlsx

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


class UnsupportedFormatError(ValueError):
    """The file is not a .docx, .pdf or .xlsx document."""


class ExtractionError(ValueError):
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


def extract(doc_format: DocFormat, data: bytes) -> Extraction:
    """Extract the text representation of a file.

    Args:
        doc_format: Format returned by ``detect_format``.
        data: Raw file bytes.

    Returns:
        The extraction.

    Raises:
        ExtractionError: If the file is corrupt or has no text (e.g. a scan without OCR).
    """
    readers = {DocFormat.DOCX: extract_docx, DocFormat.PDF: extract_pdf, DocFormat.XLSX: extract_xlsx}
    try:
        extraction = readers[doc_format](data)
    except (zipfile.BadZipFile, KeyError, ValueError, RuntimeError, OSError) as exc:
        raise ExtractionError(f"Не удалось прочитать файл: {exc}") from exc
    if not extraction.original_text:
        raise ExtractionError("В файле не найден текст (скан без текстового слоя?)")
    return extraction
