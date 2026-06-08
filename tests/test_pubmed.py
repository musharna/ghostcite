from __future__ import annotations

from pathlib import Path

import pytest

from ghostcite.pubmed import _ESEARCH, _ESUMMARY, PubMedClient, PubMedError


def _esearch_url(doi: str) -> str:
    # pytest-httpx matches the full URL including query string.
    from urllib.parse import urlencode

    params = urlencode(
        {"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json", "tool": "ghostcite"}
    )
    return f"{_ESEARCH}?{params}"


def _esummary_url(pmid: str) -> str:
    from urllib.parse import urlencode

    params = urlencode({"db": "pubmed", "id": pmid, "retmode": "json", "tool": "ghostcite"})
    return f"{_ESUMMARY}?{params}"


def test_resolve_pmid_returns_first_id(httpx_mock):
    httpx_mock.add_response(
        url=_esearch_url("10.3390/plants13060869"),
        json={"esearchresult": {"idlist": ["38592861"]}},
    )
    with PubMedClient() as pm:
        assert pm.resolve_pmid("10.3390/plants13060869") == "38592861"


def test_resolve_pmid_empty_idlist_returns_none(httpx_mock):
    httpx_mock.add_response(
        url=_esearch_url("10.0/missing"),
        json={"esearchresult": {"idlist": []}},
    )
    with PubMedClient() as pm:
        assert pm.resolve_pmid("10.0/missing") is None


def test_summary_parses_chen_m(httpx_mock):
    httpx_mock.add_response(
        url=_esummary_url("38592861"),
        json={
            "result": {
                "38592861": {
                    "authors": [{"name": "Chen M"}, {"name": "Zhang Y"}],
                    "pubdate": "2024 Mar 18",
                    "title": "Integrated Transcriptome Analysis",
                    "pubtype": ["Journal Article"],
                }
            }
        },
    )
    with PubMedClient() as pm:
        rec = pm.summary("38592861")
    assert rec.first_author_surname == "chen"  # normalized (lowercased) surname key
    assert rec.year == 2024
    assert rec.retracted is False
    assert rec.eoc is False


def test_summary_raises_on_error_key(httpx_mock):
    httpx_mock.add_response(
        url=_esummary_url("999999999"),
        json={"result": {"999999999": {"error": "cannot get document summary"}}},
    )
    with PubMedClient() as pm:
        with pytest.raises(PubMedError):
            pm.summary("999999999")


def test_summary_retracted_via_pubtype(httpx_mock):
    httpx_mock.add_response(
        url=_esummary_url("9500320"),
        json={
            "result": {
                "9500320": {
                    "authors": [{"name": "Wakefield AJ"}],
                    "pubdate": "1998 Feb 28",
                    "title": "Ileal-lymphoid-nodular hyperplasia",
                    "pubtype": ["Journal Article", "Retracted Publication"],
                }
            }
        },
    )
    with PubMedClient() as pm:
        rec = pm.summary("9500320")
    assert rec.retracted is True


def test_summary_eoc_via_pubtype(httpx_mock):
    httpx_mock.add_response(
        url=_esummary_url("12345"),
        json={
            "result": {
                "12345": {
                    "authors": [{"name": "Smith J"}],
                    "pubdate": "2010",
                    "title": "Something",
                    "pubtype": ["Journal Article", "Expression of Concern"],
                }
            }
        },
    )
    with PubMedClient() as pm:
        rec = pm.summary("12345")
    assert rec.eoc is True
    assert rec.retracted is False


def test_params_injects_tool_and_omits_unset_email_key():
    pm = PubMedClient()
    params = pm._params({"db": "pubmed"})
    assert params["tool"] == "ghostcite"
    assert params["retmode"] == "json"
    assert "email" not in params
    assert "api_key" not in params


def test_params_includes_email_and_key_when_set():
    pm = PubMedClient(email="x@example.org", api_key="KEY123")
    params = pm._params({"db": "pubmed"})
    assert params["email"] == "x@example.org"
    assert params["api_key"] == "KEY123"


def test_no_personal_email_literal_in_module():
    src = Path("src/ghostcite/pubmed.py").read_text()
    assert "@gmail" not in src
    assert "mjarnold" not in src
