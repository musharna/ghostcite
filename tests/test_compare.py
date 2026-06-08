from ghostcite.compare import normalize_surname, title_similar, evaluate
from ghostcite.models import Citation, CanonicalRecord, Tier


def test_fold_diacritics():
    assert normalize_surname("Bürger") == normalize_surname("Burger") == "burger"


def test_strip_case_and_punct():
    assert normalize_surname("O'Brien") == "obrien"
    assert normalize_surname("  van der Berg ") == "vanderberg"


def test_empty_and_none():
    assert normalize_surname("") == ""
    assert normalize_surname(None) == ""


def test_title_similar_true_for_same_title():
    assert (
        title_similar(
            "Integrated Transcriptome and Proteome Analysis",
            "Integrated transcriptome and proteome analysis reveals...",
        )
        is True
    )


def test_title_similar_false_for_different_papers():
    assert (
        title_similar(
            "Auxin response factors in lateral roots",
            "A genome resource for Neocamarosporium betae",
        )
        is False
    )


def test_title_similar_handles_missing():
    assert title_similar(None, "x") is False
    assert title_similar("x", None) is False


def _cit(**kw):
    base = dict(
        raw="r",
        doi="10.1/a",
        claimed_first_author="Li",
        claimed_year=2024,
        claimed_title="Cell Wall Activity in Phelipanche",
    )
    base.update(kw)
    return Citation(**base)


def _rec(**kw):
    base = dict(
        doi="10.1/a",
        authors=["Chen", "Zhang"],
        year=2024,
        title="Cell Wall Activity Affects Phelipanche",
        journal="Plants",
    )
    base.update(kw)
    return CanonicalRecord(**base)


def test_ok_when_first_author_and_year_match():
    c = _cit(claimed_first_author="Chen")
    assert evaluate(c, _rec()) == []  # no findings


def test_author_mismatch_is_tier_a():
    findings = evaluate(_cit(claimed_first_author="Li"), _rec())
    assert [f.tier for f in findings] == [Tier.AUTHOR]
    assert "Chen" in findings[0].message


def test_trailing_initials_do_not_false_positive():
    # "Smith J", "J Smith", "Smith JA" all carry trailing/leading single-letter
    # initials and must compare equal to the canonical family name "Smith".
    rec = _rec(authors=["Smith", "Zhang"])
    for claimed in ("Smith J", "J Smith", "Smith JA"):
        c = _cit(claimed_first_author=claimed)
        assert evaluate(c, rec) == [], f"{claimed!r} should be OK"


def test_initials_stripping_does_not_mask_real_mismatch():
    # Stripping initials must NOT turn a genuine author mismatch into OK.
    c = _cit(claimed_first_author="Li J")
    findings = evaluate(c, _rec(authors=["Chen", "Zhang"]))
    assert [f.tier for f in findings] == [Tier.AUTHOR]


def test_wrong_doi_annotation_when_title_diverges():
    c = _cit(
        claimed_first_author="Clarke", claimed_title="Arabidopsis immunity to broomrape"
    )
    rec = _rec(
        authors=["Vaghefi"], title="A genome resource for Neocamarosporium betae"
    )
    findings = evaluate(c, rec)
    assert findings[0].tier is Tier.AUTHOR
    assert "possibly wrong DOI" in findings[0].message


def test_year_mismatch_is_tier_b_when_author_ok():
    c = _cit(claimed_first_author="Chen", claimed_year=2019)
    findings = evaluate(c, _rec(year=2024))
    assert [f.tier for f in findings] == [Tier.YEAR]
    assert "2024" in findings[0].message


def test_diacritic_only_is_tier_c():
    c = _cit(claimed_first_author="Burger", claimed_year=2025, claimed_title="x")
    rec = _rec(authors=["Bürger"], year=2025, title="x")
    findings = evaluate(c, rec)
    assert [f.tier for f in findings] == [Tier.COSMETIC]


def test_retraction_is_tier_r():
    c = _cit(claimed_first_author="Chen")
    findings = evaluate(c, _rec(retracted=True))
    assert Tier.RETRACTION in [f.tier for f in findings]


def test_unresolvable_when_no_canonical():
    findings = evaluate(_cit(), None)
    assert [f.tier for f in findings] == [Tier.UNRESOLVABLE]


def test_no_claimed_author_skips_author_check():
    # DOI-list mode: nothing claimed → only retraction/unresolvable can fire
    c = Citation(raw="r", doi="10.1/a")
    assert evaluate(c, _rec()) == []
