"""Tests for DoiCache: on-disk JSON, TTL, 404-None, MISS sentinel, corruption safety."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from ghostcite.cache import MISS, DoiCache

from ghostcite.models import CanonicalRecord


@pytest.fixture()
def cache(tmp_path):
    return DoiCache(cache_dir=tmp_path / "doi")


def _record(doi: str = "10.1234/test") -> CanonicalRecord:
    return CanonicalRecord(
        doi=doi,
        authors=["Smith"],
        year=2020,
        title="A test paper",
        journal="Test Journal",
        retracted=False,
        eoc=False,
        low_confidence=False,
    )


class TestRoundTrip:
    def test_miss_when_absent(self, cache):
        assert cache.get("10.1234/absent") is MISS

    def test_round_trip_record(self, cache):
        doi = "10.1234/test"
        rec = _record(doi)
        cache.put(doi, rec)
        result = cache.get(doi)
        assert result is not MISS
        assert result is not None
        assert result.doi == doi
        assert result.authors == ["Smith"]
        assert result.year == 2020
        assert result.title == "A test paper"
        assert result.journal == "Test Journal"
        assert result.retracted is False
        assert result.eoc is False
        assert result.low_confidence is False

    def test_round_trip_none_404(self, cache):
        """Storing None (known 404) must come back as None, not MISS."""
        doi = "10.1234/notfound"
        cache.put(doi, None)
        result = cache.get(doi)
        assert result is not MISS
        assert result is None

    def test_miss_is_distinct_from_none(self, cache):
        cache.put("10.1/none", None)
        assert cache.get("10.1/none") is None  # cached 404
        assert cache.get("10.1/absent") is MISS  # never stored


class TestDoiNormalization:
    def test_doi_key_is_normalized(self, cache):
        doi = "10.1234/test"
        cache.put(doi, _record(doi))
        # Accessing via URL prefix should still hit
        assert cache.get("https://doi.org/10.1234/test") is not MISS
        # Upper-case should also hit (normalize_doi lowercases)
        assert cache.get("10.1234/TEST") is not MISS


class TestTTL:
    def test_fresh_entry_is_returned(self, cache):
        doi = "10.1/fresh"
        cache.put(doi, _record(doi))
        assert cache.get(doi) is not MISS

    def test_expired_entry_returns_miss(self, tmp_path):
        """Write an entry with a fetched_at in the past beyond TTL."""
        cache = DoiCache(cache_dir=tmp_path / "doi", ttl_days=1)
        doi = "10.1/expired"
        cache.put(doi, _record(doi))

        # Manually rewrite the file with an old fetched_at
        key = cache._key(doi)
        path = cache._path(key)
        data = json.loads(path.read_text())
        old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        data["fetched_at"] = old_ts
        path.write_text(json.dumps(data))

        assert cache.get(doi) is MISS

    def test_custom_ttl_respected(self, tmp_path):
        cache = DoiCache(cache_dir=tmp_path / "doi", ttl_days=365)
        doi = "10.1/longttl"
        cache.put(doi, _record(doi))
        assert cache.get(doi) is not MISS


class TestCorruption:
    def test_corrupted_json_returns_miss(self, cache):
        doi = "10.1/corrupt"
        cache.put(doi, _record(doi))
        key = cache._key(doi)
        path = cache._path(key)
        path.write_bytes(b"not valid json{{{{")
        # Should not raise; MISS instead
        assert cache.get(doi) is MISS

    def test_missing_required_fields_returns_miss(self, cache):
        doi = "10.1/badschema"
        cache.put(doi, _record(doi))
        key = cache._key(doi)
        path = cache._path(key)
        path.write_text(json.dumps({"some": "garbage"}))
        assert cache.get(doi) is MISS

    def test_truncated_file_returns_miss(self, cache):
        doi = "10.1/truncated"
        cache.put(doi, _record(doi))
        key = cache._key(doi)
        path = cache._path(key)
        content = path.read_text()
        path.write_text(content[:10])  # truncate
        assert cache.get(doi) is MISS


class TestCustomDir:
    def test_custom_dir_is_created(self, tmp_path):
        custom = tmp_path / "my" / "custom" / "dir"
        assert not custom.exists()
        cache = DoiCache(cache_dir=custom)
        doi = "10.1/test"
        cache.put(doi, _record(doi))
        assert custom.exists()
        assert cache.get(doi) is not MISS

    def test_two_caches_same_dir_share_data(self, tmp_path):
        d = tmp_path / "shared"
        c1 = DoiCache(cache_dir=d)
        c2 = DoiCache(cache_dir=d)
        doi = "10.1/shared"
        c1.put(doi, _record(doi))
        assert c2.get(doi) is not MISS


class TestAtomicWrite:
    def test_no_partial_file_left_on_put(self, tmp_path):
        """Verify the cache dir contains only .json files after put (no .tmp leftovers)."""
        cache = DoiCache(cache_dir=tmp_path / "doi")
        cache.put("10.1/x", _record("10.1/x"))
        cache_dir = tmp_path / "doi"
        leftovers = list(cache_dir.glob("*.tmp"))
        assert leftovers == []
