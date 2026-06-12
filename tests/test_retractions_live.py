from __future__ import annotations

import os

import pytest

from ghostcite.retractions import RetractionDB, fetch_retractions

pytestmark = pytest.mark.live

_MAILTO = os.environ.get("GHOSTCITE_MAILTO", "ghostcite-ci@example.org")


def test_fetch_then_load_flags_known_retraction(tmp_path):
    dest = tmp_path / "retractions.csv"
    meta = fetch_retractions(_MAILTO, dest)
    assert meta["row_count"] > 1000, "Retraction Watch snapshot suspiciously small"
    header = dest.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
    assert "OriginalPaperDOI" in header
    db = RetractionDB.load(dest)
    # Wakefield 1998 (Lancet) — the canonical retracted paper.
    retracted, _ = db.lookup("10.1016/S0140-6736(97)11096-0")
    assert retracted, "expected Wakefield 1998 to be in the Retraction Watch snapshot"
