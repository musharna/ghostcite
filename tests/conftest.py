"""Shared test fixtures/stubs.

``FakeClient`` lives here (not in ``test_cli``) so other test modules can reuse
it without cross-importing a sibling test module — pytest discovers conftest.py
automatically and it is importable as ``tests.conftest``.
"""

from __future__ import annotations

from ghostcite.models import CanonicalRecord


class FakeClient:
    """Stand-in for CrossRefClient: maps DOI → CanonicalRecord."""

    table = {
        "10.3390/plants13060869": CanonicalRecord(
            doi="10.3390/plants13060869",
            authors=["Chen"],
            year=2024,
            title="Integrated Transcriptome and Proteome Analysis",
        ),
    }

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def lookup_by_doi(self, doi, *, cache=None):
        return self.table.get(doi)

    def doi_resolves(self, doi):
        return None  # no probe in fake — falls back to generic unresolvable message

    def search_bibliographic(self, *a):
        return None
