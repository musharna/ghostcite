"""Real-execution checks against the live OpenAlex API.

Skipped unless GHOSTCITE_LIVE=1 is set in the environment.

    GHOSTCITE_LIVE=1 python -m pytest tests/test_openalex_live.py -v
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live

_SKIP = pytest.mark.skipif(
    os.environ.get("GHOSTCITE_LIVE") != "1",
    reason="set GHOSTCITE_LIVE=1 to run live OpenAlex network checks",
)

# Wakefield 1998 (Lancet) — the canonical retracted paper; OpenAlex flags it.
_WAKEFIELD_DOI = "10.1016/S0140-6736(97)11096-0"

# A well-known nature paper with a stable OpenAlex record.
_STABLE_DOI = "10.1038/s41586-021-03819-2"


@_SKIP
def test_live_openalex_lookup_known_doi():
    from ghostcite.openalex import OpenAlexClient

    with OpenAlexClient() as oa:
        rec = oa.lookup_by_doi(_STABLE_DOI)
    assert rec is not None, "OpenAlex should resolve this stable DOI"
    assert rec.first_author_surname is not None
    assert rec.year is not None
    assert isinstance(rec.year, int)


@_SKIP
def test_live_openalex_404_returns_none():
    from ghostcite.openalex import OpenAlexClient

    with OpenAlexClient() as oa:
        rec = oa.lookup_by_doi("10.9999/this-doi-does-not-exist-ghostcite-test")
    assert rec is None


@_SKIP
def test_live_openalex_retraction_flagged():
    """OpenAlex should flag the Wakefield paper as retracted."""
    from ghostcite.openalex import OpenAlexClient

    with OpenAlexClient() as oa:
        rec = oa.lookup_by_doi(_WAKEFIELD_DOI)
    # OpenAlex may or may not index this specific DOI; if it does, retracted must be True.
    if rec is not None:
        assert rec.retracted is True, "Wakefield 1998 should be flagged as retracted by OpenAlex"
