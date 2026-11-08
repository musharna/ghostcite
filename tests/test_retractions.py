# tests/test_retractions.py
from __future__ import annotations

import json as _json

import httpx
import pytest

from ghostcite.retractions import (
    RetractionDB,
    RetractionDBError,
    default_cache_path,
    fetch_retractions,
    normalize_doi,
    resolve_db,
)

_CSV = (
    "RecordID,OriginalPaperDOI,RetractionDOI,RetractionNature\n"
    "1,10.1016/S0140-6736(97)11096-0,10.1016/x,Retraction\n"
    "2,https://doi.org/10.1111/EOC-PAPER,10.1111/y,Expression of Concern\n"
    "3,10.9999/correction-only,10.9999/z,Correction\n"
)

_RW_BODY = (
    "RecordID,OriginalPaperDOI,RetractionNature\n"
    "1,10.1/a,Retraction\n2,10.1/b,Expression of Concern\n"
)


def _db(tmp_path):
    p = tmp_path / "rw.csv"
    p.write_text(_CSV, encoding="utf-8")
    return RetractionDB.load(p)


def test_normalize_doi_strips_prefix_and_lowercases():
    assert normalize_doi("https://doi.org/10.1/AbC") == "10.1/abc"
    assert normalize_doi("doi:10.1/AbC") == "10.1/abc"
    assert normalize_doi("  10.1/ABC  ") == "10.1/abc"
    assert normalize_doi(None) == ""


def test_lookup_retracted(tmp_path):
    db = _db(tmp_path)
    assert db.lookup("10.1016/s0140-6736(97)11096-0") == (True, False)


def test_lookup_eoc_normalizes_db_side(tmp_path):
    db = _db(tmp_path)
    assert db.lookup("10.1111/eoc-paper") == (False, True)


def test_correction_is_not_tier_r(tmp_path):
    db = _db(tmp_path)
    assert db.lookup("10.9999/correction-only") is None


def test_miss_is_unknown_not_clean(tmp_path):
    # Absent from the snapshot means "not known retracted as of the snapshot",
    # which must not read as a (False, False) verdict that overrides CrossRef.
    db = _db(tmp_path)
    assert db.lookup("10.1/nope") is None
    assert db.lookup("") is None


def test_row_count(tmp_path):
    assert _db(tmp_path).row_count == 3


def test_missing_file_raises(tmp_path):
    with pytest.raises(RetractionDBError):
        RetractionDB.load(tmp_path / "does-not-exist.csv")


def test_missing_column_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    with pytest.raises(RetractionDBError):
        RetractionDB.load(p)


def test_semicolon_multi_doi_cell(tmp_path):
    p = tmp_path / "multi.csv"
    p.write_text(
        "OriginalPaperDOI,RetractionNature\n10.1/a;10.1/b,Retraction\n",
        encoding="utf-8",
    )
    db = RetractionDB.load(p)
    assert db.lookup("10.1/a") == (True, False)
    assert db.lookup("10.1/b") == (True, False)


def test_default_cache_path_honors_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_cache_path() == tmp_path / "ghostcite" / "retractions.csv"


def test_resolve_db_none_literal_returns_none():
    assert resolve_db("none") is None
    assert resolve_db("NONE") is None


def test_resolve_db_explicit_path(tmp_path):
    p = tmp_path / "rw.csv"
    p.write_text("OriginalPaperDOI,RetractionNature\n10.1/a,Retraction\n", "utf-8")
    db = resolve_db(str(p))
    assert db is not None and db.lookup("10.1/a") == (True, False)


def test_resolve_db_auto_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cache = tmp_path / "ghostcite" / "retractions.csv"
    cache.parent.mkdir(parents=True)
    cache.write_text("OriginalPaperDOI,RetractionNature\n10.1/c,Retraction\n", "utf-8")
    db = resolve_db(None)
    assert db is not None and db.lookup("10.1/c") == (True, False)


def test_resolve_db_absent_cache_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))  # nothing written
    assert resolve_db(None) is None


def test_fetch_writes_csv_and_meta(tmp_path, httpx_mock):
    httpx_mock.add_response(
        url="https://api.labs.crossref.org/data/retractionwatch?mailto=me@x.org",
        text=_RW_BODY,
    )
    dest = tmp_path / "retractions.csv"
    meta = fetch_retractions("me@x.org", dest)
    assert dest.read_text(encoding="utf-8") == _RW_BODY
    assert meta["row_count"] == 2
    side = dest.with_suffix(".meta.json")
    on_disk = _json.loads(side.read_text(encoding="utf-8"))
    assert on_disk["row_count"] == 2
    assert "fetched_at" in on_disk and on_disk["sha256"]
    # mailto must NOT be persisted in the recorded source_url
    assert "mailto" not in on_disk["source_url"]


