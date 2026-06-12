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
