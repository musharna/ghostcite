import io
import subprocess
import sys

import pytest

from ghostcite import cli
from ghostcite.models import CanonicalRecord


class FakeClient:
    """Stand-in for CrossRefClient: maps DOI → CanonicalRecord."""

    table = {
        "10.3390/plants13060869": CanonicalRecord(
            doi="10.3390/plants13060869",
            authors=["Chen"],
            year=2024,
            title="Integrated Transcriptome and Proteome Analysis",
        ),
    }

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def lookup_by_doi(self, doi, *, cache=None):
        return self.table.get(doi)

    def search_bibliographic(self, *a):
        return None


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(cli, "CrossRefClient", FakeClient)


def _write(tmp_path, text):
    p = tmp_path / "refs.bib"
    p.write_text(text)
    return str(p)


def test_exit_1_on_author_mismatch(tmp_path, capsys):
    f = _write(
        tmp_path,
        "@article{k, author={Li, X}, year={2024}, "
        "title={Integrated Transcriptome and Proteome Analysis}, "
        "doi={10.3390/plants13060869}}",
    )
    code = cli.main([f])
    assert code == 1
    assert "Chen" in capsys.readouterr().out


def test_exit_0_when_author_matches(tmp_path, capsys):
    f = _write(
        tmp_path,
        "@article{k, author={Chen, M}, year={2024}, "
        "title={Integrated Transcriptome and Proteome Analysis}, "
        "doi={10.3390/plants13060869}}",
    )
    assert cli.main([f]) == 0


def test_dry_run_makes_no_lookups(tmp_path, capsys):
    f = _write(
        tmp_path,
        "@article{k, author={Li, X}, year={2024}, doi={10.3390/plants13060869}}",
    )
    assert cli.main([f, "--dry-run"]) == 0
    assert "would check" in capsys.readouterr().out.lower()


def test_json_output(tmp_path, capsys):
    f = _write(
        tmp_path,
        "@article{k, author={Li, X}, year={2024}, "
        "title={Integrated Transcriptome and Proteome Analysis}, "
        "doi={10.3390/plants13060869}}",
    )
    cli.main([f, "--json"])
    assert '"tier": "A"' in capsys.readouterr().out


def test_fail_on_none_forces_exit_0(tmp_path):
    f = _write(
        tmp_path,
        "@article{k, author={Li, X}, year={2024}, "
        "title={Integrated Transcriptome and Proteome Analysis}, "
        "doi={10.3390/plants13060869}}",
    )
    assert cli.main([f, "--fail-on", "none"]) == 0


def test_version_flag_prints_and_exits_0(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "ghostcite 0.3.0"


def test_max_rps_nonpositive_exits_2(tmp_path):
    f = _write(tmp_path, "@article{k, author={Chen, M}, year={2024}, doi={10.1/x}}")
    with pytest.raises(SystemExit) as exc:
        cli.main([f, "--max-rps", "0"])
    assert exc.value.code == 2


def test_stdin_dash_reads_bibtex(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO("@article{k, author={Doe, J}, year={2020}, doi={10.1234/y}}"),
    )
    assert cli.main(["-", "--dry-run"]) == 0
    assert "would check 1 entries" in capsys.readouterr().out


def test_stdin_empty_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("   \n  "))
    assert cli.main(["-"]) == 2
    assert "no input on stdin" in capsys.readouterr().err


