"""Tests for ghostcite.api: check_doi, check_text, CheckResult."""

from __future__ import annotations

from ghostcite.api import CheckResult, check_doi, check_text

from ghostcite.models import CanonicalRecord, Finding, Tier

# ---------------------------------------------------------------------------
# FakeClient — same pattern as test_cli.py
# ---------------------------------------------------------------------------


class FakeClient:
    """Stand-in for CrossRefClient; maps DOI -> CanonicalRecord | None."""

    table: dict[str, CanonicalRecord | None] = {
        "10.3390/plants13060869": CanonicalRecord(
            doi="10.3390/plants13060869",
            authors=["Chen"],
            year=2024,
            title="Integrated Transcriptome and Proteome Analysis",
        ),
        "10.1/retracted": CanonicalRecord(
            doi="10.1/retracted",
            authors=["Doe"],
            year=2000,
            title="Some retracted paper",
            retracted=True,
        ),
        "10.1/notfound": None,  # simulates 404
    }

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def lookup_by_doi(self, doi, *, cache=None):
        return self.table.get(doi, None)

    def search_bibliographic(self, *a):
        return None


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_is_ghost_author(self):
        r = CheckResult(doi="10.1/x", tier=Tier.AUTHOR, is_ghost=True, message="m", canonical=None)
        assert r.is_ghost is True

    def test_is_ghost_retraction(self):
        r = CheckResult(
            doi="10.1/x", tier=Tier.RETRACTION, is_ghost=True, message="m", canonical=None
        )
        assert r.is_ghost is True

    def test_is_ghost_year(self):
        r = CheckResult(doi="10.1/x", tier=Tier.YEAR, is_ghost=True, message="m", canonical=None)
        assert r.is_ghost is True

    def test_not_ghost_ok(self):
        r = CheckResult(doi="10.1/x", tier=Tier.OK, is_ghost=False, message="OK", canonical=None)
        assert r.is_ghost is False

    def test_not_ghost_cosmetic(self):
        r = CheckResult(
            doi="10.1/x", tier=Tier.COSMETIC, is_ghost=False, message="c", canonical=None
        )
        assert r.is_ghost is False

    def test_cross_check_defaults_none(self):
        r = CheckResult(doi=None, tier=Tier.OK, is_ghost=False, message="", canonical=None)
        assert r.cross_check is None


# ---------------------------------------------------------------------------
# check_doi
# ---------------------------------------------------------------------------


class TestCheckDoi:
    def test_correct_author_returns_ok(self):
        result = check_doi(
            "10.3390/plants13060869",
            claimed_author="Chen",
            claimed_year=2024,
            client=FakeClient(),
        )
        assert result.tier == Tier.OK
        assert result.is_ghost is False
        assert result.doi == "10.3390/plants13060869"

    def test_wrong_author_returns_author_tier(self):
        result = check_doi(
            "10.3390/plants13060869",
            claimed_author="Li",
            claimed_year=2024,
            client=FakeClient(),
        )
        assert result.tier == Tier.AUTHOR
        assert result.is_ghost is True

    def test_unresolvable_doi(self):
        result = check_doi("10.1/notfound", claimed_author="X", client=FakeClient())
        assert result.tier == Tier.UNRESOLVABLE
        assert result.is_ghost is False

    def test_retracted_doi(self):
        result = check_doi("10.1/retracted", client=FakeClient())
        assert result.tier == Tier.RETRACTION
        assert result.is_ghost is True

    def test_no_claimed_author_retracted(self):
        """check_doi without claimed fields still reports RETRACTION."""
        result = check_doi("10.1/retracted", client=FakeClient())
        assert result.tier == Tier.RETRACTION

    def test_retraction_db_override(self, tmp_path):
        """Retraction DB override fires even when CrossRef doesn't flag it."""
        from ghostcite.retractions import RetractionDB

        class NotRetractedFake(FakeClient):
            table = {
                "10.1/stealthy": CanonicalRecord(
                    doi="10.1/stealthy",
                    authors=["Doe"],
                    year=2000,
                    title="t",
                    retracted=False,
                )
            }

        csv = tmp_path / "rw.csv"
        csv.write_text("OriginalPaperDOI,RetractionNature\n10.1/stealthy,Retraction\n", "utf-8")
        rdb = RetractionDB.load(csv)

        result = check_doi("10.1/stealthy", client=NotRetractedFake(), retraction_db=rdb)
        assert result.tier == Tier.RETRACTION
        assert result.is_ghost is True

    def test_creates_client_when_none(self, monkeypatch):
        """check_doi creates its own CrossRefClient when client=None."""
        created = []

        class Tracker(FakeClient):
            def __init__(self, *a, **kw):
                created.append(True)

        import ghostcite.api as api_mod

        monkeypatch.setattr(api_mod, "CrossRefClient", Tracker)
        result = check_doi("10.3390/plants13060869", claimed_author="Chen")
        assert created  # client was instantiated
        assert result.tier in {Tier.OK, Tier.AUTHOR, Tier.UNRESOLVABLE, Tier.RETRACTION}

    def test_priority_author_over_year(self):
        """AUTHOR finding takes priority over YEAR (A > B)."""

        class BothFake(FakeClient):
            table = {
                "10.1/both": CanonicalRecord(
                    doi="10.1/both",
                    authors=["Real"],
                    year=2020,
                    title="t",
                )
            }

        # Wrong author AND wrong year -> should be AUTHOR
        result = check_doi(
            "10.1/both",
            claimed_author="Wrong",
            claimed_year=1999,
            client=BothFake(),
        )
        assert result.tier == Tier.AUTHOR

    def test_author_beats_retraction_in_priority(self):
        """Spec priority: AUTHOR > RETRACTION > YEAR. When both present, AUTHOR wins."""

        class RetractedWrongAuthor(FakeClient):
            table = {
                "10.1/ret": CanonicalRecord(
                    doi="10.1/ret",
                    authors=["Real"],
                    year=2000,
                    title="t",
                    retracted=True,
                )
            }

        result = check_doi(
            "10.1/ret",
            claimed_author="Wrong",
            client=RetractedWrongAuthor(),
        )
        # Per spec: AUTHOR > RETRACTION priority; both are ghost-tier
        assert result.tier == Tier.AUTHOR
        assert result.is_ghost is True

    def test_ok_when_no_findings(self):
        result = check_doi(
            "10.3390/plants13060869",
            claimed_author="Chen",
            claimed_year=2024,
            client=FakeClient(),
        )
        assert result.tier == Tier.OK
        assert result.message.lower() == "ok"


