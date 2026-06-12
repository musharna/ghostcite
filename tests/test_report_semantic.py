import json

from ghostcite.models import Citation, Finding, Tier
from ghostcite.report import render_json, render_text


def _det():
    return Finding(
        citation=Citation(raw="x", source_line=1, claimed_first_author="Li", doi="10.1/a"),
        tier=Tier.AUTHOR,
        canonical=None,
        message="DOI resolves to Chen",
    )


def _sem():
    return Finding(
        citation=Citation(raw="claim", doi="10.1/b"),
        tier=Tier.SUPPORT,
        canonical=None,
        message="cited source does not support the claim — no mention",
        cross_check="semantic:fake",
        deterministic=False,
    )


def test_text_segregates_semantic_section():
    out = render_text([_det(), _sem()], total=2, with_doi=2, color=False)
    assert "semantic (non-deterministic)" in out.lower()
    assert out.index("Chen") < out.lower().index("semantic (non-deterministic)")
    assert "does not support" in out


def test_text_no_semantic_section_when_all_deterministic():
    out = render_text([_det()], total=1, with_doi=1, color=False)
    assert "semantic (non-deterministic)" not in out.lower()


def test_json_includes_deterministic_flag():
    out = render_json([_det(), _sem()], total=2, with_doi=2)
    payload = json.loads(out)
    flags = {f["tier"]: f["deterministic"] for f in payload["findings"]}
    assert flags["A"] is True
    assert flags["S"] is False
