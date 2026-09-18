"""A bibliographic-search hit is a guess at WHICH paper an entry cites.

Until 0.6.1 the top CrossRef hit was accepted unconditionally and the byline
was compared against it, so a wrong hit read as a wrong author. On the 26 real
references of a published Systematic Biology paper that produced six Tier A
findings, every one a different paper ("Gaut 1992" matched a philosophy book
review by Belliotti that mentions a Gaut).
"""

from __future__ import annotations

from ghostcite.api import _process_citation
from ghostcite.models import CanonicalRecord, Citation, Tier

GAUT = (
    "GAUT, B. S., S. V. MUSE, W. D. CLARK, and M. T. CLEGG. 1992. Relative rates of "
    "nucleotide substitution at the rbcL locus of monocotyledonous plants. J. Mol. Evol. 35:292-303."
)


class Search:
    """Stand-in client: returns one canned search hit and records the query."""

    def __init__(self, hit):
        self.hit = hit
        self.calls = []

    def search_bibliographic(self, author, year, title, *, reference=None):
        self.calls.append((author, year, title, reference))
        return self.hit

    def lookup_by_doi(self, doi, *, cache=None):  # pragma: no cover - DOI path unused
        raise AssertionError("no-DOI entry must not take the DOI path")


def entry(raw=GAUT, author="GAUT", year=1992, title=None):
    return Citation(raw=raw, claimed_first_author=author, claimed_year=year, claimed_title=title)


def hit(authors, year, title, doi="10.1/x"):
    return CanonicalRecord(
        doi=doi, authors=authors, year=year, years=(year,), title=title, low_confidence=True
    )


def tiers(findings):
    return [f.tier for f in findings]


def test_wrong_paper_hit_is_inconclusive_not_a_wrong_author():
    wrong = hit(["Belliotti", "Gaut"], 1992, "Book review")
    findings, rec = _process_citation(entry(), client=Search(wrong))
    assert tiers(findings) == [Tier.UNRESOLVABLE]
    assert rec is None
    assert 'closest: Belliotti 1992, "Book review"' in findings[0].message
    # Positive control: the same entry with the right paper as the hit is clean,
    # so the gate is not simply rejecting every search result.
    right = hit(
        ["Gaut", "Muse", "Clark", "Clegg"],
        1992,
        "Relative rates of nucleotide substitution at the rbcl locus of monocotyledonous plants",
    )
    findings, rec = _process_citation(entry(), client=Search(right))
    assert findings == []
    assert rec is right


def test_review_of_the_cited_book_is_not_the_book():
    # The review's title quotes the whole book citation, so title evidence alone
    # passes; the cited author appears nowhere in its byline.
    raw = "GELMAN, A., J. B. CARLIN, H. S. STERN, and D. B. RUBIN. 1995. Bayesian data analysis. Chapman and Hall, London."
    review = hit(
        ["Molenaar"],
        1997,
        "A. Gelman, J.B. Carlin, H.S. Stern, and D.B. Rubin, Bayesian Data Analysis",
    )
    findings, _ = _process_citation(entry(raw, "GELMAN", 1995), client=Search(review))
    assert tiers(findings) == [Tier.UNRESOLVABLE]


def test_misordered_first_author_is_still_tier_a():
    # Same paper (title matches, claimed author IS in the byline) cited under its
    # second author: the finding the tool exists for must survive the gate.
    raw = GAUT.replace("GAUT, B. S., S. V. MUSE", "MUSE, S. V., B. S. GAUT")
    right = hit(
        ["Gaut", "Muse", "Clark", "Clegg"],
        1992,
        "Relative rates of nucleotide substitution at the rbcl locus of monocotyledonous plants",
    )
    findings, _ = _process_citation(entry(raw, "MUSE"), client=Search(right))
    assert tiers(findings) == [Tier.AUTHOR]
    assert "author #2" in findings[0].message


def test_entry_without_a_parsed_title_searches_on_the_whole_reference():
    client = Search(None)
    _process_citation(entry(), client=client)
    assert client.calls == [("GAUT", 1992, None, GAUT)]


def test_wrong_hit_cannot_report_its_own_retraction():
    # The retraction lookup keys on the hit's DOI; a rejected hit must not lend it.
    class DB:
        source_label = "snapshot"

        def __init__(self):
            self.asked = []

        def lookup(self, doi):
            self.asked.append(doi)
            return (True, False) if doi == "10.1/retracted" else None

    db = DB()
    wrong = hit(["Belliotti"], 1992, "Book review", doi="10.1/retracted")
    findings, _ = _process_citation(entry(), client=Search(wrong), retraction_db=db)
    assert tiers(findings) == [Tier.UNRESOLVABLE]
    assert "10.1/retracted" not in db.asked


def test_bibtex_entry_with_a_title_uses_the_claimed_title():
    c = entry(
        "@article{x}",
        "Ngou",
        2021,
        "Mutual potentiation of plant immunity by cell-surface receptors",
    )
    wrong = hit(["Ngou"], 2021, "Plant immune networks")
    findings, _ = _process_citation(c, client=Search(wrong))
    assert tiers(findings) == [Tier.UNRESOLVABLE]
    right = hit(
        ["Ngou", "Ahn"],
        2021,
        "Mutual potentiation of plant immunity by cell-surface and intracellular receptors",
    )
    assert _process_citation(c, client=Search(right))[0] == []


def test_closest_match_is_shown_on_one_line_without_markup():
    wrong = hit(
        ["Charlesworth"], 1992, "Molecular Panselectionism:\n      <i>The Causes</i>  " + "x" * 120
    )
    findings, _ = _process_citation(entry(), client=Search(wrong))
    msg = findings[0].message
    assert "\n" not in msg and "<i>" not in msg
    assert 'closest: Charlesworth 1992, "Molecular Panselectionism: The Causes xxx' in msg
    assert msg.endswith('…")')


def test_author_order_verdict_needs_the_year_to_agree():
    # A 2002 book by Cribb matched a 2000 item by Hennessy & Cribb with the same
    # title words. Title and byline membership both pass; a hit that disagrees on
    # first author AND year is more likely another work than a miscited one.
    raw = "Cribb, P., & Butterfield, I. (2002). The Genus Paphiopedilum: Orchid Register and Checklist."
    other = hit(["Hennessy", "Cribb"], 2000, "The Genus Paphiopedilum")
    findings, _ = _process_citation(entry(raw, "Cribb", 2002), client=Search(other))
    assert tiers(findings) == [Tier.UNRESOLVABLE]
    # Control: same hit with the cited year is a confirmed author-order error.
    findings, _ = _process_citation(entry(raw, "Cribb", 2000), client=Search(other))
    assert tiers(findings) == [Tier.AUTHOR]