def test_fetch_requires_mailto(tmp_path):
    with pytest.raises(RetractionDBError):
        fetch_retractions("", tmp_path / "x.csv")


def test_fetch_http_error_raises(tmp_path, httpx_mock):
    httpx_mock.add_response(
        url="https://api.labs.crossref.org/data/retractionwatch?mailto=me@x.org",
        status_code=503,
    )
    with pytest.raises(httpx.HTTPStatusError):
        fetch_retractions("me@x.org", tmp_path / "x.csv")


def test_fetch_row_count_no_trailing_newline(tmp_path, httpx_mock):
    """row_count is correct when CSV body has no trailing newline."""
    body = (
        "OriginalPaperDOI,RetractionNature\n"
        "10.1/a,Retraction\n"
        "10.1/b,Retraction"  # no trailing newline
    )
    httpx_mock.add_response(
        url="https://api.labs.crossref.org/data/retractionwatch?mailto=me@x.org",
        content=body.encode(),
    )
    dest = tmp_path / "retractions.csv"
    meta = fetch_retractions("me@x.org", dest)
    assert meta["row_count"] == 2


def test_fetch_row_count_with_trailing_newline(tmp_path, httpx_mock):
    """row_count is correct when CSV body ends with a newline (existing behavior preserved)."""
    body = (
        "OriginalPaperDOI,RetractionNature\n"
        "10.1/a,Retraction\n"
        "10.1/b,Retraction\n"  # trailing newline
    )
    httpx_mock.add_response(
        url="https://api.labs.crossref.org/data/retractionwatch?mailto=me@x.org",
        content=body.encode(),
    )
    dest = tmp_path / "retractions.csv"
    meta = fetch_retractions("me@x.org", dest)
    assert meta["row_count"] == 2


def _write_cache(tmp_path, monkeypatch, fetched_at=None):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cache = tmp_path / "ghostcite" / "retractions.csv"
    cache.parent.mkdir(parents=True)
    cache.write_text("OriginalPaperDOI,RetractionNature\n10.1/c,Retraction\n", "utf-8")
    if fetched_at is not None:
        meta = cache.with_suffix(".meta.json")
        meta.write_text(_json.dumps({"fetched_at": fetched_at}), encoding="utf-8")
    return cache


def test_resolve_db_warns_on_stale_default_cache(tmp_path, monkeypatch):
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=400)).isoformat()
    _write_cache(tmp_path, monkeypatch, fetched_at=old + "T00:00:00+00:00")
    with pytest.warns(UserWarning, match="400 days old"):
        db = resolve_db(None)
    # still used, not silently dropped
    assert db is not None and db.lookup("10.1/c") == (True, False)


def test_resolve_db_fresh_default_cache_does_not_warn(tmp_path, monkeypatch):
    import warnings

    _write_cache(tmp_path, monkeypatch)  # no meta -> file mtime (now)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert resolve_db(None) is not None


def test_resolve_db_explicit_path_is_not_age_checked(tmp_path, monkeypatch):
    # A pinned snapshot is a deliberate choice (reproducible CI); no nag.
    import warnings

    cache = _write_cache(tmp_path, monkeypatch, fetched_at="2001-01-01T00:00:00+00:00")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert resolve_db(str(cache)) is not None


def test_fetch_crash_mid_write_keeps_previous_snapshot(tmp_path, httpx_mock, monkeypatch):
    from pathlib import Path

    url = "https://api.labs.crossref.org/data/retractionwatch?mailto=me@x.org"
    dest = tmp_path / "retractions.csv"
    # positive control: a normal fetch lands the CSV and its meta
    httpx_mock.add_response(url=url, text=_RW_BODY)
    first = fetch_retractions("me@x.org", dest)
    assert dest.read_text(encoding="utf-8") == _RW_BODY

    new_body = _RW_BODY + "3,10.1/c,Retraction\n"
    httpx_mock.add_response(url=url, text=new_body)
    real_write_bytes = Path.write_bytes

    def crash_halfway(self, data):
        real_write_bytes(self, data[: len(data) // 2])
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", crash_halfway)
    with pytest.raises(OSError, match="disk full"):
        fetch_retractions("me@x.org", dest)
    monkeypatch.undo()

    assert dest.read_text(encoding="utf-8") == _RW_BODY  # not truncated
    meta = _json.loads(dest.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["fetched_at"] == first["fetched_at"]
    assert sorted(x.name for x in tmp_path.iterdir()) == [
        "retractions.csv",
        "retractions.meta.json",
    ]
