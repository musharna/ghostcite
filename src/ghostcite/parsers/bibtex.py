from __future__ import annotations

import re

from ghostcite.models import Citation

# Entry body = everything after the first comma up to the closing brace that
# precedes the next entry or end-of-input. Handles both multi-line and
# single-line ("@article{k, a={x}, b={y}}") BibTeX shapes.
_ENTRY = re.compile(r"@\w+\s*\{[^,]*,(?P<body>.*?)\}\s*(?=@|\Z)", re.DOTALL)
# A field is key = {value} or key = "value". The brace branch tolerates one
# level of nesting (e.g. a brace-protected acronym {ATP} inside a title). The
# alternation branches [^{}] and \{[^{}]*\} match disjoint first-characters, so
# this stays linear despite re.DOTALL — no catastrophic backtracking.
_FIELD = re.compile(r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"(.*?)")', re.DOTALL)
_DOI_CLEAN = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)\s*", re.IGNORECASE)


def _first_author_surname(author_field: str) -> str | None:
    # BibTeX authors are separated by " and ". Take the first.
    first = re.split(r"\s+and\s+", author_field.strip(), maxsplit=1)[0].strip()
    if not first:
        return None
    if "," in first:  # "Surname, Given"
        return first.split(",", 1)[0].strip()
    parts = first.split()  # "Given Surname"
    return parts[-1].strip() if parts else None


def _normalize_doi(raw: str) -> str:
    return _DOI_CLEAN.sub("", raw.strip()).strip().lower()


def parse_bibtex(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for m in _ENTRY.finditer(text):
        body = m.group("body")
        line_no = text[: m.start()].count("\n") + 1
        fields = {k.lower(): " ".join((bv or qv).split()) for k, bv, qv in _FIELD.findall(body)}
        year = None
        if fields.get("year"):
            ym = re.search(r"\d{4}", fields["year"])
            year = int(ym.group()) if ym else None
        cites.append(
            Citation(
                raw=m.group(0).strip().splitlines()[0],
                source_line=line_no,
                doi=_normalize_doi(fields["doi"]) if fields.get("doi") else None,
                claimed_first_author=_first_author_surname(fields.get("author", "")) or None,
                claimed_year=year,
                claimed_title=fields.get("title") or None,
            )
        )
    return cites
