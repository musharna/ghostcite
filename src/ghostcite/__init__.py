"""ghostcite — catch ghost citations by cross-checking author/year against CrossRef."""
from __future__ import annotations

__version__ = "0.2.0"

from ghostcite.api import CheckResult, check_doi, check_text
from ghostcite.models import CanonicalRecord, Finding, Tier
from ghostcite.retractions import RetractionDB, resolve_db

__all__ = [
    "__version__",
    "check_doi",
    "check_text",
    "CheckResult",
    "Finding",
    "Tier",
    "CanonicalRecord",
    "RetractionDB",
    "resolve_db",
]
