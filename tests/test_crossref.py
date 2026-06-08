import httpx

from ghostcite.crossref import CrossRefClient, _retraction_flags

WORK = {
    "message": {
        "DOI": "10.3390/plants13060869",
        "author": [{"family": "Chen", "given": "Min"}, {"family": "Zhang"}],
        "title": ["Integrated Transcriptome and Proteome Analysis"],
        "container-title": ["Plants"],
        "published": {"date-parts": [[2024, 3, 1]]},
    }
}


def test_lookup_by_doi_parses_record(httpx_mock):
    httpx_mock.add_response(
        url="https://api.crossref.org/works/10.3390/plants13060869", json=WORK
    )
    with CrossRefClient() as c:
        rec = c.lookup_by_doi("10.3390/plants13060869")
    assert rec.authors[0] == "Chen"
    assert rec.year == 2024
    assert rec.journal == "Plants"
    assert rec.retracted is False


def test_lookup_returns_none_on_404(httpx_mock):
    httpx_mock.add_response(status_code=404)
    with CrossRefClient() as c:
        assert c.lookup_by_doi("10.0/missing") is None


def test_lookup_retries_once_on_429(httpx_mock):
    # A transient 429 (with Retry-After: 0 to keep the test fast) must be
    # retried once and the subsequent 200 parsed normally — not abort the run.
    url = "https://api.crossref.org/works/10.3390/plants13060869"
    httpx_mock.add_response(url=url, status_code=429, headers={"Retry-After": "0"})
    httpx_mock.add_response(url=url, json=WORK)
    with CrossRefClient() as c:
        rec = c.lookup_by_doi("10.3390/plants13060869")
    assert rec.authors[0] == "Chen"
    assert rec.year == 2024


def test_lookup_retries_once_on_503(httpx_mock):
    url = "https://api.crossref.org/works/10.3390/plants13060869"
    httpx_mock.add_response(url=url, status_code=503, headers={"Retry-After": "0"})
    httpx_mock.add_response(url=url, json=WORK)
    with CrossRefClient() as c:
        rec = c.lookup_by_doi("10.3390/plants13060869")
    assert rec.year == 2024


def test_retraction_flags_from_relation():
    msg = {"relation": {"is-retracted-by": [{"id": "10.1/notice"}]}}
    assert _retraction_flags(msg) == (True, False)


def test_eoc_flag_from_update_to():
    msg = {"update-to": [{"type": "expression_of_concern", "DOI": "10.1/x"}]}
    assert _retraction_flags(msg) == (False, True)


def test_retraction_flag_from_updated_by():
    # Real CrossRef schema (verified against Wakefield 1998 Lancet DOI): the
    # retracted work carries an ``updated-by`` item of type "retraction".
    msg = {
        "updated-by": [
            {"type": "correction", "DOI": "10.1/c"},
            {"type": "retraction", "DOI": "10.1/r"},
        ]
    }
    assert _retraction_flags(msg) == (True, False)


def test_eoc_flag_from_updated_by():
    msg = {"updated-by": [{"type": "expression_of_concern", "DOI": "10.1/e"}]}
    assert _retraction_flags(msg) == (False, True)


SEARCH = {
    "message": {
        "items": [
            {
                "DOI": "10.1038/s41586-021-00001",
                "author": [{"family": "Ngou"}],
                "title": ["Mutual potentiation of plant immunity"],
                "container-title": ["Nature"],
                "published": {"date-parts": [[2021]]},
            }
        ]
    }
}


def test_search_bibliographic_marks_low_confidence(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": "Ngou 2021 Mutual potentiation of plant immunity",
                "rows": 1,
            },
        ),
        json=SEARCH,
    )
    with CrossRefClient() as c:
        rec = c.search_bibliographic(
            "Ngou", 2021, "Mutual potentiation of plant immunity"
        )
    assert rec.doi == "10.1038/s41586-021-00001"
    assert rec.low_confidence is True


def test_search_returns_none_on_empty(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            "https://api.crossref.org/works",
            params={"query.bibliographic": "Nobody 1999 no such paper", "rows": 1},
        ),
        json={"message": {"items": []}},
    )
    with CrossRefClient() as c:
        assert c.search_bibliographic("Nobody", 1999, "no such paper") is None