def test_stdin_doi_format_honored(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("10.3390/plants13060869\n"))
    assert cli.main(["-", "--format", "doi", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would check 1 entries" in out
    assert "1 via DOI" in out


def test_python_m_entrypoint():
    """Real-execution boundary: `python -m ghostcite --version` works via __main__."""
    result = subprocess.run(
        [sys.executable, "-m", "ghostcite", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ghostcite 0.3.0" in result.stdout


def _retracted_fake(monkeypatch):
    class RetractFake(FakeClient):
        table = {
            "10.1/ret": CanonicalRecord(
                doi="10.1/ret",
                authors=["Doe"],
                year=2000,
                title="t",
                retracted=False,  # CrossRef itself does NOT flag it...
            ),
        }

    monkeypatch.setattr(cli, "CrossRefClient", RetractFake)


def _db_csv(tmp_path):
    p = tmp_path / "rw.csv"
    p.write_text("OriginalPaperDOI,RetractionNature\n10.1/ret,Retraction\n", "utf-8")
    return str(p)


def test_retraction_db_flags_when_crossref_did_not(tmp_path, capsys, monkeypatch):
    _retracted_fake(monkeypatch)
    db = _db_csv(tmp_path)
    f = _write(tmp_path, "@article{k, author={Doe, J}, year={2000}, title={t}, doi={10.1/ret}}")
    code = cli.main([f, "--retraction-db", db])
    out = capsys.readouterr().out
    assert code == 1  # retraction is in default --fail-on
    assert "Retraction Watch snapshot" in out  # source label in finding + header


def test_retraction_db_none_disables(tmp_path, capsys, monkeypatch):
    _retracted_fake(monkeypatch)
    f = _write(tmp_path, "@article{k, author={Doe, J}, year={2000}, title={t}, doi={10.1/ret}}")
    code = cli.main([f, "--retraction-db", "none"])
    out = capsys.readouterr().out
    assert "retractions: CrossRef live" in out
    assert code == 0  # CrossRef fake did not flag it, db disabled


def test_retraction_db_missing_path_exit_2(tmp_path, capsys, monkeypatch):
    _retracted_fake(monkeypatch)
    f = _write(tmp_path, "@article{k, author={Doe, J}, year={2000}, title={t}, doi={10.1/ret}}")
    code = cli.main([f, "--retraction-db", str(tmp_path / "nope.csv")])
    assert code == 2
    assert "retraction" in capsys.readouterr().err.lower()


def test_fetch_retractions_requires_mailto(capsys, monkeypatch):
    monkeypatch.delenv("GHOSTCITE_MAILTO", raising=False)
    code = cli.main(["fetch-retractions"])
    assert code == 2
    assert "mailto" in capsys.readouterr().err.lower()


def test_fetch_retractions_success(tmp_path, capsys, monkeypatch):
    dest = tmp_path / "rw.csv"
    calls = {}

    def fake_fetch(mailto, d, **kw):
        calls["mailto"] = mailto
        return {"row_count": 5, "fetched_at": "2026-06-11T00:00:00+00:00"}

    monkeypatch.setattr(cli, "fetch_retractions", fake_fetch)
    code = cli.main(["fetch-retractions", "--mailto", "me@x.org", "--dest", str(dest)])
    assert code == 0
    assert calls["mailto"] == "me@x.org"
    out = capsys.readouterr().out
    assert "Retraction Watch" in out  # attribution printed
    assert "5" in out


def test_retraction_db_flags_even_when_crossref_404s(tmp_path, capsys, monkeypatch):
    """DB retraction must fire even when CrossRef returns None (404/unreachable)."""

    class NotFoundFake(FakeClient):
        def lookup_by_doi(self, doi, *, cache=None):
            return None

    monkeypatch.setattr(cli, "CrossRefClient", NotFoundFake)
    db = tmp_path / "rw.csv"
    db.write_text("OriginalPaperDOI,RetractionNature\n10.9999/x,Retraction\n", "utf-8")
    f = _write(tmp_path, "@article{k, author={Doe, J}, year={2020}, title={t}, doi={10.9999/x}}")
    code = cli.main([f, "--retraction-db", str(db)])
    out = capsys.readouterr().out
    assert code == 1
    assert "RETRACTED per Retraction Watch" in out
    assert "no author data" not in out


def test_fail_on_venue(tmp_path, capsys, monkeypatch):
    """Tier V: venue disagreement exits 0 by default, 1 with --fail-on venue."""

    class VenueFake(FakeClient):
        table = {
            "10.1/venue": CanonicalRecord(
                doi="10.1/venue",
                authors=["Smith"],
                year=2020,
                title="A study of widgets and gadgets",
                journal="Cell",
            ),
        }

    monkeypatch.setattr(cli, "CrossRefClient", VenueFake)
    bib = _write(
        tmp_path,
        "@article{k, author={Smith, J}, year={2020}, "
        "title={A study of widgets and gadgets}, "
        "journal={Nature}, doi={10.1/venue}}",
    )
    # Default --fail-on does NOT include venue → exit 0
    assert cli.main([bib]) == 0
    # Explicit --fail-on venue → exit 1
    assert cli.main([bib, "--fail-on", "venue"]) == 1
