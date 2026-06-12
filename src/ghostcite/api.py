"""Public API for ghostcite -- importable library surface.

Exposes:
  check_doi   -- verify a single DOI against CrossRef + optional retraction DB
  check_text  -- verify all citations in a text blob (bibtex/markdown/doi list)
  CheckResult -- collapsed result for a single DOI lookup
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ghostcite.compare import evaluate
from ghostcite.crossref import CrossRefClient
from ghostcite.models import CanonicalRecord, Citation, Finding, Tier
from ghostcite.parsers import parse

if TYPE_CHECKING:
    from ghostcite.cache import DoiCache
    from ghostcite.retractions import RetractionDB

# ---------------------------------------------------------------------------
# Tier priority (highest = most severe) for collapsing multiple findings
# ---------------------------------------------------------------------------

_TIER_PRIORITY: dict[Tier, int] = {
    Tier.AUTHOR: 6,
    Tier.RETRACTION: 5,
    Tier.YEAR: 4,
    Tier.COSMETIC: 3,
    Tier.UNRESOLVABLE: 2,
    Tier.OK: 1,
}

_GHOST_TIERS = {Tier.AUTHOR, Tier.YEAR, Tier.RETRACTION}


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Collapsed verification result for a single DOI.

    Attributes
    ----------
    doi:
        The DOI that was looked up (may be None if not present in source).
    tier:
        Highest-severity :class:`~ghostcite.models.Tier` among all findings.
    is_ghost:
        True iff ``tier`` is AUTHOR, YEAR, or RETRACTION -- i.e. the citation
        is likely a ghost cite.
    message:
        Human-readable summary of the worst finding.
    canonical:
        The :class:`~ghostcite.models.CanonicalRecord` returned by CrossRef,
        or ``None`` when the DOI did not resolve.
    cross_check:
        Optional cross-check annotation (e.g. from PubMed). ``None`` in v1.
    """

    doi: str | None
    tier: Tier
    is_ghost: bool
    message: str
    canonical: CanonicalRecord | None
    cross_check: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Shared lookup + evaluate helper (used by both check_text and cli.py)
# ---------------------------------------------------------------------------


def _process_citation(
    citation: Citation,
    *,
    client: CrossRefClient,
    retraction_db: RetractionDB | None = None,
    cache: DoiCache | None = None,
) -> tuple[list[Finding], CanonicalRecord | None]:
    """Resolve one citation and return (findings, canonical_record).

    Handles both the DOI path and the bibliographic-search fallback, plus
    retraction DB override synthesis -- exactly the logic from cli.py inner
    loop, factored out so both check_text and cli.main share one implementation.

    Returns
    -------
    tuple[list[Finding], CanonicalRecord | None]
        The evaluated findings and the CrossRef canonical record (which callers
        such as cli.py may need for PubMed cross-check).
    """
    if citation.doi:
        rec = client.lookup_by_doi(citation.doi, cache=cache)
    else:
        rec = client.search_bibliographic(
            citation.claimed_first_author, citation.claimed_year, citation.claimed_title
        )

    if retraction_db is not None:
        doi_for_lookup = citation.doi or (rec.doi if rec else "") or ""
        override = retraction_db.lookup(doi_for_lookup)
        retraction_source = retraction_db.source_label
        findings = evaluate(
            citation, rec, retraction_source=retraction_source, retraction_override=override
        )
    else:
        findings = evaluate(citation, rec)

    return findings, rec


# ---------------------------------------------------------------------------
# Public API: check_doi
# ---------------------------------------------------------------------------


def check_doi(
    doi: str,
    *,
    claimed_author: str | None = None,
    claimed_year: int | None = None,
    claimed_title: str | None = None,
    client: CrossRefClient | None = None,
    retraction_db: RetractionDB | None = None,
    cache: DoiCache | None = None,
) -> CheckResult:
    """Verify a single DOI against CrossRef.

    Parameters
    ----------
    doi:
        The DOI to look up.
    claimed_author:
        The first author as cited (free text, e.g. ``"Smith J"``).
    claimed_year:
        The year as cited.
    claimed_title:
        The title as cited (used for disambiguation only).
    client:
        An existing :class:`~ghostcite.crossref.CrossRefClient`. When ``None``
        a temporary client is created (and closed) for this call.
    retraction_db:
        Optional :class:`~ghostcite.retractions.RetractionDB` snapshot.
    cache:
        Optional :class:`~ghostcite.cache.DoiCache` for offline-first lookups.

    Returns
    -------
    CheckResult
        Collapsed to the highest-severity finding. ``tier=OK`` when clean.
    """
    citation = Citation(
        raw=doi,
        doi=doi,
        claimed_first_author=claimed_author,
        claimed_year=claimed_year,
        claimed_title=claimed_title,
    )

    if client is not None:
        findings, _rec = _process_citation(
            citation, client=client, retraction_db=retraction_db, cache=cache
        )
        return _collapse(doi, findings)

    with CrossRefClient() as owned_client:
        findings, _rec = _process_citation(
            citation, client=owned_client, retraction_db=retraction_db, cache=cache
        )
    return _collapse(doi, findings)


# ---------------------------------------------------------------------------
# Public API: check_text
# ---------------------------------------------------------------------------


def check_text(
    text: str,
    *,
    fmt: str = "auto",
    client: CrossRefClient | None = None,
    retraction_db: RetractionDB | None = None,
    cache: DoiCache | None = None,
) -> list[Finding]:
    """Parse a text blob and verify all citations found in it.

    Parameters
    ----------
    text:
        Raw text of a ``.bib``, markdown, or bare-DOI-list file.
    fmt:
        ``"auto"`` (detect), ``"bibtex"``, ``"markdown"``, or ``"doi"``.
    client:
        An existing :class:`~ghostcite.crossref.CrossRefClient`. When ``None``
        a temporary client is created for this call.
    retraction_db:
        Optional :class:`~ghostcite.retractions.RetractionDB` snapshot.
    cache:
        Optional :class:`~ghostcite.cache.DoiCache` for offline-first lookups.

    Returns
    -------
    list[Finding]
        One or more :class:`~ghostcite.models.Finding` per problematic citation.
        Empty list means all citations are clean.
    """
    citations = parse(text, fmt=fmt)

    def _run(c: CrossRefClient) -> list[Finding]:
        out: list[Finding] = []
        for cit in citations:
            findings, _rec = _process_citation(
                cit, client=c, retraction_db=retraction_db, cache=cache
            )
            out.extend(findings)
        return out

    if client is not None:
        return _run(client)

    with CrossRefClient() as owned_client:
        return _run(owned_client)


# ---------------------------------------------------------------------------
# Collapse helper
# ---------------------------------------------------------------------------


def _collapse(doi: str | None, findings: list[Finding]) -> CheckResult:
    """Collapse a list of findings to the single highest-severity CheckResult."""
    if not findings:
        return CheckResult(
            doi=doi,
            tier=Tier.OK,
            is_ghost=False,
            message="OK",
            canonical=None,
        )

    worst = max(findings, key=lambda f: _TIER_PRIORITY.get(f.tier, 0))
    return CheckResult(
        doi=doi,
        tier=worst.tier,
        is_ghost=worst.tier in _GHOST_TIERS,
        message=worst.message,
        canonical=worst.canonical,
        cross_check=worst.cross_check,
    )
