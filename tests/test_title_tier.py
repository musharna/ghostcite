"""Tier T (title / identifier-hijacking): the cited DOI resolves to a different paper."""

from ghostcite.compare import evaluate, title_mismatch
from ghostcite.models import CanonicalRecord, Citation, Tier

# --- title_mismatch helper (conservative, high-precision) --------------------


def test_title_mismatch_flags_clearly_different():
    assert (
        title_mismatch(
            "Deep learning for protein folding prediction",
            "A study of medieval French poetry economics",
        )
        is True
    )


def test_title_mismatch_tolerates_subtitle_variance():
    assert (
        title_mismatch(
            "Integrated transcriptome analysis",
            "Integrated transcriptome analysis of plant stress: a comprehensive review",
        )
        is False
    )


def test_title_mismatch_too_few_tokens_no_flag():
    # Titles with < 3 content tokens can't be judged confidently — never flag.
    assert title_mismatch("Nature", "Science magazine") is False


def test_title_mismatch_none_inputs():
    assert title_mismatch(None, "x") is False
    assert title_mismatch("x", None) is False


# --- evaluate() wiring -------------------------------------------------------


def test_title_finding_when_author_matches_but_paper_differs():
    # Identifier hijacking: author surname matches the DOI's first author, but the
    # DOI resolves to a completely different paper. Previously MISSED (no title check
    # in the author-matches branch).
    cit = Citation(
        raw="r",
        doi="10.1/x",
        claimed_first_author="Chen",
        claimed_title="Quantum effects in photosynthesis",
    )
    can = CanonicalRecord(
        doi="10.1/x",
        authors=["Chen"],
        year=2020,
        title="A history of Roman aqueduct engineering",
    )
    tiers = [f.tier for f in evaluate(cit, can)]
    assert Tier.TITLE in tiers
    assert Tier.AUTHOR not in tiers  # author matched, so only TITLE fires


def test_no_title_finding_when_titles_match():
    cit = Citation(
        raw="r",
        doi="10.1/x",
        claimed_first_author="Chen",
        claimed_title="Integrated transcriptome and proteome analysis",
    )
    can = CanonicalRecord(
        doi="10.1/x",
        authors=["Chen"],
        year=2024,
        title="Integrated transcriptome and proteome analysis",
    )
    assert all(f.tier is not Tier.TITLE for f in evaluate(cit, can))


def test_no_double_report_when_author_already_mismatched():
    # Author wrong AND title wrong: the AUTHOR finding carries it; TITLE is suppressed.
    cit = Citation(
        raw="r",
        doi="10.1/x",
        claimed_first_author="Smith",
        claimed_title="Quantum effects in photosynthesis",
    )
    can = CanonicalRecord(
        doi="10.1/x",
        authors=["Chen"],
        year=2020,
        title="A history of Roman aqueduct engineering",
    )
    tiers = [f.tier for f in evaluate(cit, can)]
    assert Tier.AUTHOR in tiers
    assert Tier.TITLE not in tiers


def test_title_finding_in_doi_mode_with_title():
    # No claimed author, but a title is present and clearly mismatched.
    cit = Citation(raw="r", doi="10.1/x", claimed_title="Quantum effects in photosynthesis")
    can = CanonicalRecord(
        doi="10.1/x",
        authors=["Chen"],
        year=2020,
        title="A history of Roman aqueduct engineering",
    )
    assert any(f.tier is Tier.TITLE for f in evaluate(cit, can))


# --- tier plumbing -----------------------------------------------------------


def test_tier_title_value():
    assert Tier.TITLE.value == "T"


def test_api_title_in_ghost_and_priority():
    from ghostcite.api import _GHOST_TIERS, _TIER_PRIORITY

    assert Tier.TITLE in _GHOST_TIERS
    assert Tier.TITLE in _TIER_PRIORITY


def test_report_has_title_glyph():
    from ghostcite.report import _GLYPH

    assert Tier.TITLE in _GLYPH


def test_cli_default_fail_on_includes_title():
    from ghostcite import cli

    assert "title" in cli._TIER_BY_NAME
    assert "title" in cli._parse_args(["x.bib"]).fail_on
