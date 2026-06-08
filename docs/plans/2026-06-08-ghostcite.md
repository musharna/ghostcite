# ghostcite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ghostcite`, a deterministic no-LLM CLI that catches ghost citations by cross-checking a bibliography's claimed (first-author, year) against CrossRef's canonical record for each DOI, plus flags retractions.

**Architecture:** Lean Python package. Parsers (bibtex/markdown/doi) → `Citation[]`; a CrossRef HTTP client → `CanonicalRecord`; a pure comparison module → `Finding[]`; a renderer (text/json); a CLI that wires them and sets exit codes. Pure-function core (parse, normalize, compare, render) is fully unit-testable with fixtures; only the CrossRef client touches the network.

**Tech Stack:** Python ≥3.9, `httpx` (HTTP), `pytest` + `pytest-httpx` (tests), `hatchling` (build). No LLM/ML deps. Spec: `docs/specs/2026-06-08-ghostcite-design.md`.

---

## File Structure

```
ghostcite/
  __init__.py          # version
  models.py            # Tier enum, Citation, CanonicalRecord, Finding
  compare.py           # normalize_surname(), title_similar(), evaluate() → Finding[]
  crossref.py          # CrossRefClient: lookup_by_doi(), search_bibliographic(), _retraction_flags()
  parsers/
    __init__.py        # sniff(), parse(text, fmt) dispatch
    bibtex.py          # parse_bibtex() — minimal internal parser, 4 fields
    markdown.py        # parse_markdown() — bullet refs
    doi.py             # parse_doi_list() — bare DOIs
  report.py            # render_text(), render_json()
  cli.py               # main(): argparse, orchestration, exit codes
tests/
  test_compare.py  test_bibtex.py  test_markdown.py  test_doi.py
  test_sniff.py  test_crossref.py  test_report.py  test_cli.py
  test_probe_live.py   # real-execution, network (marked)
  fixtures/
pyproject.toml  README.md  LICENSE
```

Exit-code policy lives only in `cli.py`. Network only in `crossref.py`. Everything else is pure.

---

## Task 1: Scaffold package + models

**Files:**

- Create: `pyproject.toml`, `ghostcite/__init__.py`, `ghostcite/models.py`, `tests/test_models.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "ghostcite"
version = "0.1.0"
description = "Catch ghost citations — cross-check a bibliography's claimed author/year against CrossRef"
readme = "README.md"
requires-python = ">=3.9"
license = { text = "MIT" }
authors = [{ name = "Jaret Arnold" }]
keywords = ["citations", "crossref", "bibtex", "research-integrity", "doi", "cli"]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Intended Audience :: Science/Research",
    "Topic :: Scientific/Engineering",
    "Environment :: Console",
]
dependencies = ["httpx>=0.24"]

[project.optional-dependencies]
dev = ["pytest>=7", "pytest-httpx>=0.30"]

[project.scripts]
ghostcite = "ghostcite.cli:main"

[project.urls]
Homepage = "https://github.com/musharna/ghostcite"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ghostcite"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: hits the real CrossRef API (deselect with -m 'not live')"]
```

- [ ] **Step 2: Create `ghostcite/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Write the failing test for models**

`tests/test_models.py`:

```python
from ghostcite.models import Tier, Citation, CanonicalRecord, Finding


def test_tier_values():
    assert Tier.AUTHOR.value == "A"
    assert Tier.YEAR.value == "B"
    assert Tier.COSMETIC.value == "C"
    assert Tier.RETRACTION.value == "R"
    assert Tier.UNRESOLVABLE.value == "U"
    assert Tier.OK.value == "OK"


def test_citation_defaults():
    c = Citation(raw="x")
    assert c.doi is None and c.claimed_first_author is None and c.source_line is None


def test_finding_holds_records():
    c = Citation(raw="x", doi="10.1/a", claimed_first_author="Li", claimed_year=2024)
    rec = CanonicalRecord(doi="10.1/a", authors=["Chen"], year=2024, title="T", journal="J")
    f = Finding(citation=c, tier=Tier.AUTHOR, canonical=rec, message="msg")
    assert f.tier is Tier.AUTHOR and f.canonical.authors == ["Chen"]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostcite.models'`

- [ ] **Step 5: Implement `ghostcite/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    OK = "OK"
    AUTHOR = "A"          # claimed first author not the real first author
    YEAR = "B"            # author matches, year differs
    COSMETIC = "C"        # matches only after diacritic/initials fold
    RETRACTION = "R"      # retracted or expression-of-concern
    UNRESOLVABLE = "U"    # DOI not found / no-DOI entry unresolved


@dataclass
class Citation:
    raw: str
    source_line: int | None = None
    doi: str | None = None
    claimed_first_author: str | None = None
    claimed_year: int | None = None
    claimed_title: str | None = None


@dataclass
class CanonicalRecord:
    doi: str | None
    authors: list[str] = field(default_factory=list)   # family names, in order
    year: int | None = None
    title: str | None = None
    journal: str | None = None
    retracted: bool = False
    eoc: bool = False                                   # expression of concern
    low_confidence: bool = False                        # from bibliographic search


@dataclass
class Finding:
    citation: Citation
    tier: Tier
    canonical: CanonicalRecord | None
    message: str
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -q`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml ghostcite/__init__.py ghostcite/models.py tests/test_models.py
git commit -m "feat: package scaffold + core models"
```

---

## Task 2: Surname normalization (`compare.normalize_surname`)

**Files:**

- Create: `ghostcite/compare.py`, `tests/test_compare.py`

- [ ] **Step 1: Write the failing test**

`tests/test_compare.py`:

```python
from ghostcite.compare import normalize_surname


def test_fold_diacritics():
    assert normalize_surname("Bürger") == normalize_surname("Burger") == "burger"


