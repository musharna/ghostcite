import json

from ghostcite.models import Citation, CanonicalRecord, Finding, Tier
from ghostcite.report import render_text, render_json


def _finding():
    c = Citation(
        raw="Li X (2024)",
        source_line=227,
        doi="10.3390/cimb46080535",
        claimed_first_author="Hsu",
        claimed_year=2024,
    )
    rec = CanonicalRecord(doi="10.3390/cimb46080535", authors=["Gerakari"], year=2024)
    return Finding(c, Tier.AUTHOR, rec, "CrossRef first author is Gerakari")


def test_text_lists_findings_and_counts():
    out = render_text([_finding()], total=46, with_doi=45)
    assert "A" in out and "Gerakari" in out and "10.3390/cimb46080535" in out
    assert "46" in out


def test_text_quiet_when_clean():
    out = render_text([], total=10, with_doi=10)
    assert "0 findings" in out or "clean" in out.lower()


def test_json_is_machine_readable():
    out = render_json([_finding()], total=46, with_doi=45)
    data = json.loads(out)
    assert data["summary"]["total"] == 46
    assert data["findings"][0]["tier"] == "A"
    assert data["findings"][0]["doi"] == "10.3390/cimb46080535"
