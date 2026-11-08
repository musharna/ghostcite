# src/ghostcite/retractions.py
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from ghostcite import __version__

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:")
_LABS_URL = "https://api.labs.crossref.org/data/retractionwatch"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"

# The auto-loaded cache is warned about past this age. Retraction Watch adds
# notices daily; a month bounds how far behind an unpinned run can silently be.
# A pinned ``--retraction-db <path>`` is a deliberate choice and is not checked.
DEFAULT_CACHE_MAX_AGE_DAYS = 30


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
            s = s[len(pref) :]
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

    def lookup(self, doi: str) -> tuple[bool, bool] | None:
        """``(retracted, eoc)`` when the snapshot lists the DOI, else ``None``.

        A DOI absent from the snapshot is unknown, not clean: it may have been
        retracted after the snapshot was taken."""
        d = normalize_doi(doi)
        if d not in self.retracted and d not in self.eoc:
            return None
        return (d in self.retracted, d in self.eoc)

    @classmethod
    def load(cls, path: str | Path) -> RetractionDB:
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as e:
            raise RetractionDBError(f"cannot read retraction db {p}: {e}") from e
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "OriginalPaperDOI" not in reader.fieldnames:
            raise RetractionDBError(f"{p}: missing required 'OriginalPaperDOI' column")
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
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
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
        db = RetractionDB.load(cache)
        _warn_if_stale(db, cache)
        return db
    return None


def _warn_if_stale(db: RetractionDB, path: Path) -> None:
    try:
        age = (date.today() - date.fromisoformat(db.snapshot_date)).days
    except ValueError:
        age = None
    if age is not None and age <= DEFAULT_CACHE_MAX_AGE_DAYS:
        return
    how_old = f"{age} days old" if age is not None else "of unknown age"
    warnings.warn(
        f"retraction snapshot {path} is {how_old} (limit {DEFAULT_CACHE_MAX_AGE_DAYS}); "
        "retractions since then are known only if CrossRef flags them. "
        "Refresh with `ghostcite fetch-retractions --mailto ...`.",
        UserWarning,
        stacklevel=3,
    )


def _write_atomic(dest: Path, data: bytes) -> None:
    """Write via a sibling temp file and ``os.replace``: a crash leaves the old file."""
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def fetch_retractions(mailto: str, dest: str | Path, *, client: httpx.Client | None = None) -> dict:
    """Download the Retraction Watch CSV to ``dest`` and write a sidecar
    ``<dest>.meta.json``. ``mailto`` is required by Crossref Labs. Returns meta."""
    if not mailto or not mailto.strip():
        raise RetractionDBError(
            "fetch-retractions requires a contact email: pass --mailto or set "
            "GHOSTCITE_MAILTO (Crossref Labs requires a mailto query parameter)."
        )
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{_LABS_URL}?mailto={mailto.strip()}"
    owns = client is None
    client = client or httpx.Client(
        timeout=180.0, headers={"User-Agent": _UA}, follow_redirects=True
    )
    try:
        r = client.get(url)
        r.raise_for_status()
        data = r.content
    finally:
        if owns:
            client.close()
    _write_atomic(dest, data)  # CSV first: its meta must never describe a file not on disk
    line_breaks = data.count(b"\n")
    row_count = max(0, line_breaks - (1 if data.endswith(b"\n") else 0))
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_url": _LABS_URL,  # mailto deliberately omitted
        "sha256": hashlib.sha256(data).hexdigest(),
        "row_count": row_count,
    }
    _write_atomic(dest.with_suffix(".meta.json"), json.dumps(meta, indent=2).encode("utf-8"))
    return meta
