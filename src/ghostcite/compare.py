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
    # A lone token is always the surname, never an initials cluster — keep it
    # even if it looks like initials (e.g. an all-caps "LI"). Only strip
    # initials-looking tokens when there is at least one other token to fall
    # back on ("Smith J" → ["Smith"], "J Smith" → ["Smith"]).
    tokens = name.split()
    if len(tokens) <= 1:
        return tokens
    return [t for t in tokens if not _is_initials(t)]


def _surname_key(name: str | None) -> str:
    """Surname comparison key: drop standalone initial tokens
    (e.g. "Smith J", "J Smith", "Smith JA") before normalizing, so a claimed
    author carrying initials still matches a bare CrossRef family name."""
    if not name:
        return ""
    return normalize_surname(" ".join(_surname_tokens(name)))


def _surname_raw(name: str | None) -> str:
    """Initial-stripped surname, diacritics PRESERVED, lowercased, despaced.
    For the CLAIMED author: drops initials ("Smith J" → "smith") so an
    initials-only difference doesn't read as a diacritic difference once
    `_surname_key` has matched the keys."""
    if not name:
        return ""
    return "".join(_surname_tokens(name)).lower()


def _canonical_raw(name: str | None) -> str:
    """Like `_surname_raw` but for a CANONICAL family name (CrossRef/PubMed):
    diacritics preserved, lowercased, despaced, NO initials-stripping — an
    all-caps family ("BURGER") is a real surname, not an initials cluster."""
    if not name:
        return ""
    return "".join(name.split()).lower()


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


_VENUE_STOP = {
    "the",
    "of",
    "and",
    "for",
    "on",
    "in",
    "journal",
    "proceedings",
    "annals",
    "review",
    "reviews",
}


