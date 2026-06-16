import json

from ghostcite.models import CanonicalRecord, Citation, Finding, Tier
from ghostcite.report import render_badge

_C = Citation(raw="x", doi="10.1/x")
_AUTHOR = Finding(_C, Tier.AUTHOR, None, "wrong author")
_VENUE = Finding(_C, Tier.VENUE, None, "venue differs")

_FAIL = {Tier.AUTHOR, Tier.TITLE, Tier.YEAR, Tier.RETRACTION}


def test_badge_clean():
    d = json.loads(render_badge([], _FAIL))
    assert d == {
        "schemaVersion": 1,
        "label": "ghostcite",
        "message": "clean",
        "color": "brightgreen",
    }


def test_badge_red_on_failing_tier():
    d = json.loads(render_badge([_AUTHOR], _FAIL))
    assert d["color"] == "red"
    assert d["message"] == "1 issue"


def test_badge_warn_only_stays_green():
    # A VENUE finding is not in the fail set → badge stays green (matches exit 0).
    d = json.loads(render_badge([_VENUE], _FAIL))
    assert d["color"] == "brightgreen"
    assert d["message"] == "clean"


def test_cli_writes_badge(monkeypatch, tmp_path):
    from ghostcite import cli

    monkeypatch.setattr(
        "ghostcite.crossref.CrossRefClient.lookup_by_doi",
        lambda self, doi, *, cache=None: CanonicalRecord(
            doi="10.1/x", authors=["Smith"], year=2020, title="T"
        ),
    )
    bib = tmp_path / "r.bib"
    bib.write_text("@article{k, author={Smith, A}, year={2020}, title={T}, doi={10.1/x}}\n")
    badge = tmp_path / "b.json"
    rc = cli.main([str(bib), "--badge", str(badge)])
    assert rc == 0
    d = json.loads(badge.read_text())
    assert d["color"] == "brightgreen" and d["label"] == "ghostcite"
