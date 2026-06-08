from __future__ import annotations

import unicodedata

from ghostcite.models import CanonicalRecord, Citation, Finding, Tier


def normalize_surname(name: str | None) -> str:
    """Fold to a comparable key: strip diacritics, lowercase, keep only letters."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in ascii_only.lower() if c.isalpha())


def _title_tokens(title: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    words = "".join(c if c.isalnum() else " " for c in ascii_only).split()
    stop = {
        "the",
        "a",
        "an",
        "of",
        "and",
        "in",
        "for",
        "on",
        "to",
        "with",
        "by",
        "reveals",
    }
    return {w for w in words if len(w) > 2 and w not in stop}


def title_similar(a: str | None, b: str | None, threshold: float = 0.4) -> bool:
    """Jaccard token overlap >= threshold. Used to tell wrong-author from wrong-DOI."""
    if not a or not b:
        return False
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return (inter / union) >= threshold


def evaluate(citation: Citation, canonical: CanonicalRecord | None) -> list[Finding]:
    """Compare a claimed citation against the canonical record. Empty list = OK."""
    if canonical is None:
        return [
            Finding(citation, Tier.UNRESOLVABLE, None, "DOI not found / unresolvable")
        ]

    findings: list[Finding] = []

    # Retraction is orthogonal — fires regardless of author/year.
    if canonical.retracted:
        findings.append(
            Finding(citation, Tier.RETRACTION, canonical, "RETRACTED per CrossRef")
        )
    elif canonical.eoc:
        findings.append(
            Finding(
                citation,
                Tier.RETRACTION,
                canonical,
                "Expression of concern per CrossRef",
            )
        )

    # Author/year only when the input actually claimed an author (not DOI-list mode).
    if citation.claimed_first_author:
        findings.extend(_author_year(citation, canonical))

    return findings


def _author_year(citation: Citation, canonical: CanonicalRecord) -> list[Finding]:
    claimed_raw = citation.claimed_first_author.strip()
    claimed = normalize_surname(claimed_raw)
    families_raw = canonical.authors or []
    first_raw = families_raw[0] if families_raw else ""
    first = normalize_surname(first_raw)
    all_norm = [normalize_surname(a) for a in families_raw]

    conf = " (low-confidence match)" if canonical.low_confidence else ""

    if claimed == first:
        # First-author matches after normalization.
        if claimed_raw.lower().replace(" ", "") != first_raw.lower().replace(" ", ""):
            return [
                Finding(
                    citation,
                    Tier.COSMETIC,
                    canonical,
                    f'diacritic/spelling: CrossRef has "{first_raw}"{conf}',
                )
            ]
        # True match → check year.
        if (
            citation.claimed_year
            and canonical.year
            and citation.claimed_year != canonical.year
        ):
            return [
                Finding(
                    citation,
                    Tier.YEAR,
                    canonical,
                    f"CrossRef year is {canonical.year}{conf}",
                )
            ]
        return []

    # First-author mismatch.
    if claimed in all_norm:
        idx = all_norm.index(claimed)
        return [
            Finding(
                citation,
                Tier.AUTHOR,
                canonical,
                f"claimed first author is actually author #{idx + 1}; "
                f"CrossRef first author is {first_raw}{conf}",
            )
        ]

    # Not in author list at all — wrong author, or wrong DOI entirely.
    if not title_similar(citation.claimed_title, canonical.title):
        return [
            Finding(
                citation,
                Tier.AUTHOR,
                canonical,
                f"DOI resolves to {first_raw} ({canonical.year}) — "
                f"possibly wrong DOI{conf}",
            )
        ]
    return [
        Finding(
            citation,
            Tier.AUTHOR,
            canonical,
            f"CrossRef first author is {first_raw}{conf}",
        )
    ]
