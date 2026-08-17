from __future__ import annotations

import re

from ghostcite.models import Citation

# An entry ends at its own BALANCED closing brace -- not at whatever happens to
# follow it.
#
# The previous pattern was
#     @\w+\s*\{[^,]*,(?P<body>.*?)\}\s*(?=@|\Z)
# which decided where an entry ended by looking at what came NEXT: the closing
# brace had to be followed by `@` or end-of-input. Any other text between two
# entries failed that lookahead, so `.*?` ran on to a later closing brace and
# merged the two entries into one. That is not a `%`-comment bug -- a stray word,
# a blank-line note, or a `\section{}` line did it too; only text starting with
# `@` was safe, by accident.
#
# The damage was worse than a lost entry. The merged match kept the FIRST entry's
# key and raw line while `_FIELD` handed back BOTH bodies' fields, and later keys
# win in the dict below -- so the surviving Citation carried entry A's identity
# with entry B's DOI, author and year. A checker built to catch
# wrong-author-for-right-DOI was manufacturing exactly that, and reporting
# "0 findings -- clean" while it did: nothing in the output, and nothing in the
# exit status, is a function of how many entries were actually read.
#
# Brace matching removes the class rather than the instance: an entry's extent is
# now a property of the entry itself, so no amount of surrounding text can change
# where it ends.
_ENTRY_START = re.compile(r"@(\w+)\s*\{", re.IGNORECASE)
# @comment / @string / @preamble are BibTeX metadata, not references. They were
# skipped before only because they happen to contain no comma; that is an
# accident of their shape, so it is now explicit.
_NON_ENTRY_TYPES = frozenset({"comment", "string", "preamble"})
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


def _iter_entries(text: str):
    """Yield (start, entry_type, full_entry_text) for each brace-balanced @entry.

    Scanning from each `@type{` to its matching close brace is what BibTeX itself
    does. An unterminated final entry is yielded to end-of-input rather than
    dropped -- a truncated file should still surface the references it does
    contain, and dropping them silently is the failure this replaced.
    """
    pos = 0
    n = len(text)
    while (m := _ENTRY_START.search(text, pos)) is not None:
        open_at = m.end() - 1  # index of the '{'
        depth = 0
        i = open_at
        while i < n:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        end = i + 1 if i < n else n
        yield m.start(), m.group(1).lower(), text[m.start() : end]
        # Resume AFTER this entry. Never rescan its interior: a brace-quoted
        # "@" inside a title would otherwise look like the start of a new entry.
        pos = end if end > m.start() else m.end()


def parse_bibtex(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for start, etype, entry in _iter_entries(text):
        if etype in _NON_ENTRY_TYPES:
            continue
        _key, sep, rest = entry.partition(",")
        if not sep:
            # No comma means no fields -- a citation key on its own, or metadata
            # in a shape we do not recognise. Skipped rather than half-parsed.
            continue
        body = rest[:-1] if rest.endswith("}") else rest
        line_no = text[:start].count("\n") + 1
        fields = {k.lower(): " ".join((bv or qv).split()) for k, bv, qv in _FIELD.findall(body)}
        year = None
        if fields.get("year"):
            ym = re.search(r"\d{4}", fields["year"])
            year = int(ym.group()) if ym else None
        cites.append(
            Citation(
                raw=entry.strip().splitlines()[0],
                source_line=line_no,
                doi=_normalize_doi(fields["doi"]) if fields.get("doi") else None,
                claimed_first_author=_first_author_surname(fields.get("author", "")) or None,
                claimed_year=year,
                claimed_title=fields.get("title") or None,
                claimed_journal=(
                    fields.get("journal")
                    or fields.get("booktitle")
                    or fields.get("journaltitle")
                    or None
                ),
            )
        )
    return cites
