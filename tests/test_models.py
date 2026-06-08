from ghostcite.models import Tier, Citation, CanonicalRecord, Finding


def test_tier_values():
    assert Tier.AUTHOR.value == "A"
    assert Tier.YEAR.value == "B"
    assert Tier.COSMETIC.value == "C"
    assert Tier.RETRACTION.value == "R"
    assert Tier.UNRESOLVABLE.value == "U"
    assert Tier.OK.value == "OK"


def test_citation_defaults():
    c = Citation(raw="x")
    assert c.doi is None and c.claimed_first_author is None and c.source_line is None


def test_finding_holds_records():
    c = Citation(raw="x", doi="10.1/a", claimed_first_author="Li", claimed_year=2024)
    rec = CanonicalRecord(
        doi="10.1/a", authors=["Chen"], year=2024, title="T", journal="J"
    )
    f = Finding(citation=c, tier=Tier.AUTHOR, canonical=rec, message="msg")
    assert f.tier is Tier.AUTHOR and f.canonical.authors == ["Chen"]
