# src/ghostcite/retractions.py
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:")


class RetractionDBError(Exception):
    """Raised when a retraction database cannot be read or parsed."""


def normalize_doi(doi: str | None) -> str:
    """Lowercase, strip a leading DOI URL/`doi:` prefix and surrounding space."""
    if not doi:
        return ""
    s = doi.strip()
    low = s.lower()
    for pref in _DOI_PREFIXES:
        if low.startswith(pref):
            s = s[len(pref):]
            break
    return s.strip().lower()


@dataclass
class RetractionDB:
    retracted: set[str] = field(default_factory=set)
    eoc: set[str] = field(default_factory=set)
    row_count: int = 0
    snapshot_date: str = ""  # YYYY-MM-DD, from sidecar meta or file mtime

    @property
    def source_label(self) -> str:
        when = f" {self.snapshot_date}" if self.snapshot_date else ""
        return f"Retraction Watch snapshot{when} ({self.row_count} rows)"

    def lookup(self, doi: str) -> tuple[bool, bool]:
        d = normalize_doi(doi)
        if not d:
            return (False, False)
        return (d in self.retracted, d in self.eoc)

    @classmethod
    def load(cls, path: str | Path) -> "RetractionDB":
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as e:
            raise RetractionDBError(f"cannot read retraction db {p}: {e}") from e
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "OriginalPaperDOI" not in reader.fieldnames:
            raise RetractionDBError(
                f"{p}: missing required 'OriginalPaperDOI' column"
            )
        retracted: set[str] = set()
        eoc: set[str] = set()
        rows = 0
        for row in reader:
            rows += 1
            nature = (row.get("RetractionNature") or "").strip().lower()
            is_retraction = "retraction" in nature
            is_eoc = "expression of concern" in nature
            if not (is_retraction or is_eoc):
                continue
            for raw in (row.get("OriginalPaperDOI") or "").split(";"):
                d = normalize_doi(raw)
                if not d:
                    continue
                if is_retraction:
                    retracted.add(d)
                elif is_eoc:
                    eoc.add(d)
        return cls(
            retracted=retracted,
            eoc=eoc,
            row_count=rows,
            snapshot_date=_snapshot_date(p),
        )


def _snapshot_date(csv_path: Path) -> str:
    """Snapshot date for the source label: sidecar meta `fetched_at` if present,
    else the CSV file's mtime. Empty string if neither is available."""
    meta = csv_path.with_suffix(".meta.json")
    if meta.exists():
        try:
            import json

            fetched = json.loads(meta.read_text(encoding="utf-8")).get("fetched_at")
            if fetched:
                return str(fetched)[:10]
        except (OSError, ValueError):
            pass
    try:
        return date.fromtimestamp(csv_path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return Path(base) / "ghostcite" / "retractions.csv"


def resolve_db(retraction_db_arg: str | None) -> RetractionDB | None:
    """Precedence: literal 'none' -> None; explicit path -> load (error if bad);
    no arg + default cache exists -> load cache; otherwise -> None (live)."""
    if retraction_db_arg is not None and retraction_db_arg.strip().lower() == "none":
        return None
    if retraction_db_arg:
        return RetractionDB.load(retraction_db_arg)
    cache = default_cache_path()
    if cache.exists():
        return RetractionDB.load(cache)
    return None
