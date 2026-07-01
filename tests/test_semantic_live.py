"""Real-execution checks. Skipped unless the relevant live env is present.

Run a local backend (e.g. Ollama) and export:
  GHOSTCITE_LIVE_SEMANTIC=1
  GHOSTCITE_SEMANTIC_BASE_URL=http://localhost:11434/v1
  GHOSTCITE_SEMANTIC_MODEL=llama3.1
Optionally GHOSTCITE_SEMANTIC_API_KEY for hosted endpoints.
"""

import os

import pytest

from ghostcite.crossref import CrossRefClient

# These hit real network/backends; select them with `pytest -m live` (the weekly
# live-tests workflow). Each test still skips unless its GHOSTCITE_LIVE* env is set.
pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("GHOSTCITE_LIVE") != "1",
    reason="set GHOSTCITE_LIVE=1 to run live network checks",
)
def test_live_crossref_abstract_fetch():
    with CrossRefClient() as c:
        rec = c.lookup_by_doi("10.1038/s41586-021-03819-2")
    assert rec is not None
    assert rec.abstract is None or isinstance(rec.abstract, str)


@pytest.mark.skipif(
    os.environ.get("GHOSTCITE_LIVE_SEMANTIC") != "1",
    reason="set GHOSTCITE_LIVE_SEMANTIC=1 + backend env to run live backend check",
)
def test_live_backend_flags_unsupported():
    from ghostcite.models import Tier
    from ghostcite.semantic.backends import build_backend
    from ghostcite.semantic.support import check_claim_support

    backend = build_backend(
        os.environ.get("GHOSTCITE_SEMANTIC_KIND", "openai"),
        base_url=os.environ.get("GHOSTCITE_SEMANTIC_BASE_URL"),
        api_key=os.environ.get("GHOSTCITE_SEMANTIC_API_KEY"),
        model=os.environ.get("GHOSTCITE_SEMANTIC_MODEL", "llama3.1"),
    )

    class _Provider:
        def get_abstract(self, doi):
            return "We found that compound X had no measurable effect on disease Y."

    f = check_claim_support(
        "Compound X cures disease Y.", "10.1/x", backend=backend, source_provider=_Provider()
    )
    assert f is not None and f.tier is Tier.SUPPORT and f.deterministic is False
