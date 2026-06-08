# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Retraction and expression-of-concern detection via CrossRef `update-to` /
  `relation` metadata.
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
