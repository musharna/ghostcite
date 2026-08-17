# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **BibTeX entries following any non-`@` text were silently merged into the
  previous entry, and the survivor carried the WRONG metadata.** Entry extent was
  decided by a lookahead requiring the closing brace to be followed by `@` or
  end-of-input, so a `%` comment, a stray note, a blank-line remark or a
  `\section{}` between two entries made the pattern run on to a later brace and
  swallow the next entry. The merged `Citation` kept the FIRST entry's key and
  raw line while taking the SECOND entry's `doi`, `author` and `year` — later
  fields win when the body of two entries is parsed as one. A tool whose purpose
  is catching wrong-author-for-right-DOI was therefore capable of manufacturing
  exactly that pairing, and it reported `0 findings — clean` while doing so:
  neither the printed count, the findings list, nor the exit status was a
  function of how many entries were actually read.

  Found on a real 17-entry bibliography that reported `16 entries, 16 with DOIs`
  with an explanatory comment block between the tenth and eleventh entries. Only
  text beginning with `@` was safe, by accident, which is why `@comment{}` blocks
  never triggered it.

  Entry extent is now determined by brace matching — a property of the entry
  itself — so no amount of surrounding text can change where an entry ends.
  `@comment` / `@string` / `@preamble` are now skipped explicitly rather than
  incidentally (they were passed over only because they happen to contain no
  comma), and an unterminated final entry is parsed to end-of-input rather than
  dropped.

## [0.5.1] - 2026-07-28

### Added

- `CITATION.cff` now carries an ORCID and is validated against the CFF 1.2.0 schema, so
  GitHub renders a **Cite this repository** panel and Zenodo can mint a DOI from it.
- `.zenodo.json` pins the metadata Zenodo uses for the DOI record (title, description,
  creators, licence, keywords) rather than letting it infer them from the repository.

### Fixed

- `CITATION.cff` claimed `0.4.0` while the project shipped `0.5.0`. Citation metadata is
  machine-readable and ends up in other people's bibliographies, so a stale version there
  is worse than none.
- A new `citation` CI job fails any change where `CITATION.cff`'s version disagrees with
  `pyproject.toml`, which is how the drift above went unnoticed. It mirrors the existing
  "tag matches pyproject version" release gate, one layer earlier.

## [0.5.0] - 2026-07-03

### Added

- Multi-file and directory input: the CLI now accepts one or more paths, and a
  directory is walked recursively for `*.bib`/`*.md` (hidden dirs like `.git`
  skipped). This makes the GitHub Action's default `paths: .` work as documented.
  When more than one file is scanned, findings are attributed with their filename
  (text `path:Lnn`, JSON `file` field). The pre-commit hook now passes staged
  filenames automatically (`pass_filenames: true`).

### Fixed

- `--fail-on` now errors on an unknown tier name instead of silently dropping it
  (a typo like `--fail-on retractions` had turned the CI gate into a no-op).
- DOI cache round-trip no longer drops the preprint flags (`is_preprint`,
  `has_preprint_relation`); a preprint served from a warm cache is now downgraded
  identically to a cold lookup (restores determinism).
- Markdown/DOI-list entries (which carry no parsed title) no longer emit a
  misleading "possibly wrong DOI" verdict on an author mismatch; they fall back to
  the neutral "CrossRef first author is …" message.
- DOIs are URL-encoded before being spliced into CrossRef/OpenAlex/`doi.org` request
  URLs, so a DOI containing `#` (or other URL-significant characters) is no longer
  silently truncated into a different query.
- `--json --dry-run` now emits valid JSON instead of a plain-text line.

### Packaging / CI

- Release workflow gains a test gate (`build` needs `test`), so a tag pushed on a
  red tree cannot publish. Action inputs are passed via `env:` (no shell
  interpolation), the Action's `pip install` is pinned, and the `v1` major tag is
  force-moved to each release commit.
- `.claude/` is git-ignored and excluded from the sdist (was leaking local
  worktrees into `uv build` artifacts). Added the `Typing :: Typed` classifier.
- `test_semantic_live.py` gains the `live` marker so the weekly live-tests
  workflow actually collects it (and that workflow now sets `GHOSTCITE_LIVE=1`).

## [0.4.0] - 2026-06-16

### Added

- Venue-mismatch tier `V` (warn-only, opt-in): flags a cited journal/venue that disagrees with
  CrossRef's container-title, using abbreviation-tolerant matching (so "J. Mol. Biol." vs
  "Journal of Molecular Biology" does not fire). Informational by default; add `--fail-on venue`
  to gate on it. Suppressed when an author/title mismatch already fired.