# ---------------------------------------------------------------------------
# check_text
# ---------------------------------------------------------------------------


BIBTEX_CORRECT = (
    "@article{k, author={Chen, M}, year={2024}, "
    "title={Integrated Transcriptome and Proteome Analysis}, "
    "doi={10.3390/plants13060869}}"
)

BIBTEX_WRONG_AUTHOR = (
    "@article{k, author={Li, X}, year={2024}, "
    "title={Integrated Transcriptome and Proteome Analysis}, "
    "doi={10.3390/plants13060869}}"
)

BIBTEX_TWO_ENTRIES = (
    "@article{a, author={Chen, M}, year={2024}, "
    "title={Integrated Transcriptome and Proteome Analysis}, "
    "doi={10.3390/plants13060869}}\n"
    "@article{b, author={Li, X}, year={2024}, "
    "title={Integrated Transcriptome and Proteome Analysis}, "
    "doi={10.3390/plants13060869}}"
)


class TestCheckText:
    def test_returns_list_of_findings(self):
        findings = check_text(BIBTEX_CORRECT, client=FakeClient())
        assert isinstance(findings, list)

    def test_empty_findings_on_correct(self):
        findings = check_text(BIBTEX_CORRECT, client=FakeClient())
        # No findings means all OK
        assert findings == [] or all(f.tier == Tier.OK for f in findings)

    def test_author_finding_on_wrong(self):
        findings = check_text(BIBTEX_WRONG_AUTHOR, client=FakeClient())
        assert any(f.tier == Tier.AUTHOR for f in findings)

    def test_two_entries_one_wrong(self):
        findings = check_text(BIBTEX_TWO_ENTRIES, client=FakeClient())
        author_findings = [f for f in findings if f.tier == Tier.AUTHOR]
        assert len(author_findings) >= 1

    def test_fmt_auto_bibtex(self):
        findings = check_text(BIBTEX_WRONG_AUTHOR, fmt="auto", client=FakeClient())
        assert any(f.tier == Tier.AUTHOR for f in findings)

    def test_fmt_doi_list(self):
        findings = check_text("10.3390/plants13060869\n", fmt="doi", client=FakeClient())
        assert isinstance(findings, list)

    def test_retraction_db_used(self, tmp_path):
        from ghostcite.retractions import RetractionDB

        class NotRetractedFake(FakeClient):
            table = {
                "10.1/stealthy": CanonicalRecord(
                    doi="10.1/stealthy",
                    authors=["Doe"],
                    year=2000,
                    title="t",
                    retracted=False,
                )
            }

        csv = tmp_path / "rw.csv"
        csv.write_text("OriginalPaperDOI,RetractionNature\n10.1/stealthy,Retraction\n", "utf-8")
        rdb = RetractionDB.load(csv)
        bib = "@article{k, author={Doe, J}, year={2000}, title={t}, doi={10.1/stealthy}}"
        findings = check_text(bib, client=NotRetractedFake(), retraction_db=rdb)
        assert any(f.tier == Tier.RETRACTION for f in findings)

    def test_cache_passed_through(self, tmp_path):
        """cache kwarg is forwarded to the client's lookup_by_doi."""
        from ghostcite.cache import DoiCache

        calls = []

        class TrackingFake(FakeClient):
            def lookup_by_doi(self, doi, *, cache=None):
                calls.append(cache)
                return super().lookup_by_doi(doi, cache=cache)

        cache = DoiCache(cache_dir=tmp_path / "doi")
        check_text(BIBTEX_CORRECT, client=TrackingFake(), cache=cache)
        assert calls  # lookup was called
        assert calls[0] is cache  # cache was forwarded

    def test_returns_finding_objects(self):
        findings = check_text(BIBTEX_WRONG_AUTHOR, client=FakeClient())
        for f in findings:
            assert isinstance(f, Finding)
