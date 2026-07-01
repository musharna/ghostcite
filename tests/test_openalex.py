from __future__ import annotations

import httpx
import pytest

from ghostcite.compare import cross_check_openalex, evaluate
from ghostcite.models import CanonicalRecord, Citation, OpenAlexRecord, Tier
from ghostcite.openalex import _BASE, OpenAlexClient, _record_from_work, _surname

# ---------------------------------------------------------------------------
# _surname helper
# ---------------------------------------------------------------------------


def test_surname_simple():
    assert _surname("Alice Smith") == "smith"


def test_surname_display_name_last_token():
    # OpenAlex display_name is "Firstname Lastname" — last non-initials token
    assert _surname("John A. Doe") == "doe"


def test_surname_initials_only_returns_none():
    # If every token is initials we get None
    assert _surname("J. A.") is None


def test_surname_none_input():
    assert _surname(None) is None


def test_surname_empty():
    assert _surname("") is None


def test_surname_single_token():
    # A lone token is always the surname even if all-caps
    assert _surname("LI") == "li"


def test_surname_diacritics_normalized():
    assert _surname("María García") == "garcia"


# ---------------------------------------------------------------------------
# _record_from_work
# ---------------------------------------------------------------------------


def _make_work(
    *,
    first_author="Alice Smith",
    year=2024,
    title="A study",
    retracted=False,
):
    return {
        "authorships": [{"author": {"display_name": first_author}}],
        "publication_year": year,
        "title": title,
        "is_retracted": retracted,
    }


def test_record_from_work_basic():
    rec = _record_from_work(_make_work())
    assert rec.first_author_surname == "smith"
    assert rec.year == 2024
    assert rec.title == "A study"
    assert rec.retracted is False


def test_record_from_work_retracted():
    rec = _record_from_work(_make_work(retracted=True))
    assert rec.retracted is True


def test_record_from_work_no_authorships():
    work = {"authorships": [], "publication_year": 2021, "title": "T", "is_retracted": False}
    rec = _record_from_work(work)
    assert rec.first_author_surname is None


def test_record_from_work_null_year():
    work = {
        "authorships": [{"author": {"display_name": "Doe"}}],
        "publication_year": None,
        "title": "T",
        "is_retracted": False,
    }
    rec = _record_from_work(work)
    assert rec.year is None


# ---------------------------------------------------------------------------
# OpenAlexClient — mock HTTP via pytest-httpx
# ---------------------------------------------------------------------------

_DOI = "10.1038/s41586-024-07487-w"
_OA_URL = f"{_BASE}/works/doi:{_DOI}"


def _work_payload(*, first_author="Alice Smith", year=2024, title="A study", retracted=False):
    return {
        "authorships": [{"author": {"display_name": first_author}}],
        "publication_year": year,
        "title": title,
        "is_retracted": retracted,
    }


def test_lookup_by_doi_returns_record(httpx_mock):
    httpx_mock.add_response(url=_OA_URL, json=_work_payload())
    with OpenAlexClient() as oa:
        rec = oa.lookup_by_doi(_DOI)
    assert isinstance(rec, OpenAlexRecord)
    assert rec.first_author_surname == "smith"
    assert rec.year == 2024


def test_lookup_by_doi_404_returns_none(httpx_mock):
    httpx_mock.add_response(url=_OA_URL, status_code=404)
    with OpenAlexClient() as oa:
        rec = oa.lookup_by_doi(_DOI)
    assert rec is None


def test_lookup_by_doi_mailto_param(httpx_mock):
    """When mailto is set the request URL should include the mailto query param."""

    captured = []

    def handler(request: httpx.Request):
        captured.append(str(request.url))
        return httpx.Response(200, json=_work_payload())

    httpx_mock.add_callback(handler)
    with OpenAlexClient(mailto="test@example.org") as oa:
        oa.lookup_by_doi(_DOI)
    assert captured
    assert "mailto=test%40example.org" in captured[0] or "mailto=test@example.org" in captured[0]


def test_lookup_by_doi_500_raises(httpx_mock):
    httpx_mock.add_response(url=_OA_URL, status_code=500)
    with OpenAlexClient() as oa:
        with pytest.raises(httpx.HTTPStatusError):
            oa.lookup_by_doi(_DOI)


def test_doi_with_fragment_is_url_encoded(httpx_mock):
    # '#' in a DOI must be percent-encoded, not sent raw (which would truncate
    # the identifier at the fragment boundary).
    encoded = f"{_BASE}/works/doi:10.1234/abc%23frag"
    httpx_mock.add_response(url=encoded, json=_work_payload())
    with OpenAlexClient() as oa:
        oa.lookup_by_doi("10.1234/abc#frag")
    requested = str(httpx_mock.get_requests()[0].url)
    assert "%23frag" in requested
    assert "#frag" not in requested


# ---------------------------------------------------------------------------
# cross_check_openalex — reconciliation logic (mirrors test_cross_check.py)
# ---------------------------------------------------------------------------


def _cit(author="Li", year=2024, doi="10.1/x", title="A study of cells"):
    return Citation(
        raw="x",
        source_line=1,
        doi=doi,
        claimed_first_author=author,
        claimed_year=year,
        claimed_title=title,
    )


