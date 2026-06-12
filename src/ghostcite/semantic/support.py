"""Claim-support checking: resolve the cited abstract, ask a backend, map to a Finding."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ghostcite.crossref import CrossRefClient
from ghostcite.models import Citation, Finding, SemanticVerdict, Tier

if TYPE_CHECKING:
    from ghostcite.cache import DoiCache
    from ghostcite.semantic.backends import SemanticBackend


class SourceTextProvider(Protocol):
    def get_abstract(self, doi: str) -> str | None: ...


class AbstractProvider:
    """Default source-text provider: the cited paper's abstract via CrossRef (cached)."""

    def __init__(
        self, *, client: CrossRefClient | None = None, cache: DoiCache | None = None
    ) -> None:
        self._client = client
        self._cache = cache

    def get_abstract(self, doi: str) -> str | None:
        if self._client is not None:
            rec = self._client.lookup_by_doi(doi, cache=self._cache)
        else:
            with CrossRefClient() as c:
                rec = c.lookup_by_doi(doi, cache=self._cache)
        return rec.abstract if rec else None


def check_claim_support(
    claim: str,
    doi: str,
    *,
    backend: SemanticBackend,
    source_provider: SourceTextProvider | None = None,
    cache: DoiCache | None = None,
) -> Finding | None:
    """Return a SUPPORT Finding iff the cited abstract does NOT support the claim.

    SUPPORTED / UNCERTAIN / missing-abstract all return None (uncertain never
    fails CI). The Finding is flagged deterministic=False.
    """
    provider = source_provider or AbstractProvider(cache=cache)
    abstract = provider.get_abstract(doi)
    if not abstract:
        return None

    result = backend.assess_support(claim, abstract)
    if result.verdict is not SemanticVerdict.UNSUPPORTED:
        return None

    citation = Citation(raw=claim, doi=doi)
    return Finding(
        citation=citation,
        tier=Tier.SUPPORT,
        canonical=None,
        message=f"cited source does not support the claim — {result.rationale}",
        cross_check=f"semantic:{backend.name}",
        deterministic=False,
    )
