# tests/test_retractions.py
from __future__ import annotations

import pytest
from ghostcite.retractions import (
    RetractionDB,
    RetractionDBError,
    default_cache_path,
    normalize_doi,
    resolve_db,
)

_CSV = (
    "RecordID,OriginalPaperDOI,RetractionDOI,RetractionNature\n"
    "1,10.1016/S0140-6736(97)11096-0,10.1016/x,Retraction\n"
    "2,https://doi.org/10.1111/EOC-PAPER,10.1111/y,Expression of Concern\n"
    "3,10.9999/correction-only,10.9999/z,Correction\n"
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
