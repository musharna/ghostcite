from __future__ import annotations

import re
import time
from collections.abc import Mapping

_INTERVAL_RE = re.compile(r"(\d+)\s*s")


class _Pacer:
    """Client-side request pacer enforcing a minimum interval between calls.

    The floor is the larger of an explicit ``--max-rps`` ceiling and whatever
    the server advertises via ``x-rate-limit-limit`` / ``x-rate-limit-interval``
    response headers, so the more conservative of the two always wins.
    """

    def __init__(self, max_rps: float | None) -> None:
        if max_rps is not None and max_rps <= 0:
            raise ValueError("max_rps must be positive")
        self._min_interval = 1.0 / max_rps if max_rps else 0.0
        self._last: float | None = None

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """Raise the floor from CrossRef rate headers. Malformed/missing → no-op."""
        raw_limit = headers.get("x-rate-limit-limit")
        raw_interval = headers.get("x-rate-limit-interval")
        if raw_limit is None or raw_interval is None:
            return
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return
        if limit <= 0:
            return
        m = _INTERVAL_RE.fullmatch(raw_interval.strip())
        if not m:
            return
        interval_sec = int(m.group(1))
        self._min_interval = max(self._min_interval, interval_sec / limit)

    def wait(self) -> None:
        """Block until at least ``_min_interval`` has elapsed since the last call."""
        now = time.monotonic()
        if self._last is None:
            # First call: prime the clock, don't sleep.
            self._last = now
            return
        delay = self._min_interval - (now - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()
