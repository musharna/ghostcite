from __future__ import annotations

import re

from ghostcite.models import Citation

# Parens are allowed INSIDE the DOI body — valid DOIs (old Elsevier/Lancet
# S-DOIs like 10.1016/s0140-6736(97)11096-0) legitimately contain balanced
# parens, per Crossref's DOI grammar. We trim a trailing UNBALANCED ")" and
# trailing sentence punctuation in `clean_doi` instead.
_DOI = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)

_TRAILING = ").,;:"


def clean_doi(doi: str) -> str:
    """Lowercase a captured DOI and strip trailing prose punctuation.

    A trailing ")" is only stripped when unbalanced (more ")" than "(" in the
    DOI), so a DOI wrapped in prose parens — "(10.1234/foo)" → "10.1234/foo" —
    is trimmed while a balanced S-DOI — "…6736(97)11096-0" — is left intact.
    """
    doi = doi.lower()
    while doi and doi[-1] in _TRAILING:
        if doi[-1] == ")" and doi.count(")") <= doi.count("("):
            break
        doi = doi[:-1]
    return doi


def parse_doi_list(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        m = _DOI.search(line)
        if not m:
            continue
        cites.append(Citation(raw=line.strip(), source_line=i, doi=clean_doi(m.group(1))))
    return cites
