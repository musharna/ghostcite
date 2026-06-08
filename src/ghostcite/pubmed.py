from __future__ import annotations

import re

import httpx

from ghostcite import __version__
from ghostcite.compare import _is_initials, normalize_surname
from ghostcite.models import PubMedRecord

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_ESEARCH = f"{_EUTILS}/esearch.fcgi"
_ESUMMARY = f"{_EUTILS}/esummary.fcgi"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"
_YEAR_RE = re.compile(r"\d{4}")


class PubMedError(RuntimeError):
    """Raised when NCBI returns an error payload — fail loud, never silently skip."""


def _surname_from_author(name: str | None) -> str | None:
    """NCBI ``authors[].name`` is "Chen M" / "Wakefield AJ" — surname then
    space-separated initials cluster, no comma. Drop the initials, keep the
    surname tokens, normalize for comparison."""
    if not name:
        return None
    tokens = [t for t in name.split() if not _is_initials(t)]
    if not tokens:
        return None
    return normalize_surname(" ".join(tokens))


def _year_from_pubdate(pubdate: str | None) -> int | None:
    """``pubdate`` is "2024 Mar 18" / "2010" — the leading token is the year."""
    if not pubdate:
        return None
    m = _YEAR_RE.match(pubdate.strip())
    return int(m.group(0)) if m else None


class PubMedClient:
    """Thin NCBI E-utilities client for DOI→PMID resolution + summary parsing.

    Uses its OWN pacer with the NCBI rate floor (3 req/s without an API key,
    10 with), independent of CrossRef. NCBI summaries carry no rate headers, so
    the pacer floor is never raised from responses.
    """

    def __init__(
        self,
        *,
        tool: str = "ghostcite",
        email: str | None = None,
        api_key: str | None = None,
        timeout: float = 20.0,
        max_rps: float | None = None,
    ) -> None:
        from ghostcite._pace import _Pacer

        self._tool = tool
        self._email = email
        self._api_key = api_key
        self._pacer = _Pacer(max_rps or (10 if api_key else 3))
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )

    def __enter__(self) -> PubMedClient:
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def _params(self, extra: dict[str, str]) -> dict[str, str]:
        """Build query params: caller's fields, then retmode + tool, then the
        optional email/api_key — injected ONLY when explicitly provided (never
        hardcoded). ``tool=ghostcite`` is always sent per NCBI policy."""
        params: dict[str, str] = {**extra, "retmode": "json", "tool": self._tool}
        if self._email:
            params["email"] = self._email
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        self._pacer.wait()
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r

    def resolve_pmid(self, doi: str) -> str | None:
        r = self._get(_ESEARCH, self._params({"db": "pubmed", "term": f"{doi}[doi]"}))
        idlist = (r.json().get("esearchresult") or {}).get("idlist") or []
        if not idlist:
            return None
        # Trust idlist over the count field; >1 is ambiguous — take the first.
        return idlist[0]

    def summary(self, pmid: str) -> PubMedRecord:
        r = self._get(_ESUMMARY, self._params({"db": "pubmed", "id": pmid}))
        result = r.json().get("result") or {}
        entry = result.get(pmid)
        if entry is None:
            raise PubMedError(f"no esummary entry for pmid {pmid}")
        if "error" in entry:
            raise PubMedError(f"esummary error for pmid {pmid}: {entry['error']}")
        authors = entry.get("authors") or []
        first = authors[0].get("name") if authors else None
        pubtypes = {str(t).lower() for t in (entry.get("pubtype") or [])}
        return PubMedRecord(
            pmid=pmid,
            first_author_surname=_surname_from_author(first),
            year=_year_from_pubdate(entry.get("pubdate")),
            title=entry.get("title"),
            retracted=any("retract" in t for t in pubtypes),
            eoc=any("concern" in t for t in pubtypes),
        )

    def lookup_by_doi(self, doi: str) -> PubMedRecord | None:
        pmid = self.resolve_pmid(doi)
        if pmid is None:
            return None
        return self.summary(pmid)

    def lookup_by_doi_meta(
        self, author: str | None, year: int | None, title: str | None
    ) -> PubMedRecord | None:
        """No-DOI fallback: search by author + year + title words, accept only a
        single exact id (avoid false positives on broad matches)."""
        terms = []
        if author:
            terms.append(f"{author}[au]")
        if year:
            terms.append(f"{year}[dp]")
        if title:
            words = [w for w in re.findall(r"[A-Za-z]{4,}", title)][:6]
            terms.extend(words)
        if not terms:
            return None
        r = self._get(_ESEARCH, self._params({"db": "pubmed", "term": " AND ".join(terms)}))
        idlist = (r.json().get("esearchresult") or {}).get("idlist") or []
        if len(idlist) != 1:
            return None
        return self.summary(idlist[0])
