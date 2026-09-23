"""Guess the organisational document type from its title and opening text."""

from la_rp_peace.enums import DocFormat, DocType

# Checked in order: the first rule whose keywords all occur wins. Specific kinds come
# before generic ones, because e.g. a job description is often titled «Положение…» too.
_RULES: tuple[tuple[DocType, tuple[str, ...]], ...] = (
    (DocType.JOB_DESCRIPTION, ("ДОЛЖНОСТН", "ИНСТРУКЦ")),
    (DocType.ORDER, ("ПРИКАЗ",)),
    (DocType.ORDER, ("РАСПОРЯЖЕНИ",)),
    (DocType.ORG_STRUCTURE, ("ОРГАНИЗАЦИОНН", "СТРУКТУР")),
    (DocType.ORG_STRUCTURE, ("ОРГСТРУКТУР",)),
    (DocType.UNIT_REGULATION, ("ПОЛОЖЕНИЕ",)),
    (DocType.INTERNAL_REGULATION, ("РЕГЛАМЕНТ",)),
    (DocType.INTERNAL_REGULATION, ("ПОЛИТИК",)),
    (DocType.INTERNAL_REGULATION, ("СТАНДАРТ",)),
    (DocType.INTERNAL_REGULATION, ("ПРАВИЛА",)),
)


def classify(filename: str, title: str | None, opening: str, doc_format: DocFormat) -> DocType:
    """Pick the most likely document type; the user can override it in the UI.

    Args:
        filename: Original file name.
        title: Title from title-styled paragraphs, if any.
        opening: The first few hundred characters of text.
        doc_format: File format.

    Returns:
        The matched type, ORG_STRUCTURE for otherwise unmatched workbooks, else UNKNOWN.
    """
    for source in (title or "", filename.replace("_", " "), opening):
        haystack = source.upper()
        for doc_type, keywords in _RULES:
            if all(keyword in haystack for keyword in keywords):
                return doc_type
    return DocType.ORG_STRUCTURE if doc_format is DocFormat.XLSX else DocType.UNKNOWN
