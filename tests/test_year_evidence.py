"""A year finding must rest on a year CrossRef actually holds.

The three records under tests/data/crossref_years/ are CrossRef responses
copied verbatim (trimmed to the fields ghostcite reads) on 2026-09-18. They
came out of published reference lists where 0.6.1 raised three one-year Tier B
findings, two of them against correct citations:

  * Benton & Donoghue, Mol Biol Evol 24:26 -- printed in the 2007 volume and
    cited as 2007 everywhere; CrossRef holds only the 2006 online date.
  * Bininda-Emonds et al. in "Biocomputing 2001" -- the proceedings is named
    for 2001 and printed in December 2000.
  * Phillips, Bennett & Lee, PNAS 106 -- online AND print dates are both 2009,
    so a citation saying 2010 contradicts a complete record. Still Tier B.
"""

from __future__ import annotations

import json
from pathlib import Path

from ghostcite.cache import DoiCache
from ghostcite.compare import evaluate
from ghostcite.crossref import _record_from_message
from ghostcite.models import Citation, Tier

DATA = Path(__file__).parent / "data" / "crossref_years"


def _record(name: str):
    return _record_from_message(json.loads((DATA / name).read_text()))


def _tiers(record, author: str, year: int) -> list[Tier]:
    cit = Citation(raw="", claimed_first_author=author, claimed_year=year, doi=record.doi)
    return [f.tier for f in evaluate(cit, record)]


def test_print_year_crossref_never_recorded_is_not_a_year_error():
    rec = _record("10.1093_molbev_msl150.json")
    assert rec.years == (2006,)
    assert _tiers(rec, "Benton", 2007) == [Tier.COSMETIC]
    # The allowance is one year after an online-only date, nothing wider.
    assert _tiers(rec, "Benton", 2008) == [Tier.YEAR]
    assert _tiers(rec, "Benton", 2005) == [Tier.YEAR]
    assert _tiers(rec, "Benton", 2006) == []


def test_proceedings_named_for_the_cited_year_is_not_a_year_error():
    rec = _record("10.1142_9789814447362_0053.json")
    assert rec.journal == "Biocomputing 2001"
    assert _tiers(rec, "Bininda-Emonds", 2001) == [Tier.COSMETIC]
    assert _tiers(rec, "Bininda-Emonds", 2002) == [Tier.YEAR]


def test_a_complete_record_still_fails_a_year_that_is_one_off():
    rec = _record("10.1073_pnas.0904649106.json")
    assert rec.years == (2009,)
    assert _tiers(rec, "Phillips", 2010) == [Tier.YEAR]
    assert _tiers(rec, "Phillips", 2009) == []


def test_cached_record_keeps_every_year_and_the_date_evidence(tmp_path):
    cache = DoiCache(cache_dir=tmp_path)
    for name, author, year, want in (
        ("10.1142_9789814447362_0053.json", "Bininda-Emonds", 2013, []),
        ("10.1093_molbev_msl150.json", "Benton", 2007, [Tier.COSMETIC]),
    ):
        rec = _record(name)
        assert _tiers(rec, author, year) == want
        cache.put(rec.doi, rec)
        again = cache.get(rec.doi)
        assert again.years == rec.years
        assert _tiers(again, author, year) == want


def test_a_year_buried_inside_a_longer_number_does_not_name_the_container():
    msg = json.loads((DATA / "10.1142_9789814447362_0053.json").read_text())
    msg["container-title"] = ["Technical Report 120010"]
    assert _tiers(_record_from_message(msg), "Bininda-Emonds", 2001) == [Tier.YEAR]
    msg["container-title"] = ["Proceedings (2001)"]
    assert _tiers(_record_from_message(msg), "Bininda-Emonds", 2001) == [Tier.COSMETIC]
