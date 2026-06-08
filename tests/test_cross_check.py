from __future__ import annotations

from ghostcite.compare import cross_check_pubmed, evaluate
from ghostcite.models import CanonicalRecord, Citation, PubMedRecord, Tier


def _cit(author="Li", year=2024, doi="10.1/x", title="A study of cells"):
    return Citation(
        raw="x",
        source_line=1,
        doi=doi,
        claimed_first_author=author,
        claimed_year=year,
        claimed_title=title,
    )


def test_404_plus_pubmed_resolves_yields_fallback_note():
    # CrossRef returned None → evaluate gives an UNRESOLVABLE finding.
    c = _cit(author="Chen", year=2024)
    findings = evaluate(c, None)
    assert findings and findings[0].tier is Tier.UNRESOLVABLE
    pm = PubMedRecord(pmid="1", first_author_surname="chen", year=2024)
    cross_check_pubmed(c, None, findings, pm)
    # The unresolvable finding is now annotated as resolved via PubMed.
    assert any(
        f.cross_check and "via PubMed" in f.cross_check and "no record" in f.cross_check
        for f in findings
    )


def test_author_finding_pubmed_corroborates_crossref():
    # CrossRef says Chen; claim is Li → AUTHOR finding. PubMed also says Chen.
    c = _cit(author="Li")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings[0].tier is Tier.AUTHOR
    pm = PubMedRecord(pmid="1", first_author_surname="chen", year=2024)
    cross_check_pubmed(c, rec, findings, pm)
    f = next(f for f in findings if f.tier is Tier.AUTHOR)
    assert f.cross_check and "corroborated by PubMed" in f.cross_check
    assert f.tier is Tier.AUTHOR  # tier unchanged


def test_author_finding_pubmed_agrees_with_claim_conflicts():
    # CrossRef says Chen (→ AUTHOR finding vs claim Li), but PubMed says Li.
    c = _cit(author="Li")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings[0].tier is Tier.AUTHOR
    pm = PubMedRecord(pmid="1", first_author_surname="li", year=2024)
    cross_check_pubmed(c, rec, findings, pm)
    f = next(f for f in findings if f.tier is Tier.AUTHOR)
    assert f.cross_check and "conflict" in f.cross_check.lower()
    assert f.tier is Tier.AUTHOR  # tier unchanged


def test_crossref_ok_pubmed_disagrees_raises_new_finding():
    # CrossRef agrees with claim (Chen) → no finding. PubMed says Singh → new AUTHOR finding.
    c = _cit(author="Chen")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings == []
    cross_check_pubmed(c, rec, findings, PubMedRecord(pmid="1", first_author_surname="singh"))
    assert any(
        f.tier is Tier.AUTHOR and f.cross_check and "raised by PubMed" in f.cross_check
        for f in findings
    )


def test_crossref_ok_pubmed_year_disagrees_raises_year_finding():
    c = _cit(author="Chen", year=2024)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings == []
    pm = PubMedRecord(pmid="1", first_author_surname="chen", year=2019)
    cross_check_pubmed(c, rec, findings, pm)
    assert any(
        f.tier is Tier.YEAR and f.cross_check and "raised by PubMed" in f.cross_check
        for f in findings
    )


def test_retraction_only_from_pubmed_raises_retraction():
    # CrossRef clean, PubMed flags retraction → RETRACTION finding appears.
    c = _cit(author="Chen", year=2024)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings == []
    pm = PubMedRecord(pmid="1", first_author_surname="chen", year=2024, retracted=True)
    cross_check_pubmed(c, rec, findings, pm)
    assert any(f.tier is Tier.RETRACTION for f in findings)


def test_none_pubmed_is_noop():
    c = _cit(author="Chen")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    before = list(findings)
    cross_check_pubmed(c, rec, findings, None)
    assert findings == before
