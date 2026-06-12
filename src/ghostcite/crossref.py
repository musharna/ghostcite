from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx

from ghostcite import __version__
from ghostcite._pace import _Pacer
from ghostcite.models import CanonicalRecord

if TYPE_CHECKING:
    from ghostcite.cache import DoiCache

_BASE = "https://api.crossref.org"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"


def _retraction_flags(message: dict) -> tuple[bool, bool]:
    """Return (retracted, expression_of_concern) from a CrossRef work message.

    CrossRef exposes retraction/EoC three ways, and the live schema (verified
    against the Wakefield 1998 Lancet DOI, 2026-06-08) uses ``updated-by``:
      - ``updated-by``: items ON THE RETRACTED WORK pointing forward to the
        notice; each has ``type`` in {retraction, expression_of_concern, ...}.
        This is the canonical "this paper was retracted" signal.
      - ``update-to``: the inverse -- items on the NOTICE pointing back to what
        it updates (kept for completeness; often null on the retracted work).
      - ``relation``: keys like ``is-retracted-by`` (rarely populated).
    """
    retracted = eoc = False
    relation = message.get("relation") or {}
    for key in relation:
        k = key.lower()
        if "retract" in k:
            retracted = True
        if "concern" in k:
            eoc = True
    for field in ("updated-by", "update-to"):
        for upd in message.get(field) or []:
            t = str(upd.get("type", "")).lower()
            if "retract" in t:
                retracted = True
            if "concern" in t:
                eoc = True
    return retracted, eoc


def _year(message: dict) -> int | None:
    for key in ("published", "published-print", "published-online", "issued"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def _record_from_message(message: dict, low_confidence: bool = False) -> CanonicalRecord:
    retracted, eoc = _retraction_flags(message)
    authors = [a.get("family", "").strip() for a in message.get("author") or [] if a.get("family")]
    title = (message.get("title") or [None])[0]
    journal = (message.get("container-title") or [None])[0]
    return CanonicalRecord(
        doi=(message.get("DOI") or "").lower() or None,
        authors=authors,
        year=_year(message),
        title=title,
        journal=journal,
        retracted=retracted,
        eoc=eoc,
        low_confidence=low_confidence,
    )


class CrossRefClient:
    def __init__(self, timeout: float = 20.0, max_rps: float | None = None):
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )
        self._pacer = _Pacer(max_rps)

    def __enter__(self) -> CrossRefClient:
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def _get(self, url: str, **kw) -> httpx.Response:
        """GET with a single retry on a transient 429/503, honoring Retry-After
        (capped at 60s). The caller handles status codes (e.g. 404)."""
        self._pacer.wait()
        r = self._client.get(url, **kw)
        self._pacer.update_from_headers(r.headers)
        if r.status_code in (429, 503):
            delay = min(int(r.headers.get("Retry-After", "5")), 60)
            time.sleep(delay)
            self._pacer.wait()
            r = self._client.get(url, **kw)
            self._pacer.update_from_headers(r.headers)
        return r

    def lookup_by_doi(
        self, doi: str, *, cache: DoiCache | None = None
    ) -> CanonicalRecord | None:
        """Look up a DOI against CrossRef, with optional read-through caching.

        Parameters
        ----------
        doi:
            The DOI to look up.
        cache:
            Optional :class:`~ghostcite.cache.DoiCache`. When provided:
            - Cache hit (record or known-404 ``None``) returned immediately,
              no network call.
            - Cache miss (``MISS``) -> network fetch -> result stored in cache.
            When ``None`` (default), behaviour is identical to the pre-cache API.
        """
        if cache is not None:
            from ghostcite.cache import MISS

            cached = cache.get(doi)
            if cached is not MISS:
                # cached may be None (known 404) or a CanonicalRecord
                return cached  # type: ignore[return-value]

        r = self._get(f"{_BASE}/works/{doi}")
        if r.status_code == 404:
            if cache is not None:
                cache.put(doi, None)
            return None
        r.raise_for_status()
        record = _record_from_message(r.json()["message"])
        if cache is not None:
            cache.put(doi, record)
        return record

    def search_bibliographic(
        self, author: str | None, year: int | None, title: str | None
    ) -> CanonicalRecord | None:
        query = " ".join(str(x) for x in (author, year, title) if x).strip()
        if not query:
            return None
        r = self._get(f"{_BASE}/works", params={"query.bibliographic": query, "rows": 1})
        r.raise_for_status()
        items = r.json().get("message", {}).get("items") or []
        if not items:
            return None
        return _record_from_message(items[0], low_confidence=True)
