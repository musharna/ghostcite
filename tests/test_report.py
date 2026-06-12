import json

from ghostcite.models import CanonicalRecord, Citation, Finding, Tier
from ghostcite.report import render_json, render_text


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


def _ok_finding():
    c = Citation(raw="Ok A (2024)", source_line=5, claimed_first_author="Ok")
    return Finding(c, Tier.OK, None, "matches")


def test_text_filters_out_ok_findings():
    # Tier.OK is public API but should never appear in a report and must not
    # KeyError on the glyph table.
    out = render_text([_ok_finding(), _finding()], total=2, with_doi=1)
    assert "matches" not in out
    assert "Gerakari" in out


def test_text_handles_only_ok_findings():
    out = render_text([_ok_finding()], total=1, with_doi=0)
    assert "matches" not in out
    assert "0 findings" in out or "clean" in out.lower()


def test_json_filters_out_ok_findings():
    out = render_json([_ok_finding(), _finding()], total=2, with_doi=1)
    data = json.loads(out)
    assert data["summary"]["findings"] == 1
    assert [f["tier"] for f in data["findings"]] == ["A"]


def test_json_is_machine_readable():
    out = render_json([_finding()], total=46, with_doi=45)
    data = json.loads(out)
    assert data["summary"]["total"] == 46
    assert data["findings"][0]["tier"] == "A"
    assert data["findings"][0]["doi"] == "10.3390/cimb46080535"


def test_text_shows_retraction_source():
    out = render_text([], total=1, with_doi=1, retraction_source="CrossRef live")
    assert "retractions: CrossRef live" in out


def test_text_no_source_line_when_unset():
    out = render_text([], total=1, with_doi=1)
    assert "retractions:" not in out


def test_json_includes_retraction_source():
    out = render_json([], total=1, with_doi=1, retraction_source="Retraction Watch snapshot 2026-06-11")
    data = json.loads(out)
    assert data["summary"]["retraction_source"] == "Retraction Watch snapshot 2026-06-11"