def _venue_norm(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return "".join(c if c.isalnum() else " " for c in ascii_only)


def _venue_tokens(name: str) -> list[str]:
    return [w for w in _venue_norm(name).split() if w not in _VENUE_STOP and len(w) > 1]


_VENUE_INITIALISM_STOP = {"the", "of", "and", "for", "on", "in", "a", "an"}


def _venue_initialism(name: str) -> str:
    """First letter of each non-connector word: used for acronym matching.

    Uses a smaller stop set than _venue_tokens so that "Proceedings", "Journal",
    etc. contribute their initial (PNAS = Proceedings National Academy Sciences;
    JMB = Journal Molecular Biology)."""
    words = [w for w in _venue_norm(name).split() if w not in _VENUE_INITIALISM_STOP]
    return "".join(w[0] for w in words if w)


def _prefix_covered(short_tokens: list[str], long_tokens: list[str]) -> bool:
    """True when every token in short_tokens is a prefix of some token in long_tokens.

    Handles dotted abbreviations: ["mol", "biol"] vs ["molecular", "biology"] → True.
    Also handles single-char initials: ["j", "mol", "biol"] vs ["molecular", "biology"] would
    still pass (j is a prefix of journal, but journal is stop-filtered; the check is directional
    and only needs the non-stop abbreviation tokens to be covered)."""
    return all(any(tok.startswith(s) for tok in long_tokens) for s in short_tokens)


def _venue_loose_tokens(name: str) -> list[str]:
    """Venue tokens with ONLY connectors removed (reuses _VENUE_INITIALISM_STOP).

    Unlike _venue_tokens, this keeps content words such as 'proceedings', 'review',
    'journal', 'annals' so that abbreviations of those words ('proc', 'rev', 'j')
    have a long-form token to match against in _is_abbrev_of.  _venue_tokens uses
    a wider stop set that strips those words; the asymmetry is what causes false
    positives like 'Phys. Rev. Lett.' → 'Physical Review Letters' (the wide set
    removes 'review' from the canonical side, leaving 'rev' with nothing to match)."""
    return [w for w in _venue_norm(name).split() if w not in _VENUE_INITIALISM_STOP and len(w) >= 2]


def _token_abbrev_match(short: str, long: str) -> bool:
    """True when short token is an abbreviation of (or equal to) long token.

    Matches:
      - prefix: long.startswith(short)  e.g. "phys"→"physical", "lett"→"letters"
      - subsequence (len>=2, same first letter): short[0]==long[0] and short is a subsequence of long
        e.g. "natl"→"national", "acad"→"academy", "sci"→"sciences", "proc"→"proceedings"

    The subsequence arm deliberately requires len(short)>=2 so that a bare single-letter
    token cannot absorb unrelated long tokens — single-char tokens are handled
    by the existing initialism / compact-form checks."""
    if long.startswith(short):
        return True
    if len(short) >= 2 and short[0] == long[0]:
        # Check short is a subsequence of long
        it = iter(long)
        return all(c in it for c in short)
    return False


def _is_abbrev_of(short_tokens: list[str], long_tokens: list[str]) -> bool:
    """True when short_tokens looks like a multi-token abbreviation of long_tokens.

    Uses loose tokens (connector-stop only, so 'proceedings'/'review'/'journal' are
    present on the long side) to avoid the asymmetric stop-word bug in _prefix_covered.

    Rule:
      - For each short token, find a DISTINCT long token it abbreviation-matches
        (_token_abbrev_match).
      - At least 2 short tokens must be matched ('covered').
      - At most 1 short token may remain unmatched ('tolerance' for trailing qualifiers
        like 'U.S.A.' in 'Proc. Natl. Acad. Sci. U.S.A.').

    The ≥2-covered floor prevents single-token venues like 'Nature' from accidentally
    matching unrelated single-token venues like 'Cell' (neither would reach 2 covered).
    This function is only called when short_tokens has ≥2 tokens; callers with a
    single-token claimed form rely on the existing initialism/compact checks."""
    if len(short_tokens) < 2:
        return False
    remaining_long = list(long_tokens)
    covered = 0
    unmatched = 0
    for s in short_tokens:
        matched = False
        for i, long_tok in enumerate(remaining_long):
            if _token_abbrev_match(s, long_tok):
                remaining_long.pop(i)
                covered += 1
                matched = True
                break
        if not matched:
            unmatched += 1
    return covered >= 2 and unmatched <= 1


def venue_mismatch(claimed: str | None, canonical: str | None, *, threshold: float = 0.5) -> bool:
    """True only when the cited venue clearly disagrees with CrossRef's container-title.

    Abbreviation-tolerant / high precision: returns False when one side's initialism matches
    the other's (PNAS ~ Proceedings of the National Academy of Sciences; J Mol Biol ~ Journal of
    Molecular Biology), when one token set is a subset of the other, or when token-Jaccard >=
    threshold. Returns False if either side is missing or has no significant tokens."""
    if not claimed or not canonical:
        return False
    tc, tk = set(_venue_tokens(claimed)), set(_venue_tokens(canonical))
    if not tc or not tk:
        return False
    if tc <= tk or tk <= tc:
        return False
    # Initialism match either direction: a dotted/short form vs the spelled-out form.
    claimed_compact = _venue_norm(claimed).replace(" ", "")
    canon_compact = _venue_norm(canonical).replace(" ", "")
    if claimed_compact in (_venue_initialism(canonical), canon_compact):
        return False
    if canon_compact in (_venue_initialism(claimed), claimed_compact):
        return False
    # Token-level prefix match: handles dotted abbreviations like "J. Mol. Biol." vs
    # "Journal of Molecular Biology" where "mol"→"molecular" and "biol"→"biology".
    tc_list, tk_list = list(tc), list(tk)
    if _prefix_covered(tc_list, tk_list) or _prefix_covered(tk_list, tc_list):
        return False
    # Loose-token abbreviation match: fixes false positives where a content word
    # (review, proceedings) is in _VENUE_STOP and gets stripped from the canonical
    # token list, leaving its abbreviation (rev, proc) unmatched in _prefix_covered.
    # Uses _VENUE_INITIALISM_STOP (connectors only) so both sides keep those words.
    cl_loose = _venue_loose_tokens(claimed)
    ck_loose = _venue_loose_tokens(canonical)
    if _is_abbrev_of(cl_loose, ck_loose) or _is_abbrev_of(ck_loose, cl_loose):
        return False
    jacc = len(tc & tk) / len(tc | tk)
    return jacc < threshold


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


def title_mismatch(
    claimed: str | None,
    canonical: str | None,
    *,
    threshold: float = 0.3,
    min_tokens: int = 3,
) -> bool:
    """True when the cited title clearly disagrees with the canonical title.

    Conservative / high-precision (this gates CI): flags ONLY when BOTH titles
    carry at least ``min_tokens`` content tokens (so tiny/truncated titles are
    never judged) AND their Jaccard token overlap is below ``threshold`` (0.3,
    stricter than ``title_similar``'s 0.4, so subtitle/formatting variance on a
    correct citation does not trip it). Catches "identifier hijacking" — a DOI
    that resolves to a different paper than the one cited.
    """
    if not claimed or not canonical:
        return False
    tc, tk = _title_tokens(claimed), _title_tokens(canonical)
    if len(tc) < min_tokens or len(tk) < min_tokens:
        return False
    inter = len(tc & tk)
    union = len(tc | tk)
    return (inter / union) < threshold


def evaluate(
    citation: Citation,
    canonical: CanonicalRecord | None,
    retraction_source: str = "CrossRef",
    *,
    retraction_override: tuple[bool, bool] | None = None,
) -> list[Finding]:
    """Compare a claimed citation against the canonical record. Empty list = OK.

    ``retraction_override`` (retracted, eoc), when given, replaces the canonical
    record\'s retraction flags as the authoritative signal — used by the offline
    Retraction Watch source. It applies even when ``canonical is None`` (CrossRef
    could not resolve the DOI but the snapshot still knows it is retracted)."""
    if retraction_override is not None:
        retracted, eoc = retraction_override
    else:
        retracted = bool(canonical and canonical.retracted)
        eoc = bool(canonical and canonical.eoc)

    findings: list[Finding] = []
    if retracted:
        findings.append(
            Finding(citation, Tier.RETRACTION, canonical, f"RETRACTED per {retraction_source}")
        )
    elif eoc:
        findings.append(
            Finding(
                citation,
                Tier.RETRACTION,
                canonical,
                f"Expression of concern per {retraction_source}",
            )
        )

    if canonical is None:
        # No CrossRef record: the byline is genuinely unverifiable. The retraction
        # (if any) is already reported above.
        findings.append(Finding(citation, Tier.UNRESOLVABLE, None, "DOI not found / unresolvable"))
        return findings

    # Author/year only when the input actually claimed an author (not DOI-list mode).
    if citation.claimed_first_author:
        findings.extend(_author_year(citation, canonical))

    # Title mismatch (identifier hijacking): the DOI resolves to a different paper.
    # Fires independent of the author result, but suppressed when an AUTHOR finding
    # already carries the wrong-paper signal (avoids double-reporting). This fills the
    # gap where the claimed author coincidentally matches — or is absent — yet the
    # title clearly disagrees.
    if not any(f.tier is Tier.AUTHOR for f in findings) and title_mismatch(
        citation.claimed_title, canonical.title
    ):
        findings.append(
            Finding(
                citation,
                Tier.TITLE,
                canonical,
                f'DOI resolves to a different title: CrossRef has "{canonical.title}"',
            )
        )

    # Venue mismatch (warn-only): cited journal disagrees with CrossRef's container-title.
    # Suppressed when AUTHOR/TITLE already fired (those carry the wrong-paper signal).
    if not any(f.tier in (Tier.AUTHOR, Tier.TITLE) for f in findings) and venue_mismatch(
        citation.claimed_journal, canonical.journal
    ):
        findings.append(
            Finding(
                citation,
                Tier.VENUE,
                canonical,
                f'cited venue differs: CrossRef container is "{canonical.journal}"',
            )
        )

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
    # Asymmetric normalization: the claimed author is free text that may carry
    # initials ("Smith JA") → initials-strip it. A CrossRef `family` field is
    # ALWAYS a pure surname (even when ALL CAPS) → diacritic-fold only, never
    # initials-strip (else "TURING" → "" and a correct claim is flagged Tier A).
    claimed = _surname_key(claimed_raw)
    first_raw = families_raw[0] if families_raw else ""
    first = normalize_surname(first_raw)
    all_norm = [normalize_surname(a) for a in families_raw]

    conf = " (low-confidence match)" if canonical.low_confidence else ""

    if claimed == first:
        # First-author matches after normalization.
        if _surname_raw(claimed_raw) != _canonical_raw(first_raw):
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
    # PubMed's surname field is a pure surname (possibly ALL CAPS) — fold only,
    # don't initials-strip it (see _author_year for the same asymmetry).
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
    no_data_note = "PubMed record had no author/year data — not verifiable"
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
        else:
            # PubMed was consulted but lacks the usable author/year needed to
            # corroborate this finding — say so instead of leaving it silent.
            f.cross_check = no_data_note

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
