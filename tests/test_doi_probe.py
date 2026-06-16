# METRIC_REFERENCE_OK — TDD: tests introduced before implementation (Task 3 dead-DOI probe)
from ghostcite.compare import evaluate
from ghostcite.models import Citation, Tier


def test_evaluate_unresolved_reason_is_used():
    c = Citation(raw="x", doi="10.1/x", claimed_first_author="Smith")
    findings = evaluate(c, None, unresolved_reason="DOI does not resolve (dead or fabricated DOI)")
    u = [f for f in findings if f.tier is Tier.UNRESOLVABLE]
    assert u and "dead or fabricated" in u[0].message


def test_evaluate_default_unresolved_message_unchanged():
    c = Citation(raw="x", doi="10.1/x", claimed_first_author="Smith")
    findings = evaluate(c, None)
    u = [f for f in findings if f.tier is Tier.UNRESOLVABLE]
    assert u and u[0].message == "DOI not found / unresolvable"


import httpx  # noqa: E402

from ghostcite.crossref import CrossRefClient  # noqa: E402


def _client_with_head(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    c = CrossRefClient()
    c._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return c


def test_doi_resolves_true_on_200():
    assert _client_with_head(200).doi_resolves("10.1/x") is True


def test_doi_resolves_false_on_404():
    assert _client_with_head(404).doi_resolves("10.1/x") is False


def test_doi_resolves_none_on_error():
    def boom(request):
        raise httpx.ConnectError("down")

    c = CrossRefClient()
    c._client = httpx.Client(transport=httpx.MockTransport(boom))
    assert c.doi_resolves("10.1/x") is None


def test_no_doi_probe_skips_head(monkeypatch, tmp_path):
    from ghostcite import cli

    calls = {"n": 0}
    monkeypatch.setattr(
        "ghostcite.crossref.CrossRefClient.lookup_by_doi",
        lambda self, doi, *, cache=None: None,
    )

    def spy(self, doi):
        calls["n"] += 1
        return False

    monkeypatch.setattr("ghostcite.crossref.CrossRefClient.doi_resolves", spy)
    bib = tmp_path / "r.bib"
    bib.write_text("@article{k, author={Smith, A}, year={2020}, title={T}, doi={10.1/x}}\n")
    cli.main([str(bib), "--no-doi-probe"])
    assert calls["n"] == 0
    cli.main([str(bib)])
    assert calls["n"] == 1
