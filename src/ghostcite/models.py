from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    OK = "OK"
    AUTHOR = "A"  # claimed first author not the real first author
    YEAR = "B"  # author matches, year differs
    COSMETIC = "C"  # matches only after diacritic/initials fold
    RETRACTION = "R"  # retracted or expression-of-concern
    TITLE = "T"  # DOI resolves to a different paper (identifier hijacking)
    UNRESOLVABLE = "U"  # DOI not found / no-DOI entry unresolved
    SUPPORT = "S"  # (semantic, non-deterministic) cited source does not support the claim
    VENUE = "V"  # cited venue/journal disagrees with CrossRef container-title (warn-only)


@dataclass
class Citation:
    raw: str
    source_line: int | None = None
    doi: str | None = None
    claimed_first_author: str | None = None
    claimed_year: int | None = None
    claimed_title: str | None = None
    claimed_journal: str | None = None


@dataclass
class CanonicalRecord:
    doi: str | None
    authors: list[str] = field(default_factory=list)  # family names, in order
    year: int | None = None
    title: str | None = None
    journal: str | None = None
    retracted: bool = False
    eoc: bool = False  # expression of concern
    low_confidence: bool = False  # from bibliographic search
    is_preprint: bool = False
    has_preprint_relation: bool = False
    abstract: str | None = None  # plain-text abstract, when a source provides one


@dataclass
class PubMedRecord:
    pmid: str
    first_author_surname: str | None = None
    year: int | None = None
    title: str | None = None
    retracted: bool = False
    eoc: bool = False  # expression of concern


@dataclass
class Finding:
    citation: Citation
    tier: Tier
    canonical: CanonicalRecord | None
    message: str
    cross_check: str | None = None
    deterministic: bool = True  # semantic findings set this False


class SemanticVerdict(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


@dataclass
class SupportResult:
    verdict: SemanticVerdict
    rationale: str
    backend: str
