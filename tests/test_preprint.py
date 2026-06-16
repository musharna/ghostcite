from ghostcite.crossref import _record_from_message


def test_subtype_preprint_sets_is_preprint():
    rec = _record_from_message(
        {"DOI": "10.1/x", "subtype": "preprint", "author": [{"family": "Smith"}], "title": ["T"]}
    )
    assert rec.is_preprint is True
    assert rec.has_preprint_relation is False


def test_relation_has_preprint_sets_flag():
    rec = _record_from_message(
        {
            "DOI": "10.1/x",
            "relation": {"has-preprint": [{"id": "10.1/pre"}]},
            "author": [{"family": "Smith"}],
            "title": ["T"],
        }
    )
    assert rec.has_preprint_relation is True


def test_plain_record_has_no_preprint_flags():
    rec = _record_from_message({"DOI": "10.1/x", "author": [{"family": "Smith"}], "title": ["T"]})
    assert rec.is_preprint is False
    assert rec.has_preprint_relation is False


# ---------------------------------------------------------------------------
# evaluate() — year-drift downgrade tests
# ---------------------------------------------------------------------------

from ghostcite.compare import evaluate  # noqa: E402
from ghostcite.models import CanonicalRecord, Citation, Tier  # noqa: E402


def _rec(
    *,
    doi: str = "10.1/x",
    authors: list[str] | None = None,
    year: int = 2021,
    title: str = "T",
    journal: str | None = None,
    is_preprint: bool = False,
    has_preprint_relation: bool = False,
) -> CanonicalRecord:
    return CanonicalRecord(
        doi=doi,
        authors=authors if authors is not None else ["Smith"],
        year=year,
        title=title,
        journal=journal,
        is_preprint=is_preprint,
        has_preprint_relation=has_preprint_relation,
    )


def test_year_drift_downgraded_when_preprint():
    c = Citation(raw="x", doi="10.1/x", claimed_first_author="Smith", claimed_year=2022)
    findings = evaluate(c, _rec(is_preprint=True))
    tiers = [f.tier for f in findings]
    assert Tier.YEAR not in tiers
    assert Tier.COSMETIC in tiers  # downgraded, non-failing


def test_year_drift_still_fails_when_not_preprint():
    c = Citation(raw="x", doi="10.1/x", claimed_first_author="Smith", claimed_year=2022)
    findings = evaluate(c, _rec())
    assert Tier.YEAR in [f.tier for f in findings]


def test_wrong_author_still_fails_on_preprint():
    c = Citation(raw="x", doi="10.1/x", claimed_first_author="Jones", claimed_year=2021)
    findings = evaluate(c, _rec(is_preprint=True))
    assert Tier.AUTHOR in [f.tier for f in findings]