def test_oa_404_plus_oa_resolves_yields_fallback_note():
    c = _cit(author="Chen", year=2024)
    findings = evaluate(c, None)
    assert findings and findings[0].tier is Tier.UNRESOLVABLE
    oa = OpenAlexRecord(first_author_surname="chen", year=2024)
    cross_check_openalex(c, None, findings, oa)
    assert any(
        f.cross_check and "via OpenAlex" in f.cross_check and "no record" in f.cross_check
        for f in findings
    )


def test_oa_author_finding_openalex_corroborates_crossref():
    c = _cit(author="Li")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings[0].tier is Tier.AUTHOR
    oa = OpenAlexRecord(first_author_surname="chen", year=2024)
    cross_check_openalex(c, rec, findings, oa)
    f = next(f for f in findings if f.tier is Tier.AUTHOR)
    assert f.cross_check and "corroborated by OpenAlex" in f.cross_check
    assert f.tier is Tier.AUTHOR


def test_oa_author_finding_openalex_agrees_with_claim_conflicts():
    c = _cit(author="Li")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings[0].tier is Tier.AUTHOR
    oa = OpenAlexRecord(first_author_surname="li", year=2024)
    cross_check_openalex(c, rec, findings, oa)
    f = next(f for f in findings if f.tier is Tier.AUTHOR)
    assert f.cross_check and "conflict" in f.cross_check.lower()
    assert f.tier is Tier.AUTHOR


def test_oa_crossref_ok_openalex_disagrees_raises_new_finding():
    c = _cit(author="Chen")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings == []
    cross_check_openalex(c, rec, findings, OpenAlexRecord(first_author_surname="singh"))
    assert any(
        f.tier is Tier.AUTHOR and f.cross_check and "raised by OpenAlex" in f.cross_check
        for f in findings
    )


def test_oa_crossref_ok_openalex_year_disagrees_raises_year_finding():
    c = _cit(author="Chen", year=2024)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings == []
    oa = OpenAlexRecord(first_author_surname="chen", year=2019)
    cross_check_openalex(c, rec, findings, oa)
    assert any(
        f.tier is Tier.YEAR and f.cross_check and "raised by OpenAlex" in f.cross_check
        for f in findings
    )


def test_oa_retraction_only_from_openalex_raises_retraction():
    c = _cit(author="Chen", year=2024)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    assert findings == []
    oa = OpenAlexRecord(first_author_surname="chen", year=2024, retracted=True)
    cross_check_openalex(c, rec, findings, oa)
    assert any(f.tier is Tier.RETRACTION for f in findings)


def test_oa_year_finding_openalex_no_year_notes_not_verifiable():
    c = _cit(author="Chen", year=2024)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2019, title="A study of cells")
    findings = evaluate(c, rec)
    f = next(f for f in findings if f.tier is Tier.YEAR)
    assert f.cross_check is None
    oa = OpenAlexRecord(first_author_surname="chen", year=None)
    cross_check_openalex(c, rec, findings, oa)
    assert f.cross_check == "OpenAlex record had no author/year data — not verifiable"


def test_oa_author_finding_openalex_empty_surname_notes_not_verifiable():
    c = _cit(author="Li")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    f = next(f for f in findings if f.tier is Tier.AUTHOR)
    assert f.cross_check is None
    oa = OpenAlexRecord(first_author_surname="", year=2024)
    cross_check_openalex(c, rec, findings, oa)
    assert f.cross_check == "OpenAlex record had no author/year data — not verifiable"


def test_oa_none_openalex_is_noop():
    c = _cit(author="Chen")
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, title="A study of cells")
    findings = evaluate(c, rec)
    before = list(findings)
    cross_check_openalex(c, rec, findings, None)
    assert findings == before


# ---------------------------------------------------------------------------
# CLI: multi-value --cross-check parsing
# ---------------------------------------------------------------------------

from ghostcite.cli import _parse_args  # noqa: E402


def test_parse_cross_check_pubmed_single():
    args = _parse_args(["myfile.bib", "--cross-check", "pubmed"])
    assert "pubmed" in args.cross_sources


def test_parse_cross_check_openalex_single():
    args = _parse_args(["myfile.bib", "--cross-check", "openalex"])
    assert "openalex" in args.cross_sources


def test_parse_cross_check_multi():
    args = _parse_args(["myfile.bib", "--cross-check", "pubmed,openalex"])
    assert args.cross_sources == {"pubmed", "openalex"}


def test_parse_cross_check_none_gives_empty_set():
    args = _parse_args(["myfile.bib", "--cross-check", "none"])
    assert args.cross_sources == set()


def test_parse_cross_check_default_none():
    args = _parse_args(["myfile.bib"])
    assert args.cross_sources == set()


def test_parse_cross_check_unknown_source_exits_2():
    with pytest.raises(SystemExit) as exc:
        _parse_args(["myfile.bib", "--cross-check", "scopus"])
    assert exc.value.code == 2


def test_parse_openalex_mailto_flag():
    args = _parse_args(["myfile.bib", "--openalex-mailto", "test@example.org"])
    assert args.openalex_mailto == "test@example.org"
