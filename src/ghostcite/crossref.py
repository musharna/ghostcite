from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx

from ghostcite import __version__
from ghostcite._pace import _Pacer
from ghostcite.models import CanonicalRecord

if TYPE_CHECKING:
    from ghostcite.cache import DoiCache

_BASE = "https://api.crossref.org"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"

_TAG_RE = re.compile(r"<[^>]+>")


# CrossRef rejects very long query strings; a reference's identifying text
# (authors, year, title) sits at its start.
_MAX_REFERENCE_QUERY = 500


def _strip_jats(raw: str | None) -> str | None:
    """Flatten a CrossRef JATS abstract string to plain text, or None."""
    if not raw:
        return None
    text = _TAG_RE.sub("", raw)
    text = " ".join(text.split())  # collapse whitespace
    return text or None


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


def _preprint_flags(message: dict) -> tuple[bool, bool]:
    subtype = str(message.get("subtype", "")).lower()
    is_preprint = subtype == "preprint" or (
        str(message.get("type", "")).lower() == "posted-content" and subtype in ("", "preprint")
    )
    relation = message.get("relation") or {}
    has_rel = any("preprint" in k.lower() for k in relation)
    return is_preprint, has_rel


_DATE_KEYS = ("published", "published-print", "published-online", "issued")


def _years(message: dict) -> tuple[int, ...]:
    """Every distinct year CrossRef carries for this record, earliest first.

    An online-first article publishes twice: `published-online` in one year and
    `published-print` in the next. Both are real publication dates and the
    article is legitimately cited by either — in practice the print/issue year is
    the canonical form (featureCounts is universally "Liao et al. 2014" though
    CrossRef's `published` says 2013). Returning only the first key found made
    every such bibliography look wrong.
    """
    seen: list[int] = []
    for key in _DATE_KEYS:
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            y = int(parts[0][0])
            if y not in seen:
                seen.append(y)
    return tuple(sorted(seen))


def _year_of(message: dict, key: str) -> int | None:
    parts = (message.get(key) or {}).get("date-parts") or []
    return int(parts[0][0]) if parts and parts[0] and parts[0][0] else None


def _year(message: dict) -> int | None:
    ys = _years(message)
    return ys[0] if ys else None


def _record_from_message(message: dict, low_confidence: bool = False) -> CanonicalRecord:
    retracted, eoc = _retraction_flags(message)
    is_preprint, has_preprint_relation = _preprint_flags(message)
    authors = [a.get("family", "").strip() for a in message.get("author") or [] if a.get("family")]
    title = (message.get("title") or [None])[0]
    journal = (message.get("container-title") or [None])[0]
    return CanonicalRecord(
        doi=(message.get("DOI") or "").lower() or None,
        authors=authors,
        year=_year(message),
        years=_years(message),
        online_year=_year_of(message, "published-online"),
        print_year=_year_of(message, "published-print"),
        title=title,
        journal=journal,
        retracted=retracted,
        eoc=eoc,
        low_confidence=low_confidence,
        is_preprint=is_preprint,
        has_preprint_relation=has_preprint_relation,
        abstract=_strip_jats(message.get("abstract")),
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

    def doi_resolves(self, doi: str) -> bool | None:
        """Best-effort HEAD on https://doi.org/<doi> to distinguish a dead/fabricated DOI from
        one that simply isn't in CrossRef. Returns True (resolves), False (404/410), or None
        (network error / timeout — caller falls back to the generic message). Never raises."""
        try:
            self._pacer.wait()
            r = self._client.head(f"https://doi.org/{quote(doi, safe='/')}", follow_redirects=True)
            if r.status_code in (404, 410):
                return False
            return 200 <= r.status_code < 400
        except Exception:
            return None

    def lookup_by_doi(self, doi: str, *, cache: DoiCache | None = None) -> CanonicalRecord | None:
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

        r = self._get(f"{_BASE}/works/{quote(doi, safe='/')}")
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
        self,
        author: str | None,
        year: int | None,
        title: str | None,
        *,
        reference: str | None = None,
    ) -> CanonicalRecord | None:
        """Best match for a citation with no DOI. The hit is a GUESS: callers must
        confirm it is the cited work (``compare.search_hit_is_cited_work``).

        ``reference`` is the entry as printed. It is the query when no title was
        parsed (manuscript reference lists): ``query.bibliographic`` is built for
        whole reference strings, and "Gaut 1992" alone matches a book review.
        """
        if not title and reference:
            query = " ".join(reference.split())[:_MAX_REFERENCE_QUERY]
        else:
            query = " ".join(str(x) for x in (author, year, title) if x).strip()
        if not query:
            return None
        r = self._get(f"{_BASE}/works", params={"query.bibliographic": query, "rows": 1})
        r.raise_for_status()
        items = r.json().get("message", {}).get("items") or []
        if not items:
            return None
        return _record_from_message(items[0], low_confidence=True)
