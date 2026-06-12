import json
import sys

import ghostcite
from ghostcite import cli
from ghostcite.models import SemanticVerdict, SupportResult


class FakeBackend:
    name = "fake"

    def __init__(self, *a, **k):
        pass

    def assess_support(self, claim, source_text):
        return SupportResult(
            verdict=SemanticVerdict.UNSUPPORTED, rationale="no mention", backend="fake"
        )


def _patch_semantic(monkeypatch):
    import ghostcite.semantic.backends as backends_mod
    import ghostcite.semantic.support as support_mod

    monkeypatch.setattr(backends_mod, "build_backend", lambda *a, **k: FakeBackend())

    class FakeProvider:
        def __init__(self, *a, **k):
            pass

        def get_abstract(self, doi):
            return "an abstract"

    monkeypatch.setattr(support_mod, "AbstractProvider", FakeProvider)


def _claims_file(tmp_path):
    p = tmp_path / "claims.json"
    p.write_text(json.dumps([{"claim": "X cures Y", "doi": "10.1/x"}]), "utf-8")
    return str(p)


def test_claims_manifest_reports_unsupported(tmp_path, capsys, monkeypatch):
    _patch_semantic(monkeypatch)
    code = cli.main(
        [
            "--claims",
            _claims_file(tmp_path),
            "--semantic-backend",
            "openai",
            "--semantic-base-url",
            "http://x/v1",
            "--semantic-model",
            "m",
        ]
    )
    out = capsys.readouterr().out
    assert "does not support" in out
    assert code == 0  # support excluded from default --fail-on


def test_claims_manifest_fail_on_support(tmp_path, capsys, monkeypatch):
    _patch_semantic(monkeypatch)
    code = cli.main(
        [
            "--claims",
            _claims_file(tmp_path),
            "--semantic-backend",
            "openai",
            "--semantic-base-url",
            "http://x/v1",
            "--semantic-model",
            "m",
            "--fail-on",
            "support",
        ]
    )
    assert code == 1


def test_claims_requires_backend_config(tmp_path, capsys):
    # no api key for anthropic -> real build_backend raises -> exit 2
    code = cli.main(["--claims", _claims_file(tmp_path), "--semantic-backend", "anthropic"])
    assert code == 2
    assert "api key" in capsys.readouterr().err.lower()


def test_semantic_on_bib_warns_and_runs_core(tmp_path, capsys, monkeypatch):
    from tests.test_cli import FakeClient  # reuse the existing fake

    monkeypatch.setattr(cli, "CrossRefClient", FakeClient)
    f = tmp_path / "r.bib"
    f.write_text("@article{k, author={Chen, M}, year={2024}, doi={10.3390/plants13060869}}")
    code = cli.main(
        [
            str(f),
            "--semantic",
            "--semantic-backend",
            "openai",
            "--semantic-base-url",
            "http://x/v1",
            "--semantic-model",
            "m",
        ]
    )
    err = capsys.readouterr().err
    assert "no claims" in err.lower()
    assert code == 0


def test_importing_ghostcite_does_not_import_semantic():
    import importlib

    for mod in list(sys.modules):
        if mod.startswith("ghostcite.semantic"):
            del sys.modules[mod]
    importlib.reload(ghostcite)
    assert not any(m.startswith("ghostcite.semantic") for m in sys.modules)
