from __future__ import annotations

import httpx

from ghostcite import __version__
from ghostcite.models import CanonicalRecord

_BASE = "https://api.crossref.org"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"


def _retraction_flags(message: dict) -> tuple[bool, bool]:
    """Return (retracted, expression_of_concern) from a CrossRef work message."""
    retracted = eoc = False
    relation = message.get("relation") or {}
    for key in relation:
        k = key.lower()
        if "retract" in k:
            retracted = True
        if "concern" in k:
            eoc = True
    for upd in message.get("update-to") or []:
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


def _record_from_message(
    message: dict, low_confidence: bool = False
) -> CanonicalRecord:
    retracted, eoc = _retraction_flags(message)
    authors = [
        a.get("family", "").strip()
        for a in message.get("author") or []
        if a.get("family")
    ]
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
    def __init__(self, timeout: float = 20.0):
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )

    def __enter__(self) -> "CrossRefClient":
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def lookup_by_doi(self, doi: str) -> CanonicalRecord | None:
        r = self._client.get(f"{_BASE}/works/{doi}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _record_from_message(r.json()["message"])

    def search_bibliographic(
        self, author: str | None, year: int | None, title: str | None
    ) -> CanonicalRecord | None:
        query = " ".join(str(x) for x in (author, year, title) if x).strip()
        if not query:
            return None
        r = self._client.get(
            f"{_BASE}/works", params={"query.bibliographic": query, "rows": 1}
        )
        r.raise_for_status()
        items = r.json().get("message", {}).get("items") or []
        if not items:
            return None
        return _record_from_message(items[0], low_confidence=True)
