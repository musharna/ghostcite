from __future__ import annotations

import re

from ghostcite.models import Citation

_DOI = re.compile(r"(10\.\d{4,9}/[^\s)>\"]+)", re.IGNORECASE)


def parse_doi_list(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        m = _DOI.search(line)
        if not m:
            continue
        cites.append(Citation(raw=line.strip(), source_line=i, doi=m.group(1).rstrip(".").lower()))
    return cites
