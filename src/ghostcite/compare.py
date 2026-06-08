from __future__ import annotations

import unicodedata

from ghostcite.models import CanonicalRecord, Citation, Finding, PubMedRecord, Tier


def normalize_surname(name: str | None) -> str:
    """Fold to a comparable key: strip diacritics, lowercase, keep only letters."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in ascii_only.lower() if c.isalpha())


def _is_initials(token: str) -> bool:
    """True if a token is an initials cluster, e.g. "J", "J.", "JA", "J.A.".
    Single letter, or all-uppercase letters after stripping dots — a real
    surname ("Li", "Berg") is mixed-case, not all-caps."""
    bare = token.replace(".", "")
    if not bare or not bare.isalpha():
        return False
    return len(bare) == 1 or bare.isupper()


def _surname_tokens(name: str) -> list[str]:
    return [t for t in name.split() if not _is_initials(t)]


def _surname_key(name: str | None) -> str:
    """Surname comparison key: drop standalone initial tokens
    (e.g. "Smith J", "J Smith", "Smith JA") before normalizing, so a claimed
    author carrying initials still matches a bare CrossRef family name."""
    if not name:
        return ""
    return normalize_surname(" ".join(_surname_tokens(name)))


def _surname_raw(name: str | None) -> str:
    """Initial-stripped surname, diacritics PRESERVED, lowercased, despaced.
    Used to tell a genuine diacritic/spelling difference from a pure
    initials-only difference once `_surname_key` has matched the keys."""
    if not name:
        return ""
    return "".join(_surname_tokens(name)).lower()


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
        return [Finding(citation, Tier.UNRESOLVABLE, None, "DOI not found / unresolvable")]

    findings: list[Finding] = []

    # Retraction is orthogonal — fires regardless of author/year.
    if canonical.retracted:
        findings.append(Finding(citation, Tier.RETRACTION, canonical, "RETRACTED per CrossRef"))
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
    families_raw = canonical.authors or []
    if not families_raw:
        # DOI resolved but CrossRef has no author array (some preprints,
        # datasets, protocols). Author can't be verified → warn, don't fail CI.
        return [
            Finding(
                citation,
                Tier.UNRESOLVABLE,
                canonical,
                "CrossRef record has no author data — author not verifiable",
            )
        ]
    if not citation.claimed_first_author:
        # No claimed author to verify against (caller already guards this, but
        # keep the precondition explicit so the type is narrowed).
        return []
    claimed_raw = citation.claimed_first_author.strip()
    claimed = _surname_key(claimed_raw)
    first_raw = families_raw[0] if families_raw else ""
    first = _surname_key(first_raw)
    all_norm = [_surname_key(a) for a in families_raw]

    conf = " (low-confidence match)" if canonical.low_confidence else ""

    if claimed == first:
        # First-author matches after normalization.
        if _surname_raw(claimed_raw) != _surname_raw(first_raw):
            return [
                Finding(
                    citation,
                    Tier.COSMETIC,
                    canonical,
                    f'diacritic/spelling: CrossRef has "{first_raw}"{conf}',
                )
            ]
        # True match → check year.
        if citation.claimed_year and canonical.year and citation.claimed_year != canonical.year:
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
                f"DOI resolves to {first_raw} ({canonical.year}) — possibly wrong DOI{conf}",
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


def cross_check_pubmed(
    citation: Citation,
    canonical: CanonicalRecord | None,
    findings: list[Finding],
    pubmed: PubMedRecord | None,
) -> None:
    """Reconcile CrossRef-derived ``findings`` against a PubMed record in place.

    Annotates existing findings with a ``cross_check`` note and/or appends NEW
    findings (author/year disagreements PubMed sees that CrossRef didn't,
    retractions PubMed flags). Pure aside from mutating ``findings``; no I/O.

    Semantics:
      * CrossRef had no record (UNRESOLVABLE) + PubMed resolves → annotate the
        unresolvable finding: evaluable via PubMed (low confidence).
      * An AUTHOR/YEAR finding that PubMed *corroborates* (PubMed agrees with
        CrossRef, not the claim) → note "corroborated by PubMed", tier kept.
      * An AUTHOR/YEAR finding that PubMed *contradicts* (PubMed agrees with the
        cited claim) → conflict note, tier kept (manual review).
      * No CrossRef author/year finding but PubMed disagrees with the claim →
        NEW AUTHOR/YEAR finding "raised by PubMed".
      * Retraction is OR-combined: PubMed-flagged retraction/EoC appends a
        RETRACTION finding if CrossRef didn't already.
    """
    if pubmed is None:
        return

    claimed_author = _surname_key(citation.claimed_first_author)
    pm_author = normalize_surname(pubmed.first_author_surname)
    claimed_year = citation.claimed_year

    # 1. Retraction / expression of concern — OR-combine with CrossRef.
    if (pubmed.retracted or pubmed.eoc) and not any(f.tier is Tier.RETRACTION for f in findings):
        label = "RETRACTED" if pubmed.retracted else "Expression of concern"
        findings.append(
            Finding(
                citation,
                Tier.RETRACTION,
                canonical,
                f"{label} per PubMed",
                cross_check="raised by PubMed",
            )
        )

    # 2. CrossRef had no usable record → PubMed makes it evaluable.
    if canonical is None:
        for f in findings:
            if f.tier is Tier.UNRESOLVABLE:
                f.cross_check = "resolved via PubMed; CrossRef had no record (low confidence)"
        return

    author_year_findings = [f for f in findings if f.tier in (Tier.AUTHOR, Tier.YEAR)]

    # 3. Existing AUTHOR/YEAR findings — does PubMed back CrossRef or the claim?
    for f in author_year_findings:
        if f.tier is Tier.AUTHOR and pm_author and claimed_author:
            if pm_author == claimed_author:
                f.cross_check = (
                    "⚠ PubMed agrees with the cited author — CrossRef and PubMed "
                    "conflict; verify manually"
                )
            else:
                f.cross_check = "corroborated by PubMed"
        elif f.tier is Tier.YEAR and pubmed.year and claimed_year:
            if pubmed.year == claimed_year:
                f.cross_check = (
                    "⚠ PubMed agrees with the cited year — CrossRef and PubMed "
                    "conflict; verify manually"
                )
            else:
                f.cross_check = "corroborated by PubMed"

    # 4. CrossRef raised no author finding but PubMed disagrees with the claim.
    has_author_finding = any(f.tier is Tier.AUTHOR for f in findings)
    if not has_author_finding and claimed_author and pm_author and pm_author != claimed_author:
        findings.append(
            Finding(
                citation,
                Tier.AUTHOR,
                canonical,
                f"PubMed first author is {pubmed.first_author_surname}",
                cross_check="raised by PubMed",
            )
        )

    # 5. CrossRef raised no year finding but PubMed disagrees with the claimed year.
    has_year_finding = any(f.tier is Tier.YEAR for f in findings)
    if (
        not has_year_finding
        and claimed_year
        and pubmed.year
        and pubmed.year != claimed_year
        # Only when the author lines up — otherwise the author finding carries it.
        and (not pm_author or not claimed_author or pm_author == claimed_author)
    ):
        findings.append(
            Finding(
                citation,
                Tier.YEAR,
                canonical,
                f"PubMed year is {pubmed.year}",
                cross_check="raised by PubMed",
            )
        )
