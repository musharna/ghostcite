"""On-disk DOI cache for ghostcite.

Stores CrossRef lookup results as JSON files under an XDG-compliant directory.
Keys are normalized DOIs (via ``normalize_doi``). Two-valued entries:
- Record present:  {"fetched_at": <ISO>, "record": {...}}
- Known 404/None:  {"fetched_at": <ISO>, "record": null}

A sentinel ``MISS`` (distinct from ``None``) signals "not in cache".
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Union

from ghostcite.models import CanonicalRecord
from ghostcite.retractions import normalize_doi

# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


class _MissSentinel:
    """Singleton sentinel meaning 'not in cache' — distinct from cached None."""

    _instance: _MissSentinel | None = None

    def __new__(cls) -> _MissSentinel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISS"


MISS: _MissSentinel = _MissSentinel()

# Type alias for callers
CacheResult = Union[CanonicalRecord, None, _MissSentinel]

_DEFAULT_TTL_DAYS = 30


def _default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "ghostcite" / "doi"


# ---------------------------------------------------------------------------
# DoiCache
# ---------------------------------------------------------------------------


class DoiCache:
    """Persistent on-disk cache for CrossRef DOI lookups.

    Parameters
    ----------
    cache_dir:
        Directory for cache files. Defaults to ``~/.cache/ghostcite/doi/``
        (XDG-aware). Created on first write.
    ttl_days:
        How long a cache entry is valid. Defaults to 30 days.
    """

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        ttl_days: int = _DEFAULT_TTL_DAYS,
    ) -> None:
        self._dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        self._ttl = timedelta(days=ttl_days)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, doi: str) -> str:
        """Stable, filesystem-safe key for a DOI."""
        normed = normalize_doi(doi)
        # SHA-256 hex digest avoids any slash/special-char issues in DOIs
        return hashlib.sha256(normed.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, doi: str) -> CacheResult:
        """Return a cached ``CanonicalRecord``, ``None`` (known 404), or ``MISS``.

        Never raises on corruption or missing files — returns ``MISS`` instead.
        """
        key = self._key(doi)
        path = self._path(key)
        if not path.exists():
            return MISS
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Corrupted / unreadable → treat as cache miss
            return MISS

        # Validate envelope
        if not isinstance(data, dict) or "fetched_at" not in data or "record" not in data:
            return MISS

        # TTL check
        try:
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return MISS

        age = datetime.now(timezone.utc) - fetched_at
        if age > self._ttl:
            return MISS

        # Deserialize
        raw = data["record"]
        if raw is None:
            return None  # known 404

        try:
            return CanonicalRecord(
                doi=raw.get("doi"),
                authors=raw.get("authors", []),
                year=raw.get("year"),
                title=raw.get("title"),
                journal=raw.get("journal"),
                retracted=bool(raw.get("retracted", False)),
                eoc=bool(raw.get("eoc", False)),
                low_confidence=bool(raw.get("low_confidence", False)),
            )
        except (TypeError, AttributeError):
            return MISS

    def put(self, doi: str, record: CanonicalRecord | None) -> None:
        """Store a lookup result.

        Parameters
        ----------
        doi:
            The DOI that was looked up (will be normalized internally).
        record:
            The ``CanonicalRecord`` returned by CrossRef, or ``None`` for a 404.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        key = self._key(doi)
        path = self._path(key)

        raw_record = None if record is None else asdict(record)
        envelope = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "record": raw_record,
        }
        payload = json.dumps(envelope, ensure_ascii=False)

        # Atomic write: write to a temp file then rename
        tmp_fd, tmp_name = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, path)
        except Exception:
            # Best-effort cleanup; don't leave .tmp around
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
