"""End-to-end on a real typeset journal PDF (a Systematic Biology article kept in
GHOSTCITE_LIVE_PDF). Skipped unless GHOSTCITE_LIVE=1 and that path is a file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_PDF_ENV = os.environ.get("GHOSTCITE_LIVE_PDF", "")
_PDF = Path(_PDF_ENV) if _PDF_ENV else None  # Path("") would be "." and exist
_SKIP = pytest.mark.skipif(
    os.environ.get("GHOSTCITE_LIVE") != "1" or _PDF is None or not _PDF.is_file(),
    reason="set GHOSTCITE_LIVE=1 and GHOSTCITE_LIVE_PDF=<path to Parham et al. 2012 Syst. Biol. PDF>",
)


@_SKIP
def test_typeset_pdf_reference_list_is_read():
    from ghostcite.parsers import parse_file_bytes

    cites = parse_file_bytes(_PDF.read_bytes(), str(_PDF))
    # Parham et al. 2012 Syst. Biol. "Best practices for justifying fossil
    # calibrations" cites ~150 works, author-year, wrapped over two columns.
    assert 130 <= len(cites) <= 160
    assert all(c.claimed_first_author for c in cites)
    assert {c.claimed_first_author for c in cites} >= {"Abdul", "Alfaro", "Zardoya", "Zuckerkandl"}
