"""ghostcite — catch ghost citations by cross-checking author/year against CrossRef."""

from __future__ import annotations

__version__ = "0.4.0"

from ghostcite.api import CheckResult, check_claim_support, check_doi, check_text
from ghostcite.models import (
    CanonicalRecord,
    Finding,
    SemanticVerdict,
    SupportResult,
    Tier,
)
from ghostcite.retractions import RetractionDB, resolve_db

__all__ = [
    "__version__",
    "check_doi",
    "check_text",
    "check_claim_support",
    "CheckResult",
    "Finding",
    "Tier",
    "CanonicalRecord",
    "SemanticVerdict",
    "SupportResult",
    "RetractionDB",
    "resolve_db",
]
