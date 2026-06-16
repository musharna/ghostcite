from __future__ import annotations

import os

import httpx

from ghostcite import __version__
from ghostcite._pace import _Pacer
from ghostcite.compare import _is_initials, normalize_surname
from ghostcite.models import OpenAlexRecord

_BASE = "https://api.openalex.org"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"


def _surname(display_name: str | None) -> str | None:
    """OpenAlex ``display_name`` is "Firstname Lastname" — last non-initials token,
    normalized for comparison. Returns None if no usable surname token is found."""
    if not display_name:
        return None
    tokens = display_name.split()
    if not tokens:
        return None
    # A single token is always the surname, even if it looks like initials.
    if len(tokens) == 1:
        return normalize_surname(tokens[0]) or None
    # Multiple tokens: drop initials clusters, keep the last remaining token.
    non_initials = [t for t in tokens if not _is_initials(t)]
    if not non_initials:
        return None
    return normalize_surname(non_initials[-1]) or None


def _record_from_work(work: dict) -> OpenAlexRecord:
    """Parse an OpenAlex /works JSON object into an OpenAlexRecord."""
    authorships = work.get("authorships") or []
    first_author_surname: str | None = None
    if authorships:
        first_display = (authorships[0].get("author") or {}).get("display_name")
        first_author_surname = _surname(first_display)
    year = work.get("publication_year")
    title = work.get("title")
    retracted = bool(work.get("is_retracted"))
    return OpenAlexRecord(
        first_author_surname=first_author_surname,
        year=year,
        title=title,
        retracted=retracted,
    )


class OpenAlexClient:
    """Thin OpenAlex client for DOI→work resolution.

    Uses its own pacer (10 req/s default per OpenAlex polite pool).
    Supports the ``mailto`` parameter for the polite pool — set via
    ``--openalex-mailto`` or the ``OPENALEX_MAILTO`` env var.
    """

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        max_rps: float | None = None,
        mailto: str | None = None,
    ) -> None:
        self._mailto = mailto or os.environ.get("OPENALEX_MAILTO")
        self._pacer = _Pacer(max_rps or 10)
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )

    def __enter__(self) -> OpenAlexClient:
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def lookup_by_doi(self, doi: str) -> OpenAlexRecord | None:
        """Resolve a DOI via OpenAlex /works/doi:<doi>. Returns None on 404."""
        url = f"{_BASE}/works/doi:{doi}"
        params: dict[str, str] = {}
        if self._mailto:
            params["mailto"] = self._mailto
        self._pacer.wait()
        r = self._client.get(url, params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _record_from_work(r.json())
