import pytest

from ghostcite.compare import evaluate
from ghostcite.crossref import CrossRefClient
from ghostcite.models import Citation, Tier

pytestmark = pytest.mark.live


def test_known_ghost_li_should_be_chen():
    # From the 2026-04-29 Phelipanche audit: cited "Li 2024", DOI is actually Chen et al.
    c = Citation(
        raw="Li X (2024)",
        doi="10.3390/plants13060869",
        claimed_first_author="Li",
        claimed_year=2024,
        claimed_title="Cell wall activity in Phelipanche",
    )
    with CrossRefClient() as client:
        rec = client.lookup_by_doi(c.doi)
    assert rec is not None and rec.authors, "CrossRef returned no record/authors"
    findings = evaluate(c, rec)
    assert any(f.tier is Tier.AUTHOR for f in findings)
    assert any("hen" in (f.message or "") for f in findings)  # Chen


def test_correct_citation_is_clean():
    c = Citation(
        raw="Chen M (2024)",
        doi="10.3390/plants13060869",
        claimed_first_author="Chen",
        claimed_year=2024,
    )
    with CrossRefClient() as client:
        rec = client.lookup_by_doi(c.doi)
    assert evaluate(c, rec) == []


def test_pacer_learns_interval_from_real_headers():
    # Two sequential real lookups; CrossRef advertises 5 req / 1s → 0.2s floor.
    with CrossRefClient() as client:
        client.lookup_by_doi("10.3390/plants13060869")
        client.lookup_by_doi("10.3390/plants13060869")
        assert client._pacer._min_interval == pytest.approx(0.2)


def test_known_retracted_doi_flags_R():
    # A well-known retracted paper (Wakefield 1998, Lancet). Verify CrossRef marks it.
    c = Citation(
        raw="x",
        doi="10.1016/s0140-6736(97)11096-0",
        claimed_first_author="Wakefield",
        claimed_year=1998,
    )
    with CrossRefClient() as client:
        rec = client.lookup_by_doi(c.doi)
    assert rec is not None
    findings = evaluate(c, rec)
    assert any(f.tier is Tier.RETRACTION for f in findings), (
        "expected retraction flag; if this fails, inspect rec + fix _retraction_flags"
    )
