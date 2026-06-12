from ghostcite.models import (
    CanonicalRecord,
    SemanticVerdict,
    SupportResult,
    Tier,
)
from ghostcite.semantic.support import check_claim_support


class FakeBackend:
    name = "fake"

    def __init__(self, verdict):
        self._verdict = verdict
        self.calls = []

    def assess_support(self, claim, source_text):
        self.calls.append((claim, source_text))
        return SupportResult(verdict=self._verdict, rationale="because", backend=self.name)


class FakeProvider:
    def __init__(self, abstract):
        self._abstract = abstract

    def get_abstract(self, doi):
        return self._abstract


def test_unsupported_yields_support_finding():
    b = FakeBackend(SemanticVerdict.UNSUPPORTED)
    f = check_claim_support(
        "X cures Y.", "10.1/x", backend=b, source_provider=FakeProvider("abstract text")
    )
    assert f is not None
    assert f.tier is Tier.SUPPORT
    assert f.deterministic is False
    assert f.cross_check == "semantic:fake"
    assert "because" in f.message
    assert b.calls == [("X cures Y.", "abstract text")]


def test_supported_yields_none():
    b = FakeBackend(SemanticVerdict.SUPPORTED)
    assert check_claim_support("c", "10.1/x", backend=b, source_provider=FakeProvider("a")) is None


def test_uncertain_yields_none():
    b = FakeBackend(SemanticVerdict.UNCERTAIN)
    assert check_claim_support("c", "10.1/x", backend=b, source_provider=FakeProvider("a")) is None


def test_missing_abstract_yields_none_and_skips_backend():
    b = FakeBackend(SemanticVerdict.UNSUPPORTED)
    f = check_claim_support("c", "10.1/x", backend=b, source_provider=FakeProvider(None))
    assert f is None
    assert b.calls == []  # never called the backend


def test_default_provider_uses_crossref(monkeypatch):
    from ghostcite.semantic import support as support_mod

    class FakeClient:
        def lookup_by_doi(self, doi, *, cache=None):
            return CanonicalRecord(doi=doi, abstract="from crossref")

    prov = support_mod.AbstractProvider(client=FakeClient())
    assert prov.get_abstract("10.1/x") == "from crossref"
