from ghostcite.models import (
    CanonicalRecord,
    Citation,
    Finding,
    SemanticVerdict,
    SupportResult,
    Tier,
)


def test_support_tier_value():
    assert Tier.SUPPORT.value == "S"


def test_finding_defaults_deterministic_true():
    f = Finding(citation=Citation(raw="x"), tier=Tier.OK, canonical=None, message="ok")
    assert f.deterministic is True


def test_finding_can_be_marked_nondeterministic():
    f = Finding(
        citation=Citation(raw="x"),
        tier=Tier.SUPPORT,
        canonical=None,
        message="unsupported",
        deterministic=False,
    )
    assert f.deterministic is False


def test_canonical_record_has_abstract_field():
    r = CanonicalRecord(doi="10.1/x", abstract="An abstract.")
    assert r.abstract == "An abstract."
    assert CanonicalRecord(doi="10.1/x").abstract is None


def test_support_result_shape():
    sr = SupportResult(verdict=SemanticVerdict.UNSUPPORTED, rationale="no mention", backend="fake")
    assert sr.verdict is SemanticVerdict.UNSUPPORTED
    assert sr.rationale == "no mention"
    assert sr.backend == "fake"
