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
    httpx_mock.add_response(url="https://api.crossref.org/works/10.3390/plants13060869", json=WORK)
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


def test_doi_with_fragment_is_url_encoded(httpx_mock):
    # A DOI containing '#' must be percent-encoded, or the fragment would be
    # stripped and a *different* identifier silently queried.
    encoded = "https://api.crossref.org/works/10.1234/abc%23frag"
    httpx_mock.add_response(url=encoded, json=WORK)
    with CrossRefClient() as c:
        c.lookup_by_doi("10.1234/abc#frag")
    requested = str(httpx_mock.get_requests()[0].url)
    assert "%23frag" in requested
    assert "#frag" not in requested


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
        rec = c.search_bibliographic("Ngou", 2021, "Mutual potentiation of plant immunity")
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


# ---------------------------------------------------------------------------
# Cache read-through tests
# ---------------------------------------------------------------------------


def test_cache_hit_skips_network(httpx_mock, tmp_path):
    """Second call with same cache must not make a network request."""
    from ghostcite.cache import MISS, DoiCache

    url = "https://api.crossref.org/works/10.3390/plants13060869"
    httpx_mock.add_response(url=url, json=WORK)

    cache = DoiCache(cache_dir=tmp_path / "doi")
    doi = "10.3390/plants13060869"

    with CrossRefClient() as c:
        # First call: cache miss -> network -> store
        rec1 = c.lookup_by_doi(doi, cache=cache)
        assert rec1 is not None
        assert rec1.authors[0] == "Chen"
        assert cache.get(doi) is not MISS  # stored

        # Second call: cache hit -> no network request (httpx_mock has only 1 response)
        rec2 = c.lookup_by_doi(doi, cache=cache)
        assert rec2 is not None
        assert rec2.authors[0] == "Chen"


def test_cache_stores_404_none(httpx_mock, tmp_path):
    """A 404 response is stored as None in the cache (known-absent sentinel)."""
    from ghostcite.cache import DoiCache

    url = "https://api.crossref.org/works/10.0/missing"
    httpx_mock.add_response(url=url, status_code=404)

    cache = DoiCache(cache_dir=tmp_path / "doi")
    doi = "10.0/missing"

    with CrossRefClient() as c:
        rec = c.lookup_by_doi(doi, cache=cache)
    assert rec is None
    # Second access: cache returns None without network
    result = cache.get(doi)
    assert result is None  # cached 404, not MISS


def test_no_cache_arg_unchanged(httpx_mock):
    """When cache=None, behaviour is identical to before (no cache logic)."""
    url = "https://api.crossref.org/works/10.3390/plants13060869"
    httpx_mock.add_response(url=url, json=WORK)
    with CrossRefClient() as c:
        rec = c.lookup_by_doi("10.3390/plants13060869")  # no cache kwarg
    assert rec is not None
    assert rec.year == 2024


def test_cached_hit_returned_without_network(httpx_mock, tmp_path):
    """Pre-seeded cache entry is returned without touching the network at all."""
    from ghostcite.cache import DoiCache
    from ghostcite.models import CanonicalRecord

    cache = DoiCache(cache_dir=tmp_path / "doi")
    doi = "10.1234/preseed"
    seeded = CanonicalRecord(doi=doi, authors=["Preseed"], year=2021)
    cache.put(doi, seeded)

    # No httpx mock response registered -- any network call would raise
    with CrossRefClient() as c:
        rec = c.lookup_by_doi(doi, cache=cache)
    assert rec is not None
    assert rec.authors[0] == "Preseed"
