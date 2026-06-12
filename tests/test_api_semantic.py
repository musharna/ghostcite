import ghostcite
from ghostcite.models import SemanticVerdict, SupportResult, Tier


class FakeBackend:
    name = "fake"

    def assess_support(self, claim, source_text):
        return SupportResult(verdict=SemanticVerdict.UNSUPPORTED, rationale="r", backend="fake")


class FakeProvider:
    def get_abstract(self, doi):
        return "some abstract"


def test_check_claim_support_exported_from_package():
    assert hasattr(ghostcite, "check_claim_support")
    assert "check_claim_support" in ghostcite.__all__


def test_check_claim_support_via_api():
    from ghostcite.api import check_claim_support

    f = check_claim_support(
        "claim", "10.1/x", backend=FakeBackend(), source_provider=FakeProvider()
    )
    assert f is not None and f.tier is Tier.SUPPORT and f.deterministic is False


def test_support_tier_in_priority_table():
    from ghostcite.api import _TIER_PRIORITY

    assert Tier.SUPPORT in _TIER_PRIORITY
