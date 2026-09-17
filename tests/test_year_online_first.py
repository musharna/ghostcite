"""Online-first papers must not be flagged as year mismatches.

CrossRef carries several date fields. `published` is the EARLIEST of them, so for
any journal with online-first publication it holds the online date while the
paper is universally cited by its print-issue year. `_year()` returned the first
field it found, so the canonical year was the online one and a bibliography using
the print year was flagged Tier B.

Two real cases, both found auditing a manuscript on 2026-09-16:

  featureCounts -- 10.1093/bioinformatics/btt656
      published-online 2013-11-13, published-print 2014-04-01
      cited everywhere, correctly, as Liao et al. 2014

  Yang et al. -- 10.1093/molbev/msu343
      published-online 2014-12-21, published-print 2015-03-01
      cited, correctly, as Yang et al. 2015

Acting on either flag would have introduced a defect into a correct bibliography,
which is the opposite of what this tool is for. A false positive here is worse
than a miss: it costs the user's trust in every other flag in the report.
"""

from ghostcite.compare import evaluate
from ghostcite.crossref import _record_from_message
from ghostcite.models import Citation

FEATURECOUNTS = {
    "DOI": "10.1093/bioinformatics/btt656",
    "title": ["featureCounts: an efficient general purpose program"],
    "container-title": ["Bioinformatics"],
    "author": [{"family": "Liao"}, {"family": "Smyth"}, {"family": "Shi"}],
    "published": {"date-parts": [[2013, 11, 13]]},
    "published-online": {"date-parts": [[2013, 11, 13]]},
    "published-print": {"date-parts": [[2014, 4, 1]]},
    "issued": {"date-parts": [[2013, 11, 13]]},
}


def _cit(year: int) -> Citation:
    return Citation(
        raw=f"Liao et al. ({year})",
        claimed_first_author="Liao",
        claimed_year=year,
        doi="10.1093/bioinformatics/btt656",
    )


def test_record_keeps_every_candidate_year():
    rec = _record_from_message(FEATURECOUNTS)
    assert 2013 in rec.years
    assert 2014 in rec.years, "the print year must be retained, not just the earliest date"


def test_print_year_is_not_a_mismatch():
    # THE BUG. The bib says 2014 (print, and the canonical citation); CrossRef's
    # `published` says 2013 (online). This must not be a finding.
    rec = _record_from_message(FEATURECOUNTS)
    assert evaluate(_cit(2014), rec) == []


def test_online_year_is_also_accepted():
    # Someone citing the online year is not wrong either — both are real
    # publication dates for the same article.
    rec = _record_from_message(FEATURECOUNTS)
    assert evaluate(_cit(2013), rec) == []


def test_a_genuinely_wrong_year_is_still_flagged():
    # The positive control. Widening the accepted set must not blind the check:
    # a year matching NEITHER date is still a Tier B finding.
    rec = _record_from_message(FEATURECOUNTS)
    findings = evaluate(_cit(2019), rec)
    assert len(findings) == 1
    assert findings[0].tier.value == "B"


def test_single_date_record_is_unaffected():
    # A record with only one date behaves exactly as before: match passes,
    # mismatch flags.
    msg = {
        "DOI": "10.1/x",
        "title": ["t"],
        "author": [{"family": "Chen"}],
        "issued": {"date-parts": [[2019, 1, 1]]},
    }
    rec = _record_from_message(msg)
    assert rec.year == 2019
    assert rec.years == (2019,)
    ok = Citation(raw="Chen (2019)", claimed_first_author="Chen", claimed_year=2019, doi="10.1/x")
    bad = Citation(raw="Chen (2024)", claimed_first_author="Chen", claimed_year=2024, doi="10.1/x")
    assert evaluate(ok, rec) == []
    assert [f.tier.value for f in evaluate(bad, rec)] == ["B"]
