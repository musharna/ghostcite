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
    assert db.lookup("10.9999/correction-only") == (False, False)


def test_miss_returns_false_false(tmp_path):
    db = _db(tmp_path)
    assert db.lookup("10.1/nope") == (False, False)


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
