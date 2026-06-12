from __future__ import annotations

from ghostcite.compare import evaluate
from ghostcite.models import CanonicalRecord, Citation, Tier


def _retracted_cite():
    c = Citation(raw="x", doi="10.1/a", claimed_first_author="Doe", claimed_year=2000)
    rec = CanonicalRecord(doi="10.1/a", authors=["Doe"], year=2000, retracted=True)
    return c, rec


def test_default_source_is_crossref():
    c, rec = _retracted_cite()
    findings = evaluate(c, rec)
    assert any(f.tier is Tier.RETRACTION and "per CrossRef" in f.message for f in findings)


def test_custom_source_label():
    c, rec = _retracted_cite()
    findings = evaluate(c, rec, retraction_source="Retraction Watch snapshot 2026-06-11")
    assert any(
        f.tier is Tier.RETRACTION and "Retraction Watch snapshot 2026-06-11" in f.message
        for f in findings
    )


def test_eoc_uses_source_label():
    c = Citation(raw="x", doi="10.1/b", claimed_first_author="Doe", claimed_year=2000)
    rec = CanonicalRecord(doi="10.1/b", authors=["Doe"], year=2000, eoc=True)
    findings = evaluate(c, rec, retraction_source="Retraction Watch")
    assert any("Expression of concern per Retraction Watch" in f.message for f in findings)


def test_retraction_override_with_null_canonical():
    c = Citation(raw="x", doi="10.1/rw", claimed_first_author="Doe", claimed_year=2020)
    findings = evaluate(
        c, None, retraction_source="Retraction Watch", retraction_override=(True, False)
    )
    tiers = [f.tier for f in findings]
    assert Tier.RETRACTION in tiers
    assert Tier.UNRESOLVABLE in tiers
    assert any(f.tier == Tier.RETRACTION and "Retraction Watch" in f.message for f in findings)
    assert any(f.tier == Tier.UNRESOLVABLE and "DOI not found" in f.message for f in findings)
    assert all("no author data" not in f.message for f in findings)


def test_retraction_override_false_suppresses_retraction_on_flagged_rec():
    c = Citation(raw="x", doi="10.1/a", claimed_first_author="Doe", claimed_year=2000)
    rec = CanonicalRecord(doi="10.1/a", authors=["Doe"], year=2000, retracted=True)
    findings = evaluate(c, rec, retraction_source="CrossRef", retraction_override=(False, False))
    assert not any(f.tier is Tier.RETRACTION for f in findings)


def test_no_override_null_canonical_still_returns_unresolvable():
    c = Citation(raw="x", doi="10.1/z", claimed_first_author="Doe", claimed_year=2020)
    findings = evaluate(c, None)
    assert len(findings) == 1
    assert findings[0].tier is Tier.UNRESOLVABLE
    assert "DOI not found" in findings[0].message