def test_strip_case_and_punct():
    assert normalize_surname("O'Brien") == "obrien"
    assert normalize_surname("  van der Berg ") == "vanderberg"


def test_empty_and_none():
    assert normalize_surname("") == ""
    assert normalize_surname(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compare.py -q`
Expected: FAIL — `ImportError: cannot import name 'normalize_surname'`

- [ ] **Step 3: Implement `normalize_surname` in `ghostcite/compare.py`**

```python
from __future__ import annotations

import unicodedata

from ghostcite.models import Citation, CanonicalRecord, Finding, Tier


def normalize_surname(name: str | None) -> str:
    """Fold to a comparable key: strip diacritics, lowercase, keep only letters."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in ascii_only.lower() if c.isalpha())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compare.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/compare.py tests/test_compare.py
git commit -m "feat: surname normalization"
```

---

## Task 3: Title similarity helper (`compare.title_similar`)

**Files:**

- Modify: `ghostcite/compare.py`
- Modify: `tests/test_compare.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_compare.py`:

```python
from ghostcite.compare import title_similar


def test_title_similar_true_for_same_title():
    assert title_similar("Integrated Transcriptome and Proteome Analysis",
                         "Integrated transcriptome and proteome analysis reveals...") is True


def test_title_similar_false_for_different_papers():
    assert title_similar("Auxin response factors in lateral roots",
                         "A genome resource for Neocamarosporium betae") is False


def test_title_similar_handles_missing():
    assert title_similar(None, "x") is False
    assert title_similar("x", None) is False
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_compare.py -k title -q`
Expected: FAIL — `cannot import name 'title_similar'`

- [ ] **Step 3: Implement `title_similar`**

Add to `ghostcite/compare.py`:

```python
def _title_tokens(title: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    words = "".join(c if c.isalnum() else " " for c in ascii_only).split()
    stop = {"the", "a", "an", "of", "and", "in", "for", "on", "to", "with", "by", "reveals"}
    return {w for w in words if len(w) > 2 and w not in stop}


def title_similar(a: str | None, b: str | None, threshold: float = 0.4) -> bool:
    """Jaccard token overlap >= threshold. Used to tell wrong-author from wrong-DOI."""
    if not a or not b:
        return False
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return (inter / union) >= threshold
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_compare.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/compare.py tests/test_compare.py
git commit -m "feat: title similarity helper"
```

---

## Task 4: Core comparison (`compare.evaluate`)

**Files:**

- Modify: `ghostcite/compare.py`
- Modify: `tests/test_compare.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_compare.py`:

```python
from ghostcite.compare import evaluate
from ghostcite.models import Citation, CanonicalRecord, Tier


def _cit(**kw):
    base = dict(raw="r", doi="10.1/a", claimed_first_author="Li",
                claimed_year=2024, claimed_title="Cell Wall Activity in Phelipanche")
    base.update(kw)
    return Citation(**base)


def _rec(**kw):
    base = dict(doi="10.1/a", authors=["Chen", "Zhang"], year=2024,
                title="Cell Wall Activity Affects Phelipanche", journal="Plants")
    base.update(kw)
    return CanonicalRecord(**base)


def test_ok_when_first_author_and_year_match():
    c = _cit(claimed_first_author="Chen")
    assert evaluate(c, _rec()) == []  # no findings


def test_author_mismatch_is_tier_a():
    findings = evaluate(_cit(claimed_first_author="Li"), _rec())
    assert [f.tier for f in findings] == [Tier.AUTHOR]
    assert "Chen" in findings[0].message


def test_wrong_doi_annotation_when_title_diverges():
    c = _cit(claimed_first_author="Clarke", claimed_title="Arabidopsis immunity to broomrape")
    rec = _rec(authors=["Vaghefi"], title="A genome resource for Neocamarosporium betae")
    findings = evaluate(c, rec)
    assert findings[0].tier is Tier.AUTHOR
    assert "possibly wrong DOI" in findings[0].message


def test_year_mismatch_is_tier_b_when_author_ok():
    c = _cit(claimed_first_author="Chen", claimed_year=2019)
    findings = evaluate(c, _rec(year=2024))
    assert [f.tier for f in findings] == [Tier.YEAR]
    assert "2024" in findings[0].message


def test_diacritic_only_is_tier_c():
    c = _cit(claimed_first_author="Burger", claimed_year=2025, claimed_title="x")
    rec = _rec(authors=["Bürger"], year=2025, title="x")
    findings = evaluate(c, rec)
    assert [f.tier for f in findings] == [Tier.COSMETIC]


def test_retraction_is_tier_r():
    c = _cit(claimed_first_author="Chen")
    findings = evaluate(c, _rec(retracted=True))
    assert Tier.RETRACTION in [f.tier for f in findings]


def test_unresolvable_when_no_canonical():
    findings = evaluate(_cit(), None)
    assert [f.tier for f in findings] == [Tier.UNRESOLVABLE]


def test_no_claimed_author_skips_author_check():
    # DOI-list mode: nothing claimed → only retraction/unresolvable can fire
    c = Citation(raw="r", doi="10.1/a")
    assert evaluate(c, _rec()) == []
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_compare.py -k evaluate -q`
Expected: FAIL — `cannot import name 'evaluate'`

- [ ] **Step 3: Implement `evaluate`**

Add to `ghostcite/compare.py`:

```python
def evaluate(citation: Citation, canonical: CanonicalRecord | None) -> list[Finding]:
    """Compare a claimed citation against the canonical record. Empty list = OK."""
    if canonical is None:
        return [Finding(citation, Tier.UNRESOLVABLE, None,
                        "DOI not found / unresolvable")]

    findings: list[Finding] = []

    # Retraction is orthogonal — fires regardless of author/year.
    if canonical.retracted:
        findings.append(Finding(citation, Tier.RETRACTION, canonical, "RETRACTED per CrossRef"))
    elif canonical.eoc:
        findings.append(Finding(citation, Tier.RETRACTION, canonical,
                                "Expression of concern per CrossRef"))

    # Author/year only when the input actually claimed an author (not DOI-list mode).
    if citation.claimed_first_author:
        findings.extend(_author_year(citation, canonical))

    return findings


def _author_year(citation: Citation, canonical: CanonicalRecord) -> list[Finding]:
    claimed_raw = citation.claimed_first_author.strip()
    claimed = normalize_surname(claimed_raw)
    families_raw = canonical.authors or []
    first_raw = families_raw[0] if families_raw else ""
    first = normalize_surname(first_raw)
    all_norm = [normalize_surname(a) for a in families_raw]

    conf = " (low-confidence match)" if canonical.low_confidence else ""

    if claimed == first:
        # First-author matches after normalization.
        if claimed_raw.lower().replace(" ", "") != first_raw.lower().replace(" ", ""):
            return [Finding(citation, Tier.COSMETIC, canonical,
                            f'diacritic/spelling: CrossRef has "{first_raw}"{conf}')]
        # True match → check year.
        if citation.claimed_year and canonical.year and citation.claimed_year != canonical.year:
            return [Finding(citation, Tier.YEAR, canonical,
                            f"CrossRef year is {canonical.year}{conf}")]
        return []

    # First-author mismatch.
    if claimed in all_norm:
        idx = all_norm.index(claimed)
        return [Finding(citation, Tier.AUTHOR, canonical,
                        f"claimed first author is actually author #{idx + 1}; "
                        f"CrossRef first author is {first_raw}{conf}")]

    # Not in author list at all — wrong author, or wrong DOI entirely.
    if not title_similar(citation.claimed_title, canonical.title):
        return [Finding(citation, Tier.AUTHOR, canonical,
                        f"DOI resolves to {first_raw} ({canonical.year}) — "
                        f"possibly wrong DOI{conf}")]
    return [Finding(citation, Tier.AUTHOR, canonical,
                    f"CrossRef first author is {first_raw}{conf}")]
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_compare.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/compare.py tests/test_compare.py
git commit -m "feat: core citation comparison + severity tiers"
```

---

## Task 5: BibTeX parser (`parsers/bibtex.py`)

**Files:**

- Create: `ghostcite/parsers/__init__.py` (empty for now), `ghostcite/parsers/bibtex.py`, `tests/test_bibtex.py`

- [ ] **Step 1: Write failing test**

`tests/test_bibtex.py`:

```python
from ghostcite.parsers.bibtex import parse_bibtex

SAMPLE = r"""
@article{chen2024,
  author  = {Chen, Min and Zhang, Lei and Yao, Z.},
  title   = {Integrated Transcriptome and Proteome Analysis},
  journal = {Plants},
  year    = {2024},
  doi     = {10.3390/plants13060869},
}

@article{nodoi2021,
  author = {Ngou, B.},
  title  = {Mutual potentiation of plant immunity},
  year   = {2021},
}
"""


def test_parses_fields():
    cites = parse_bibtex(SAMPLE)
    assert len(cites) == 2
    c = cites[0]
    assert c.claimed_first_author == "Chen"
    assert c.claimed_year == 2024
    assert c.doi == "10.3390/plants13060869"
    assert "Integrated Transcriptome" in c.claimed_title


def test_entry_without_doi_has_none():
    c = parse_bibtex(SAMPLE)[1]
    assert c.doi is None
    assert c.claimed_first_author == "Ngou"
    assert c.claimed_year == 2021
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_bibtex.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostcite.parsers'`

- [ ] **Step 3: Create `ghostcite/parsers/__init__.py`** (leave empty for this task)

```python

```

- [ ] **Step 4: Implement `ghostcite/parsers/bibtex.py`**

```python
from __future__ import annotations

import re

from ghostcite.models import Citation

_ENTRY = re.compile(r"@\w+\s*\{[^,]*,(?P<body>.*?)\n\}", re.DOTALL)
_FIELD = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.MULTILINE | re.DOTALL)
_DOI_CLEAN = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)\s*", re.IGNORECASE)


def _first_author_surname(author_field: str) -> str | None:
    # BibTeX authors are separated by " and ". Take the first.
    first = re.split(r"\s+and\s+", author_field.strip(), maxsplit=1)[0].strip()
    if not first:
        return None
    if "," in first:                 # "Surname, Given"
        return first.split(",", 1)[0].strip()
    parts = first.split()            # "Given Surname"
    return parts[-1].strip() if parts else None


def _normalize_doi(raw: str) -> str:
    return _DOI_CLEAN.sub("", raw.strip()).strip().lower()


def parse_bibtex(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for m in _ENTRY.finditer(text):
        body = m.group("body")
        line_no = text[: m.start()].count("\n") + 1
        fields = {k.lower(): " ".join(v.split()) for k, v in _FIELD.findall(body)}
        year = None
        if fields.get("year"):
            ym = re.search(r"\d{4}", fields["year"])
            year = int(ym.group()) if ym else None
        cites.append(Citation(
            raw=m.group(0).strip().splitlines()[0],
            source_line=line_no,
            doi=_normalize_doi(fields["doi"]) if fields.get("doi") else None,
            claimed_first_author=_first_author_surname(fields.get("author", "")) or None,
            claimed_year=year,
            claimed_title=fields.get("title") or None,
        ))
    return cites
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_bibtex.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add ghostcite/parsers/__init__.py ghostcite/parsers/bibtex.py tests/test_bibtex.py
git commit -m "feat: minimal internal BibTeX parser"
```

---

## Task 6: Markdown reference parser (`parsers/markdown.py`)

**Files:**

- Create: `ghostcite/parsers/markdown.py`, `tests/test_markdown.py`

- [ ] **Step 1: Write failing test**

`tests/test_markdown.py`:

```python
from ghostcite.parsers.markdown import parse_markdown

SAMPLE = """\
# References

- **Chen M, Zhang L, Yao Z (2024).** Integrated transcriptome analysis. Plants 13(6):869. https://doi.org/10.3390/plants13060869
- **Ngou B et al. (2021).** Mutual potentiation of plant immunity. Nature.
- not a reference line
"""


def test_parses_bullet_refs():
    cites = parse_markdown(SAMPLE)
    assert len(cites) == 2
    assert cites[0].claimed_first_author == "Chen"
    assert cites[0].claimed_year == 2024
    assert cites[0].doi == "10.3390/plants13060869"


def test_ref_without_doi():
    c = parse_markdown(SAMPLE)[1]
    assert c.claimed_first_author == "Ngou"
    assert c.claimed_year == 2021
    assert c.doi is None
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_markdown.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `ghostcite/parsers/markdown.py`**

```python
from __future__ import annotations

import re

from ghostcite.models import Citation

_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_YEAR = re.compile(r"\((\d{4})[a-z]?\)")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s)>\"]+)", re.IGNORECASE)
# Leading author surname: first capitalized word(s) before an initial or comma.
_FIRST_AUTHOR = re.compile(r"^\**\s*([A-Z][A-Za-zÀ-ÿ'’-]+)")


def parse_markdown(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _BULLET.match(line)
        if not m:
            continue
        content = m.group(1)
        # Require a year to count it as a reference (filters non-ref bullets).
        ym = _YEAR.search(content)
        if not ym:
            continue
        author_m = _FIRST_AUTHOR.match(content)
        doi_m = _DOI.search(content)
        doi = doi_m.group(1).rstrip(".").lower() if doi_m else None
        cites.append(Citation(
            raw=content.strip(),
            source_line=i,
            doi=doi,
            claimed_first_author=author_m.group(1) if author_m else None,
            claimed_year=int(ym.group(1)),
            claimed_title=None,   # title hard to delimit reliably; left None in v1
        ))
    return cites
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_markdown.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/parsers/markdown.py tests/test_markdown.py
git commit -m "feat: markdown reference-list parser"
```

---

## Task 7: DOI-list parser (`parsers/doi.py`)

**Files:**

- Create: `ghostcite/parsers/doi.py`, `tests/test_doi.py`

- [ ] **Step 1: Write failing test**

`tests/test_doi.py`:

```python
from ghostcite.parsers.doi import parse_doi_list

SAMPLE = """\
10.3390/plants13060869
doi:10.1038/s41586-024-00001
https://doi.org/10.1093/bib/bbx115
# a comment line
not-a-doi
"""


def test_extracts_dois_only():
    cites = parse_doi_list(SAMPLE)
    dois = [c.doi for c in cites]
    assert dois == ["10.3390/plants13060869", "10.1038/s41586-024-00001", "10.1093/bib/bbx115"]
    assert all(c.claimed_first_author is None for c in cites)
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_doi.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `ghostcite/parsers/doi.py`**

```python
from __future__ import annotations

import re

from ghostcite.models import Citation

_DOI = re.compile(r"(10\.\d{4,9}/[^\s)>\"]+)", re.IGNORECASE)


def parse_doi_list(text: str) -> list[Citation]:
    cites: list[Citation] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        m = _DOI.search(line)
        if not m:
            continue
        cites.append(Citation(raw=line.strip(), source_line=i,
                              doi=m.group(1).rstrip(".").lower()))
    return cites
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_doi.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/parsers/doi.py tests/test_doi.py
git commit -m "feat: bare DOI-list parser"
```

---

## Task 8: Format sniffing + dispatch (`parsers.sniff`, `parsers.parse`)

**Files:**

- Modify: `ghostcite/parsers/__init__.py`
- Create: `tests/test_sniff.py`

- [ ] **Step 1: Write failing test**

`tests/test_sniff.py`:

```python
from ghostcite.parsers import sniff, parse

BIB = "@article{k,\n author={Li, X},\n year={2024},\n doi={10.1/a}\n}"
MD = "- **Chen M (2024).** Title. https://doi.org/10.1/a"
DOIS = "10.3390/plants13060869\n10.1038/s41586-024-00001"


def test_sniff():
    assert sniff(BIB) == "bibtex"
    assert sniff(MD) == "markdown"
    assert sniff(DOIS) == "doi"


def test_parse_dispatches_by_sniff():
    assert parse(BIB)[0].claimed_first_author == "Li"
    assert parse(MD)[0].claimed_first_author == "Chen"
    assert parse(DOIS)[0].doi == "10.3390/plants13060869"


def test_parse_honors_explicit_format():
    # Force DOI mode on markdown → only the DOI is extracted, no author.
    out = parse(MD, fmt="doi")
    assert out[0].claimed_first_author is None and out[0].doi == "10.1/a"
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_sniff.py -q`
Expected: FAIL — `cannot import name 'sniff'`

- [ ] **Step 3: Implement dispatch in `ghostcite/parsers/__init__.py`**

```python
from __future__ import annotations

import re

from ghostcite.models import Citation
from ghostcite.parsers.bibtex import parse_bibtex
from ghostcite.parsers.markdown import parse_markdown
from ghostcite.parsers.doi import parse_doi_list

_DOI_LINE = re.compile(r"^\s*(?:doi:|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+\s*$",
                       re.IGNORECASE)


def sniff(text: str) -> str:
    """Return 'bibtex' | 'markdown' | 'doi' from the content shape."""
    if re.search(r"@\w+\s*\{", text):
        return "bibtex"
    nonblank = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if nonblank and all(_DOI_LINE.match(ln) for ln in nonblank):
        return "doi"
    return "markdown"


def parse(text: str, fmt: str = "auto") -> list[Citation]:
    if fmt == "auto":
        fmt = sniff(text)
    if fmt == "bibtex":
        return parse_bibtex(text)
    if fmt == "doi":
        return parse_doi_list(text)
    if fmt == "markdown":
        return parse_markdown(text)
    raise ValueError(f"unknown format: {fmt}")
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_sniff.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/parsers/__init__.py tests/test_sniff.py
git commit -m "feat: format sniffing + parser dispatch"
```

---

## Task 9: CrossRef client — DOI lookup + retraction (`crossref.py`)

**Files:**

- Create: `ghostcite/crossref.py`, `tests/test_crossref.py`

**Note on retraction fields:** CrossRef exposes retraction/EoC via `message["relation"]` (keys like `is-retracted-by`) and/or `message["update-to"]` items whose `type` ∈ {`retraction`, `expression_of_concern`}. The parser below checks both. The live probe in Task 13 validates against a real retracted DOI; if the field shape differs, fix `_retraction_flags` then.

- [ ] **Step 1: Write failing test (mocked HTTP)**

`tests/test_crossref.py`:

```python
import httpx
import pytest

from ghostcite.crossref import CrossRefClient, _retraction_flags

WORK = {
    "message": {
        "DOI": "10.3390/plants13060869",
        "author": [{"family": "Chen", "given": "Min"}, {"family": "Zhang"}],
        "title": ["Integrated Transcriptome and Proteome Analysis"],
        "container-title": ["Plants"],
        "published": {"date-parts": [[2024, 3, 1]]},
    }
}


def test_lookup_by_doi_parses_record(httpx_mock):
    httpx_mock.add_response(url="https://api.crossref.org/works/10.3390/plants13060869",
                            json=WORK)
    with CrossRefClient() as c:
        rec = c.lookup_by_doi("10.3390/plants13060869")
    assert rec.authors[0] == "Chen"
    assert rec.year == 2024
    assert rec.journal == "Plants"
    assert rec.retracted is False


def test_lookup_returns_none_on_404(httpx_mock):
    httpx_mock.add_response(status_code=404)
    with CrossRefClient() as c:
        assert c.lookup_by_doi("10.0/missing") is None


def test_retraction_flags_from_relation():
    msg = {"relation": {"is-retracted-by": [{"id": "10.1/notice"}]}}
    assert _retraction_flags(msg) == (True, False)


def test_eoc_flag_from_update_to():
    msg = {"update-to": [{"type": "expression_of_concern", "DOI": "10.1/x"}]}
    assert _retraction_flags(msg) == (False, True)
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_crossref.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostcite.crossref'`

- [ ] **Step 3: Implement `ghostcite/crossref.py`**

```python
from __future__ import annotations

import httpx

from ghostcite import __version__
from ghostcite.models import CanonicalRecord

_BASE = "https://api.crossref.org"
_UA = f"ghostcite/{__version__} (https://github.com/musharna/ghostcite)"


def _retraction_flags(message: dict) -> tuple[bool, bool]:
    """Return (retracted, expression_of_concern) from a CrossRef work message."""
    retracted = eoc = False
    relation = message.get("relation") or {}
    for key in relation:
        k = key.lower()
        if "retract" in k:
            retracted = True
        if "concern" in k:
            eoc = True
    for upd in message.get("update-to") or []:
        t = str(upd.get("type", "")).lower()
        if "retract" in t:
            retracted = True
        if "concern" in t:
            eoc = True
    return retracted, eoc


def _year(message: dict) -> int | None:
    for key in ("published", "published-print", "published-online", "issued"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def _record_from_message(message: dict, low_confidence: bool = False) -> CanonicalRecord:
    retracted, eoc = _retraction_flags(message)
    authors = [a.get("family", "").strip() for a in message.get("author") or []
               if a.get("family")]
    title = (message.get("title") or [None])[0]
    journal = (message.get("container-title") or [None])[0]
    return CanonicalRecord(
        doi=(message.get("DOI") or "").lower() or None,
        authors=authors, year=_year(message), title=title, journal=journal,
        retracted=retracted, eoc=eoc, low_confidence=low_confidence,
    )


class CrossRefClient:
    def __init__(self, timeout: float = 20.0):
        self._client = httpx.Client(
            timeout=timeout, headers={"User-Agent": _UA},
            follow_redirects=True,
        )

    def __enter__(self) -> "CrossRefClient":
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def lookup_by_doi(self, doi: str) -> CanonicalRecord | None:
        r = self._client.get(f"{_BASE}/works/{doi}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _record_from_message(r.json()["message"])
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_crossref.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/crossref.py tests/test_crossref.py
git commit -m "feat: CrossRef DOI lookup + retraction/EoC detection"
```

---

## Task 10: CrossRef bibliographic search for no-DOI entries

**Files:**

- Modify: `ghostcite/crossref.py`
- Modify: `tests/test_crossref.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_crossref.py`:

```python
SEARCH = {"message": {"items": [{
    "DOI": "10.1038/s41586-021-00001",
    "author": [{"family": "Ngou"}],
    "title": ["Mutual potentiation of plant immunity"],
    "container-title": ["Nature"],
    "published": {"date-parts": [[2021]]},
}]}}


def test_search_bibliographic_marks_low_confidence(httpx_mock):
    httpx_mock.add_response(url__startswith="https://api.crossref.org/works?", json=SEARCH)
    with CrossRefClient() as c:
        rec = c.search_bibliographic("Ngou", 2021, "Mutual potentiation of plant immunity")
    assert rec.doi == "10.1038/s41586-021-00001"
    assert rec.low_confidence is True


def test_search_returns_none_on_empty(httpx_mock):
    httpx_mock.add_response(url__startswith="https://api.crossref.org/works?",
                            json={"message": {"items": []}})
    with CrossRefClient() as c:
        assert c.search_bibliographic("Nobody", 1999, "no such paper") is None
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_crossref.py -k search -q`
Expected: FAIL — `AttributeError: 'CrossRefClient' object has no attribute 'search_bibliographic'`

- [ ] **Step 3: Add `search_bibliographic` to `CrossRefClient`**

```python
    def search_bibliographic(self, author: str | None, year: int | None,
                             title: str | None) -> CanonicalRecord | None:
        query = " ".join(str(x) for x in (author, year, title) if x).strip()
        if not query:
            return None
        r = self._client.get(f"{_BASE}/works",
                             params={"query.bibliographic": query, "rows": 1})
        r.raise_for_status()
        items = r.json().get("message", {}).get("items") or []
        if not items:
            return None
        return _record_from_message(items[0], low_confidence=True)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_crossref.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/crossref.py tests/test_crossref.py
git commit -m "feat: CrossRef bibliographic search for no-DOI entries"
```

---

## Task 11: Reporters (`report.py`)

**Files:**

- Create: `ghostcite/report.py`, `tests/test_report.py`

- [ ] **Step 1: Write failing test**

`tests/test_report.py`:

```python
import json

from ghostcite.models import Citation, CanonicalRecord, Finding, Tier
from ghostcite.report import render_text, render_json


def _finding():
    c = Citation(raw="Li X (2024)", source_line=227, doi="10.3390/cimb46080535",
                 claimed_first_author="Hsu", claimed_year=2024)
    rec = CanonicalRecord(doi="10.3390/cimb46080535", authors=["Gerakari"], year=2024)
    return Finding(c, Tier.AUTHOR, rec, "CrossRef first author is Gerakari")


def test_text_lists_findings_and_counts():
    out = render_text([_finding()], total=46, with_doi=45)
    assert "A" in out and "Gerakari" in out and "10.3390/cimb46080535" in out
    assert "46" in out


def test_text_quiet_when_clean():
    out = render_text([], total=10, with_doi=10)
    assert "0 findings" in out or "clean" in out.lower()


def test_json_is_machine_readable():
    out = render_json([_finding()], total=46, with_doi=45)
    data = json.loads(out)
    assert data["summary"]["total"] == 46
    assert data["findings"][0]["tier"] == "A"
    assert data["findings"][0]["doi"] == "10.3390/cimb46080535"
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `ghostcite/report.py`**

```python
from __future__ import annotations

import json

from ghostcite.models import Finding, Tier

_GLYPH = {Tier.AUTHOR: "✗ A", Tier.YEAR: "✗ B", Tier.COSMETIC: "· C",
          Tier.RETRACTION: "⚠ R", Tier.UNRESOLVABLE: "? U"}


def render_text(findings: list[Finding], total: int, with_doi: int) -> str:
    lines = [f"ghostcite: {total} entries, {with_doi} with DOIs"]
    if not findings:
        lines.append("  0 findings — clean")
        return "\n".join(lines)
    for f in sorted(findings, key=lambda x: (x.citation.source_line or 0)):
        loc = f"L{f.citation.source_line}" if f.citation.source_line else "—"
        who = f.citation.claimed_first_author or f.citation.doi or "?"
        yr = f"({f.citation.claimed_year})" if f.citation.claimed_year else ""
        doi = f"  [{f.citation.doi}]" if f.citation.doi else ""
        lines.append(f"  {_GLYPH[f.tier]}  {loc}  {who} {yr}  →  {f.message}{doi}")
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.tier.value] = counts.get(f.tier.value, 0) + 1
    summary = " · ".join(f"{n} {t}" for t, n in sorted(counts.items()))
    lines.append(f"  {summary}")
    return "\n".join(lines)


def render_json(findings: list[Finding], total: int, with_doi: int) -> str:
    payload = {
        "summary": {"total": total, "with_doi": with_doi, "findings": len(findings)},
        "findings": [
            {
                "tier": f.tier.value,
                "line": f.citation.source_line,
                "claimed_author": f.citation.claimed_first_author,
                "claimed_year": f.citation.claimed_year,
                "doi": f.citation.doi,
                "message": f.message,
                "canonical_authors": f.canonical.authors if f.canonical else None,
                "canonical_year": f.canonical.year if f.canonical else None,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_report.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ghostcite/report.py tests/test_report.py
git commit -m "feat: text + json reporters"
```

---

## Task 12: CLI orchestration + exit codes (`cli.py`)

**Files:**

- Create: `ghostcite/cli.py`, `tests/test_cli.py`

**Exit policy:** `0` clean (no findings at/above threshold), `1` findings present, `2` tool error. `--fail-on` (default `author,year,retraction`) selects which tiers count toward exit 1. Tier `C`/`U` never force exit 1.

- [ ] **Step 1: Write failing test (CrossRef monkeypatched — no network)**

`tests/test_cli.py`:

```python
import pytest

from ghostcite import cli
from ghostcite.models import CanonicalRecord


class FakeClient:
    """Stand-in for CrossRefClient: maps DOI → CanonicalRecord."""
    table = {
        "10.3390/plants13060869": CanonicalRecord(
            doi="10.3390/plants13060869", authors=["Chen"], year=2024,
            title="Integrated Transcriptome and Proteome Analysis"),
    }

    def __enter__(self): return self
    def __exit__(self, *a): return None
    def lookup_by_doi(self, doi): return self.table.get(doi)
    def search_bibliographic(self, *a): return None


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(cli, "CrossRefClient", FakeClient)


def _write(tmp_path, text):
    p = tmp_path / "refs.bib"
    p.write_text(text)
    return str(p)


def test_exit_1_on_author_mismatch(tmp_path, capsys):
    f = _write(tmp_path, "@article{k, author={Li, X}, year={2024}, "
                         "title={Integrated Transcriptome and Proteome Analysis}, "
                         "doi={10.3390/plants13060869}}")
    code = cli.main([f])
    assert code == 1
    assert "Chen" in capsys.readouterr().out


def test_exit_0_when_author_matches(tmp_path, capsys):
    f = _write(tmp_path, "@article{k, author={Chen, M}, year={2024}, "
                         "title={Integrated Transcriptome and Proteome Analysis}, "
                         "doi={10.3390/plants13060869}}")
    assert cli.main([f]) == 0


def test_dry_run_makes_no_lookups(tmp_path, capsys):
    f = _write(tmp_path, "@article{k, author={Li, X}, year={2024}, doi={10.3390/plants13060869}}")
    assert cli.main([f, "--dry-run"]) == 0
    assert "would check" in capsys.readouterr().out.lower()


def test_json_output(tmp_path, capsys):
    f = _write(tmp_path, "@article{k, author={Li, X}, year={2024}, "
                         "title={Integrated Transcriptome and Proteome Analysis}, "
                         "doi={10.3390/plants13060869}}")
    cli.main([f, "--json"])
    assert '"tier": "A"' in capsys.readouterr().out


def test_fail_on_none_forces_exit_0(tmp_path):
    f = _write(tmp_path, "@article{k, author={Li, X}, year={2024}, "
                         "title={Integrated Transcriptome and Proteome Analysis}, "
                         "doi={10.3390/plants13060869}}")
    assert cli.main([f, "--fail-on", "none"]) == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostcite.cli'`

- [ ] **Step 3: Implement `ghostcite/cli.py`**

```python
from __future__ import annotations

import argparse
import sys

from ghostcite.compare import evaluate
from ghostcite.crossref import CrossRefClient
from ghostcite.models import Finding, Tier
from ghostcite.parsers import parse
from ghostcite.report import render_json, render_text

_TIER_BY_NAME = {"author": Tier.AUTHOR, "year": Tier.YEAR, "retraction": Tier.RETRACTION}


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="ghostcite",
        description="Catch ghost citations: cross-check claimed author/year against CrossRef.")
    p.add_argument("file", help="bibliography file (.bib, markdown refs, or DOI list)")
    p.add_argument("--format", choices=["auto", "bibtex", "markdown", "doi"], default="auto")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--dry-run", action="store_true", help="parse + count only, no network")
    p.add_argument("--fail-on", default="author,year,retraction",
                   help="comma list of tiers that cause exit 1, or 'none' "
                        "(choices: author,year,retraction,none)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        text = open(args.file, encoding="utf-8").read()
    except OSError as e:
        print(f"ghostcite: cannot read {args.file}: {e}", file=sys.stderr)
        return 2

    try:
        citations = parse(text, fmt=args.format)
    except ValueError as e:
        print(f"ghostcite: {e}", file=sys.stderr)
        return 2

    with_doi = sum(1 for c in citations if c.doi)
    if args.dry_run:
        print(f"ghostcite: would check {len(citations)} entries "
              f"({with_doi} via DOI, {len(citations) - with_doi} via search).")
        return 0

    findings: list[Finding] = []
    try:
        with CrossRefClient() as client:
            for c in citations:
                if c.doi:
                    rec = client.lookup_by_doi(c.doi)
                else:
                    rec = client.search_bibliographic(
                        c.claimed_first_author, c.claimed_year, c.claimed_title)
                findings.extend(evaluate(c, rec))
    except Exception as e:  # fail-loud: surface, keep partial findings
        print(f"ghostcite: CrossRef error: {e}", file=sys.stderr)
        out = render_json(findings, len(citations), with_doi) if args.json \
            else render_text(findings, len(citations), with_doi)
        print(out)
        return 2

    out = render_json(findings, len(citations), with_doi) if args.json \
        else render_text(findings, len(citations), with_doi)
    print(out)

    if args.fail_on.strip().lower() == "none":
        return 0
    fail_tiers = {_TIER_BY_NAME[n.strip()] for n in args.fail_on.split(",")
                  if n.strip() in _TIER_BY_NAME}
    return 1 if any(f.tier in fail_tiers for f in findings) else 0
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full unit suite**

Run: `python -m pytest -q -m "not live"`
Expected: PASS (all tasks 1–12)

- [ ] **Step 6: Commit**

```bash
git add ghostcite/cli.py tests/test_cli.py
git commit -m "feat: CLI orchestration + exit-code policy"
```

---

## Task 13: Real-execution probes (live CrossRef)

**Files:**

- Create: `tests/test_probe_live.py`

These hit the real API and are marked `live` (run explicitly; excluded from the default suite). They are the real-execution check required by the testing doctrine — synthetic mocks alone don't prove the CrossRef schema assumptions.

- [ ] **Step 1: Write the live probes**

`tests/test_probe_live.py`:

```python
import pytest

from ghostcite.compare import evaluate
from ghostcite.crossref import CrossRefClient
from ghostcite.models import Citation, Tier

pytestmark = pytest.mark.live


def test_known_ghost_li_should_be_chen():
    # From the 2026-04-29 Phelipanche audit: cited "Li 2024", DOI is actually Chen et al.
    c = Citation(raw="Li X (2024)", doi="10.3390/plants13060869",
                 claimed_first_author="Li", claimed_year=2024,
                 claimed_title="Cell wall activity in Phelipanche")
    with CrossRefClient() as client:
        rec = client.lookup_by_doi(c.doi)
    assert rec is not None and rec.authors, "CrossRef returned no record/authors"
    findings = evaluate(c, rec)
    assert any(f.tier is Tier.AUTHOR for f in findings)
    assert any("hen" in (f.message or "") for f in findings)  # Chen


def test_correct_citation_is_clean():
    c = Citation(raw="Chen M (2024)", doi="10.3390/plants13060869",
                 claimed_first_author="Chen", claimed_year=2024)
    with CrossRefClient() as client:
        rec = client.lookup_by_doi(c.doi)
    assert evaluate(c, rec) == []


def test_known_retracted_doi_flags_R():
    # A well-known retracted paper (Wakefield 1998, Lancet). Verify CrossRef marks it.
    c = Citation(raw="x", doi="10.1016/s0140-6736(97)11096-0",
                 claimed_first_author="Wakefield", claimed_year=1998)
    with CrossRefClient() as client:
        rec = client.lookup_by_doi(c.doi)
    assert rec is not None
    findings = evaluate(c, rec)
    assert any(f.tier is Tier.RETRACTION for f in findings), \
        "expected retraction flag; if this fails, inspect rec + fix _retraction_flags"
```

- [ ] **Step 2: Run the live probes**

Run: `python -m pytest tests/test_probe_live.py -m live -q`
Expected: PASS (3 passed).

**If `test_known_retracted_doi_flags_R` fails:** the CrossRef retraction field shape differs from the assumption. Print the raw record (`python -c "import httpx,json; print(json.dumps(httpx.get('https://api.crossref.org/works/10.1016/s0140-6736(97)11096-0', headers={'User-Agent':'ghostcite-dev'}).json()['message'].get('relation'), indent=2))"`), then adjust `_retraction_flags` in `crossref.py` and its unit test in Task 9 to match, and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_probe_live.py
git commit -m "test: live CrossRef real-execution probes (ghost + retraction)"
```

---

## Task 14: README, LICENSE, scrub gate, publish

**Files:**

- Create: `README.md`, `LICENSE`, `.gitignore`

- [ ] **Step 1: Write `LICENSE`** (MIT, `Copyright (c) 2026 Jaret Arnold` — copy the standard MIT text used in the other repos).

- [ ] **Step 2: Write `README.md`** covering: one-line pitch ("catch ghost citations — right DOI, wrong author"), the problem (LLM-fabricated/mis-attributed references), `pip install ghostcite`, usage (`ghostcite refs.bib`, `--json`, `--dry-run`, `--fail-on`), input formats (bib/markdown/doi auto-detect), the severity tiers table (A/B/C/R/U), exit codes, "how it works" (CrossRef cross-check, no LLM), and a CI/pre-submission example. Include a real example using the Li→Chen case.

- [ ] **Step 3: Write `.gitignore`** (`__pycache__/`, `*.pyc`, `.pytest_cache/`, `dist/`, `build/`, `*.egg-info/`, `.venv/`).

- [ ] **Step 4: Scrub gate — verify clean before any push**

Run:

```bash
cd ~/ghostcite
grep -rIE 'mjarnold1998@gmail|/home/mjarnold|/mnt/c/Users|6532713|ZOTERO|api[_-]?key|\.claude' \
  --exclude-dir=.git --exclude-dir=docs . || echo "CLEAN"
```

Expected: `CLEAN` (the User-Agent uses the repo URL, no email). If anything prints, remove it before continuing.

- [ ] **Step 5: Full suite (offline) green + build sanity**

Run: `python -m pytest -q -m "not live"` → all pass.
Run: `python -m pip install -e . && ghostcite --help` → prints usage.

- [ ] **Step 6: Commit**

```bash
git add README.md LICENSE .gitignore
git commit -m "docs: README + LICENSE + gitignore"
```

- [ ] **Step 7: Create the public repo + push** (after user confirms it's ready to go public)

```bash
git branch -M main
gh repo create musharna/ghostcite --public --source=. --remote=origin --push \
  --description "Catch ghost citations — cross-check a bibliography's claimed author/year against CrossRef. No LLM."
gh repo edit musharna/ghostcite --add-topic citations --add-topic crossref \
  --add-topic bibtex --add-topic research-integrity --add-topic doi --add-topic cli --add-topic python
```

- [ ] **Step 8: Post-publish follow-up (separate task, not blocking)**

Repoint CLAUDE.md line 30 ("Reusable bib auditor: `/tmp/audit_refs_11.py`") to the installed `ghostcite`; optionally wire into the "triple-check every citation" rule. Clean up the orphaned `~/.claude/envs/verify-citations/` venv.

---

## Self-Review

**Spec coverage:** §3 inputs → Tasks 5–8. §4 CrossRef → Tasks 9–10. §5 tiers → Tasks 2–4. §6 output/exit → Tasks 11–12. §8 errors → Task 12 (fail-loud try/except) + Task 9 (404→None). §9 testing → every task's unit tests + Task 13 live probes. §10 packaging/scrub → Tasks 1, 14. All sections covered.

**Placeholder scan:** No TBD/TODO; every code step has complete code. The one runtime-uncertain assumption (CrossRef retraction field shape) is explicitly handled with a fix-it instruction in Task 13, not a placeholder.

**Type consistency:** `Citation`, `CanonicalRecord`, `Finding`, `Tier` defined in Task 1 and used consistently. `evaluate() -> list[Finding]`, `parse(text, fmt) -> list[Citation]`, `CrossRefClient.lookup_by_doi() -> CanonicalRecord | None`, `render_text/json(findings, total, with_doi)` — signatures match across Tasks 4, 8, 9, 11, 12.
