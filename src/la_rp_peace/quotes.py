"""Find verbatim quotes in document text.

A quote matches when its words appear in the same order with the same characters; any run
of whitespace (spaces, line breaks between paragraphs) matches any other. Nothing else is
forgiven: a paraphrase, a changed letter or different quotation marks do not match.
"""

import regex

_WORD_GAP = r"\s+"


class QuoteNotFoundError(ValueError):
    """The quote does not occur in the text."""


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Return the range of the first occurrence of ``quote`` in ``text``, or None.

    Args:
        text: Text to search, e.g. a node's own text or a document's ``original_text``.
        quote: Cited words.

    Returns:
        Start and end offsets in ``text``.
    """
    words = quote.split()
    if not words:
        return None
    match = regex.search(_WORD_GAP.join(regex.escape(word) for word in words), text)
    return None if match is None else (match.start(), match.end())


def locate_quote(text: str, quote: str) -> tuple[int, int]:
    """Like ``find_quote`` but raises when the quote is absent.

    Raises:
        QuoteNotFoundError: If the quote is empty or not in the text.
    """
    found = find_quote(text, quote)
    if found is None:
        raise QuoteNotFoundError(f"Цитата не найдена в тексте: «{quote}»")
    return found
