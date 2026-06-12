from ghostcite.cache import DoiCache
from ghostcite.models import CanonicalRecord


def test_abstract_round_trips(tmp_path):
    cache = DoiCache(cache_dir=tmp_path)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024, abstract="Hello world.")
    cache.put("10.1/x", rec)
    got = cache.get("10.1/x")
    assert got is not None
    assert got.abstract == "Hello world."
