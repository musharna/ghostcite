from ghostcite.compare import evaluate, venue_mismatch
from ghostcite.models import CanonicalRecord, Citation, Tier


def test_abbreviation_pairs_do_not_fire():
    # Same venue, abbreviated vs full — must NOT be a mismatch.
    assert venue_mismatch("J. Mol. Biol.", "Journal of Molecular Biology") is False
    assert venue_mismatch("PNAS", "Proceedings of the National Academy of Sciences") is False
    assert venue_mismatch("Nature", "Nature") is False


def test_real_disagreement_fires():
    assert venue_mismatch("Nature", "Cell") is True


def test_missing_or_short_returns_false():
    assert venue_mismatch(None, "Cell") is False
    assert venue_mismatch("Nature", None) is False
    assert venue_mismatch("", "") is False


def test_standard_abbreviations_do_not_fire():
    """Standard dotted abbreviations of multi-word journal names must not produce false positives.

    These are the cases where _prefix_covered previously failed because content words like
    'Review' / 'Proceedings' are in _VENUE_STOP and get stripped from the canonical token list,
    leaving abbreviation tokens (rev, proc) with nothing to prefix-match against.
    The _is_abbrev_of helper fixes this by operating on loose tokens (connector-stop only).
    """
    # 'Rev' abbreviates 'Review' — previously a false positive
    assert venue_mismatch("Phys. Rev. Lett.", "Physical Review Letters") is False
    # 'Proc' abbreviates 'Proceedings' — previously a false positive
    assert (
        venue_mismatch(
            "Proc. Natl. Acad. Sci. U.S.A.", "Proceedings of the National Academy of Sciences"
        )
        is False
    )
    # Existing cases that must continue passing
    assert venue_mismatch("J. Mol. Biol.", "Journal of Molecular Biology") is False
    assert venue_mismatch("PNAS", "Proceedings of the National Academy of Sciences") is False
    assert venue_mismatch("N Engl J Med", "The New England Journal of Medicine") is False
    assert venue_mismatch("Nat. Commun.", "Nature Communications") is False
    assert venue_mismatch("J. Am. Chem. Soc.", "Journal of the American Chemical Society") is False
    assert venue_mismatch(None, "Cell") is False
    assert venue_mismatch("Nature", None) is False
    assert venue_mismatch("", "") is False


def test_distinct_journals_fire():
    """Genuinely different journals must still trigger a mismatch."""
    assert venue_mismatch("Nature", "Cell") is True


def _rec(
    *,
    doi: str = "10.1/x",
    authors: list[str] | None = None,
    year: int = 2020,
    title: str = "A study of widgets and gadgets",
    journal: str = "Cell",
) -> CanonicalRecord:
    return CanonicalRecord(
        doi=doi,
        authors=authors if authors is not None else ["Smith"],
        year=year,
        title=title,
        journal=journal,
    )


def test_evaluate_emits_venue_when_journal_disagrees():
    c = Citation(
        raw="x",
        doi="10.1/x",
        claimed_first_author="Smith",
        claimed_year=2020,
        claimed_title="A study of widgets and gadgets",
        claimed_journal="Nature",
    )
    findings = evaluate(c, _rec())
    assert [f.tier for f in findings] == [Tier.VENUE]


def test_evaluate_suppresses_venue_when_author_already_flagged():
    c = Citation(
        raw="x",
        doi="10.1/x",
        claimed_first_author="Jones",
        claimed_year=2020,
        claimed_title="A study of widgets and gadgets",
        claimed_journal="Nature",
    )
    findings = evaluate(c, _rec())
    assert Tier.AUTHOR in [f.tier for f in findings]
    assert Tier.VENUE not in [f.tier for f in findings]


def test_evaluate_suppresses_venue_when_title_already_flagged():
    # Author matches (no AUTHOR finding) but the title clearly disagrees -> TITLE fires,
    # which must suppress the venue finding even though the journal also disagrees.
    c = Citation(
        raw="x",
        doi="10.1/x",
        claimed_first_author="Smith",
        claimed_year=2020,
        claimed_title="Completely unrelated quantum chromodynamics measurements",
        claimed_journal="Nature",
    )
    findings = evaluate(c, _rec())
    assert Tier.TITLE in [f.tier for f in findings]
    assert Tier.VENUE not in [f.tier for f in findings]
