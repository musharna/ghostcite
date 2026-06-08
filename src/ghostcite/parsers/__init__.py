from __future__ import annotations

import re

from ghostcite.models import Citation
from ghostcite.parsers.bibtex import parse_bibtex
from ghostcite.parsers.markdown import parse_markdown
from ghostcite.parsers.doi import parse_doi_list

_DOI_LINE = re.compile(
    r"^\s*(?:doi:|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+\s*$", re.IGNORECASE
)


def sniff(text: str) -> str:
    """Return 'bibtex' | 'markdown' | 'doi' from the content shape."""
    if re.search(r"@\w+\s*\{", text):
        return "bibtex"
    nonblank = [
        ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    ]
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
    raise ValueError(f"unknown format: {fmt}")
