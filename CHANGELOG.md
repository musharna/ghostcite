# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-08

Initial release.

- CrossRef author/year cross-check: compares each citation's claimed first-author
  surname and year against CrossRef's canonical record for the DOI.
- Input auto-detection for BibTeX, Markdown reference lists, and bare DOI lists.
- Severity tiers: A (author mismatch), B (year mismatch), C (cosmetic fold-only),
  R (retraction / expression-of-concern), U (unresolvable / not verifiable).
- Retraction and expression-of-concern detection via CrossRef `update-to` /
  `relation` metadata.
- No-DOI entries resolved by best-effort bibliographic search, flagged
  low-confidence and never escalated above a warning on their own.
- `--json` machine-readable output, `--dry-run` parse-and-count (no network), and
  `--fail-on` CI gate to select which tiers force a non-zero exit.
- Exit-code policy: `0` clean, `1` findings at/above the fail threshold, `2` tool
  error (network down, unparseable input).