- Preprint ↔ published awareness: a year difference that is explained by the DOI being a preprint
  (or having a preprint/published relation) is downgraded from a CI-failing year mismatch to a
  non-failing informational finding.
- Dead-DOI resolution probe: when a DOI is absent from CrossRef, a `HEAD https://doi.org/<doi>`
  distinguishes "dead/fabricated DOI" from "resolves but not in CrossRef" in the Tier U message.
  Best-effort, never fails CI on its own; `--no-doi-probe` skips it for fully offline runs.
- `--badge <path>`: writes a shields.io endpoint badge JSON (citation health) keyed to the active
  `--fail-on` threshold (green/clean vs red/N issues). Warn-only tiers do not turn it red.
- `--cross-check` now accepts a comma-separated list and adds **openalex** as a second source of
  truth (mirroring the PubMed pass: corroborate/conflict, raise findings CrossRef missed, and
  OR-combine retraction). `--cross-check pubmed` is unchanged; `--cross-check pubmed,openalex`
  runs both. Optional `--openalex-mailto` / `OPENALEX_MAILTO` for the polite pool.

## [0.3.0] - 2026-06-12

### Added

- Title-mismatch tier (`T`): catches "identifier hijacking" — a DOI that resolves
  to a different paper than the one cited — by comparing the claimed title against
  CrossRef's canonical title (conservative token-overlap; tolerates subtitle and
  formatting variance). Fires even when the claimed author coincidentally matches.
  Deterministic; included in the default `--fail-on` (`author,title,year,retraction`).
- Opt-in semantic claim-support layer (`--semantic` / `--claims <file.json>`):
  checks whether a cited paper's abstract supports a claim via a bring-your-own
  LLM backend (OpenAI-compatible or Anthropic), abstract-grounded. Findings are
  marked non-deterministic (`tier=S`), segregated in output, and excluded from
  `--fail-on` unless opted in (`--fail-on support`). With `--semantic` off,
  behavior and dependencies are unchanged — the deterministic core never imports
  the semantic subpackage.
- `ghostcite.check_claim_support()` public API; `CanonicalRecord.abstract`
  populated from CrossRef (JATS-stripped).

## [0.2.0] - 2026-06-11

### Added

- Offline / reproducible retraction checking via a local Retraction Watch
  snapshot. `ghostcite fetch-retractions --mailto …` downloads the snapshot to
  the XDG cache (with a provenance sidecar); `--retraction-db <path>` pins an
  exact snapshot (or `none` to force live CrossRef). When a snapshot is active it
  is the authoritative retraction source and the report names it; the byline/year
  check still queries CrossRef live. Attribution: Crossref + Retraction Watch
  (The Center for Scientific Integrity) — see `NOTICE`.

## [0.1.0] - 2026-06-08

Initial release.

### Added

- CrossRef author/year cross-check: compares each citation's claimed first-author
  surname and year against CrossRef's canonical record for the DOI.
- Input auto-detection for BibTeX, Markdown reference lists, and bare DOI lists
  (override with `--format {auto,bibtex,markdown,doi}`).
- Read the bibliography from stdin by passing `-` as the filename
  (e.g. `cat refs.bib | ghostcite -`).
- Severity tiers: A (author mismatch), B (year mismatch), C (cosmetic fold-only),
  R (retraction / expression-of-concern), U (unresolvable / not verifiable).
- Retraction and expression-of-concern detection via CrossRef `updated-by` /
  `update-to` / `relation` metadata.
- `--cross-check pubmed`: optional second source of truth via PubMed / NCBI
  E-utilities. Corroborates or conflicts CrossRef findings, can raise findings
  CrossRef missed, and supplies records for DOIs absent from CrossRef. Honors
  `--ncbi-email` / `--ncbi-api-key` (or `NCBI_EMAIL` / `NCBI_API_KEY`) for NCBI
  etiquette and a higher rate limit.
- Proactive rate pacing: self-throttles to CrossRef's advertised rate limit (read
  from response headers); `--max-rps` to cap further.
- `--color {auto,always,never}` colorized tier glyphs, honoring `NO_COLOR`.
- No-DOI entries resolved by best-effort bibliographic search, flagged
  low-confidence and never escalated above a warning on their own.
- `--json` machine-readable output, `--dry-run` parse-and-count (no network), and
  `--fail-on` CI gate to select which tiers force a non-zero exit.
- `--version` flag and `python -m ghostcite` module entry point.
- Composite GitHub Action (`musharna/ghostcite@v1`) for drop-in CI usage.
- Exit-code policy: `0` clean, `1` findings at/above the fail threshold, `2` tool
  error (network down, unparseable input).
