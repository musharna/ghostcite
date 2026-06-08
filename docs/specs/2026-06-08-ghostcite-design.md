# ghostcite — design spec

**Date:** 2026-06-08
**Status:** design ready for user review (pre-implementation)
**Origin:** Recovers + generalizes the lost `audit_refs_11.py` bibliographic auditor (canonical incident: the 2026-04-29 Phelipanche manuscript citation audit — 6/46 ghost citations caught). Distinct from the `[ID:]` format gate (`citation-gate.py`) and the LLM claim-support verifier (`verify_citations.py`).

## 1. Purpose

A deterministic, **no-LLM** command-line tool that catches **ghost citations** — references whose claimed author/year doesn't match the real bibliographic record for the cited DOI. The dominant failure mode it targets: _right DOI, wrong first author_ (e.g. a manuscript cites "Li et al. 2024" but DOI `10.3390/plants13060869` is actually Chen et al.). Also flags retracted / expression-of-concern works.

It answers: **"does the metadata you wrote for this citation match what CrossRef says the DOI actually is?"**

## 2. Non-goals (v1)

- **No claim-support / entailment.** "Does the source _say_ what the prose claims" is a different tool (the LLM/NLI `verify_citations` line). Out of scope.
- **No auto-fix.** Report and explain only; the user edits.
- **No LLM, no API key, no model download.** Determinism and zero-friction install are core to the value.
- **No PubMed in v1.** Designed as a future `--cross-check pubmed` flag; CrossRef is the v1 source of truth.
- **No citation-_style_ linting** (that's `citation-gate`'s job — bracket/format hygiene).

## 3. Inputs

Auto-detect the input format (sniff, with `--format {bib,markdown,doi,auto}` override):

| Format                      | Detection                                            | Yields claimed (author, year)?                |
| --------------------------- | ---------------------------------------------------- | --------------------------------------------- |
| **BibTeX** (`.bib`)         | `@article{`/`@…{` entries                            | Yes — `author`, `year`, `doi`, `title` fields |
| **Markdown reference list** | bullet lines `- **AuthorList (YYYY).** … DOI/10.x …` | Yes — parsed from the bullet                  |
| **DOI list**                | newline-delimited bare DOIs / `doi:` / DOI URLs      | **No** — nothing to compare against           |

**Degraded mode for DOI-list input:** with no claimed author/year to compare, the tool can't detect mismatches; it instead fetches each DOI's canonical record and reports it + retraction status (a "lookup + retraction sweep"). Surfaced clearly so the user isn't misled into thinking a clean run means "authors verified."

A **Citation record** after parsing:

```python
@dataclass
class Citation:
    raw: str                  # the original entry text (for the report)
    source_line: int | None   # line number in the input, if known
    doi: str | None           # normalized, lowercased, bare (no https://doi.org/ prefix)
    claimed_first_author: str | None   # surname only, as written
    claimed_year: int | None
    claimed_title: str | None          # used to disambiguate wrong-DOI vs wrong-author
```

## 4. Data source

**CrossRef** REST, `GET https://api.crossref.org/works/{doi}`:

- Canonical author list (`author[].family`), `published` year, `title`, `container-title` (journal).
- Retraction / expression-of-concern via the `update-to` / `relation` fields (`update-type` ∈ {retraction, expression_of_concern, correction, …}).
- No-DOI Markdown/bib entries that carry author+title but no DOI → optional resolve via `GET /works?query.bibliographic=…&rows=1` (best-effort; low confidence flagged).

Etiquette: a descriptive **User-Agent** with the repo URL and a generic project contact (the "polite pool") — **never a personal email**. Polite rate-limiting (sequential by default, respect `X-Rate-Limit-*` headers, small backoff on 429/503).

## 5. Checks & severity tiers

Grounded in the Phelipanche audit taxonomy:

| Tier   | Name             | Condition                                                                                                                                                                                                                                        | Fails CI?                                        |
| ------ | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| **A**  | author-mismatch  | claimed first-author surname ∉ CrossRef author family-names (after normalization). If `claimed_title` also diverges strongly from CrossRef title → annotate **"possibly wrong DOI entirely"** (the TA1/TA2 case) vs plain wrong-author (TA3/TA4) | **Yes**                                          |
| **B**  | year-mismatch    | author matches, but claimed year ≠ CrossRef year (±0; online-vs-print noted)                                                                                                                                                                     | **Yes** (tunable)                                |
| **C**  | cosmetic         | author matches only after diacritic-fold or initials normalization (Bürger vs Burger)                                                                                                                                                            | **No** (info only)                               |
| **R**  | retraction / EoC | CrossRef marks the work retracted or under expression-of-concern                                                                                                                                                                                 | **Yes** (orthogonal — fires regardless of A/B/C) |
| **U**  | unresolvable     | DOI 404s at CrossRef, or no-DOI entry that bibliographic search couldn't resolve                                                                                                                                                                 | **No** (warn)                                    |
| **OK** | —                | first-author + year match                                                                                                                                                                                                                        | —                                                |

**Author normalization** (to keep Tier C and false positives out of the failure path):

- Unicode NFKD fold (Bürger → burger), lowercase, strip punctuation.
- Compare **surname** primarily; tolerate "surname only" vs "Surname, F." vs "F. Surname".
- "first author present anywhere in CrossRef author list" is a softer secondary check used to distinguish wrong-author (Tier A) from wrong-DOI-entirely (Tier A + title divergence).
- Initials-only differences → Tier C, not A.

