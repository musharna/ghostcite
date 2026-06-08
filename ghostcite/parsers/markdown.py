from __future__ import annotations

import re

from ghostcite.models import Citation

_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_YEAR = re.compile(r"\((\d{4})[a-z]?\)")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s)>\"]+)", re.IGNORECASE)
# Leading author surname: first capitalized word(s) before an initial or comma.
_FIRST_AUTHOR = re.compile(r"^\**\s*([A-Z][A-Za-zÀ-ÿ'’-]+)")


def parse_markdown(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _BULLET.match(line)
        if not m:
            continue
        content = m.group(1)
        # Require a year to count it as a reference (filters non-ref bullets).
        ym = _YEAR.search(content)
        if not ym:
            continue
        author_m = _FIRST_AUTHOR.match(content)
        doi_m = _DOI.search(content)
        doi = doi_m.group(1).rstrip(".").lower() if doi_m else None
        cites.append(
            Citation(
                raw=content.strip(),
                source_line=i,
                doi=doi,
                claimed_first_author=author_m.group(1) if author_m else None,
                claimed_year=int(ym.group(1)),
                claimed_title=None,  # title hard to delimit reliably; left None in v1
            )
        )
    return cites
