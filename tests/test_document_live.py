"""End-to-end on a real typeset journal PDF (a Systematic Biology article kept in
the user's Downloads). Skipped unless GHOSTCITE_LIVE=1 and the file exists.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_PDF = Path("/mnt/c/Users/a2b32/Downloads/12_Parham.pdf")
_SKIP = pytest.mark.skipif(
    os.environ.get("GHOSTCITE_LIVE") != "1" or not _PDF.exists(),
    reason="set GHOSTCITE_LIVE=1 and keep the sample PDF in place",
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