## 6. Output

- **Default:** human-readable tiered report, **quiet on all-clean** (prints a one-line summary only). Mirrors the audit-memo structure: per-finding `claimed → CrossRef-canonical`, with the DOI and a one-line diagnosis.
- **`--json`:** machine-readable array of findings (for CI / programmatic use).
- **`--dry-run`:** parse + classify + count, **no network** — prints how many entries would be checked.
- **Exit codes:** `0` = clean (no A/B/R); `1` = findings at/above the fail threshold; `2` = tool error (network down, unparseable input, etc.).
- **`--fail-on {author,year,retraction,none}`** (default `author,year,retraction`): tune which tiers cause a non-zero exit, so it works as a pre-submission/CI gate or a passive reporter.

Example default report:

```
ghostcite: references.bib — 46 entries, 45 with DOIs
  ✗ A  L227  Hsu CF (2024)  →  CrossRef first author is Gerakari  [10.3390/cimb46080535]
  ✗ A  L312  Clarke CR (2019)  →  DOI resolves to Vaghefi N (2019) — possibly wrong DOI  [10.1094/MPMI-12-18-0334-A]
  ✗ B  L94   Spies D (2019)  →  CrossRef year is 2017  [10.1093/bib/bbx115]
  ⚠ R  L150  Smith J (2021)  →  RETRACTED per CrossRef  [10.xxxx/…]
  · C  L204  Burger M (2025)  →  diacritic: CrossRef has "Bürger" (cosmetic)
  ? U  L401  Ngou (2021)  →  no DOI; bibliographic search inconclusive
  3 author · 1 year · 1 retraction · 1 cosmetic · 1 unresolvable  →  exit 1
```

## 7. Architecture

A lean package (not a single file — auto-detect + future PubMed warrant a few clean seams):

```
ghostcite/
  __init__.py
  cli.py            # argparse, orchestration, exit-code policy
  models.py         # Citation, Finding, Verdict dataclasses + enums
  parsers/
    __init__.py     # sniff() → dispatch
    bibtex.py       # @article{…} → Citation[]
    markdown.py     # bullet refs → Citation[]
    doi.py          # bare DOI list → Citation[] (no claimed author/year)
  crossref.py       # HTTP client: lookup_by_doi(), search_bibliographic(), retraction_status()
  compare.py        # author/year normalization + tier assignment → Finding
  report.py         # text + json renderers
docs/specs/2026-06-08-ghostcite-design.md
tests/
pyproject.toml      # hatchling, console_scripts entry `ghostcite`
README.md
LICENSE             # MIT
```

Each unit is independently testable: parsers take text → `Citation[]`; `crossref.py` takes a DOI → canonical record (mockable); `compare.py` takes `(Citation, CanonicalRecord)` → `Finding`; `report.py` takes `Finding[]` → string/JSON.

**Dependencies:** `httpx` (or stdlib `urllib`) for HTTP; a BibTeX parser (`bibtexparser`, or a small internal parser to stay dependency-light — decide at build time). Python ≥3.9. No LLM/ML deps.

## 8. Error handling

- **Fail-loud:** CrossRef network/5xx errors surface to stderr with the DOI that failed; the run preserves and reports all findings completed so far, then exits 2. No silent skips.
- **Per-entry resilience:** one DOI 404 → that entry becomes Tier U, the run continues.
- **Rate-limit:** respect CrossRef polite-pool headers; backoff on 429/503; `--max-rps` override.
- **Unparseable input:** clear message naming the line; exit 2.

## 9. Testing

- **Unit (mocked CrossRef fixtures):** each parser (bib/markdown/doi sniff + extraction); author normalization (diacritics, initials, surname-only); tier assignment for A/B/C/R/U/OK; report rendering (text + json); exit-code policy per `--fail-on`.
- **Real-execution probe (live CrossRef):** the actual **`10.3390/plants13060869`** case from the Phelipanche audit — claimed "Li 2024", CrossRef returns first author "Chen" → must produce Tier A. A known true-positive against the live API, per the real-execution-testing doctrine.
- **Retraction probe:** a known retracted DOI → must produce Tier R.

## 10. Packaging & publication

- Public repo **`musharna/ghostcite`**, MIT, `main`, topics (citations, crossref, bibtex, research-integrity, cli…).
- `pip install ghostcite` → `ghostcite refs.bib`.
- **Scrub gate** before push: no personal email (generic polite-pool UA), no Zotero lib id, no home paths, no API-key reads. (These were the couplings in the original `verify_citations`; ghostcite is built clean from scratch, so the gate is a confirmation, not a removal.)
- **Bonus / follow-up (not v1 scope):** repoint CLAUDE.md line 30 ("Reusable bib auditor: `/tmp/audit_refs_11.py`") to the installed `ghostcite`, and optionally wire it into the "triple-check every citation" rule — recovering the lost capability in a persistent location.

## 11. Open decisions (flag before build)

1. **Name:** `ghostcite` (proposed). Alternatives: `refcheck`, `citecheck`, `doicheck`.
2. **BibTeX parser:** vendored-minimal (zero deps) vs `bibtexparser` dependency. Lean toward minimal-internal for the common fields (author/year/doi/title), since we only need 4 fields.
3. **No-DOI bibliographic resolution:** include best-effort CrossRef search in v1, or defer (emit Tier U for all no-DOI entries in v1)? Leaning: include but mark low-confidence.
