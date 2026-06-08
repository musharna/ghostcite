
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


def test_retraction_flags_from_relation():
    msg = {"relation": {"is-retracted-by": [{"id": "10.1/notice"}]}}
    assert _retraction_flags(msg) == (True, False)


def test_eoc_flag_from_update_to():
    msg = {"update-to": [{"type": "expression_of_concern", "DOI": "10.1/x"}]}
    assert _retraction_flags(msg) == (False, True)
