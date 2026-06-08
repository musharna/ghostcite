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

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def lookup_by_doi(self, doi):
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
