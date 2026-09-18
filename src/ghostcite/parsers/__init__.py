from __future__ import annotations

import re

from ghostcite.models import Citation
from ghostcite.parsers.bibtex import parse_bibtex
from ghostcite.parsers.document import DocumentInputError, parse_document, parse_document_text
from ghostcite.parsers.doi import parse_doi_list
from ghostcite.parsers.markdown import parse_markdown

FORMATS = ("auto", "bibtex", "markdown", "doi", "document")
DOCUMENT_SUFFIXES = (".pdf", ".docx")

_DOI_LINE = re.compile(
    r"^\s*(?:doi:|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+\s*$", re.IGNORECASE
)


def sniff(text: str) -> str:
    """Return 'bibtex' | 'markdown' | 'doi' from the content shape."""
    if re.search(r"@\w+\s*\{", text):
        return "bibtex"
    nonblank = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if nonblank and all(_DOI_LINE.match(ln) for ln in nonblank):
        return "doi"
    return "markdown"


def parse(text: str, fmt: str = "auto") -> list[Citation]:
    if fmt == "auto":
        fmt = sniff(text)
    if fmt == "bibtex":
        return parse_bibtex(text)
    if fmt == "doi":
        return parse_doi_list(text)
    if fmt == "markdown":
        return parse_markdown(text)
    if fmt == "document":
        # A manuscript body as plain text (or a PDF/DOCX already extracted):
        # find the reference section and split it into entries.
        return parse_document_text(text)
    raise ValueError(f"unknown format: {fmt}")


def parse_file_bytes(data: bytes, filename: str, fmt: str = "auto") -> list[Citation]:
    """Parse a file by its bytes: PDF/DOCX go through the document extractor,
    everything else is decoded as UTF-8 text and dispatched as ``parse``."""
    if fmt in ("auto", "document") and filename.lower().endswith(DOCUMENT_SUFFIXES):
        return parse_document(data, filename)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"{filename}: not UTF-8 text (a PDF or DOCX needs its own suffix): {e}"
        ) from e
    return parse(text, fmt=fmt)


__all__ = [
    "DOCUMENT_SUFFIXES",
    "DocumentInputError",
    "FORMATS",
    "parse",
    "parse_document",
    "parse_file_bytes",
    "sniff",
]
