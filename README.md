# ghostcite

**Catch ghost citations — right DOI, wrong author.**

`ghostcite` is a deterministic, **no-LLM** command-line tool that cross-checks a
bibliography's _claimed_ author and year against CrossRef's canonical record for
each DOI. It catches the dominant ghost-citation failure mode — a reference whose
cited authorship doesn't match the paper the DOI actually points to — and flags
retracted or expression-of-concern works along the way.

## The problem

LLM-assisted writing (and plain copy-paste drift) routinely produces references
that _look_ right but attribute the cited DOI to the wrong authors or year. A
manuscript cites "Li et al. 2024," but DOI `10.3390/plants13060869` is actually
**Chen et al.** A reviewer catches it; an automated check catches it first.

`ghostcite` answers exactly one question, deterministically:

> Does the metadata you wrote for this citation match what CrossRef says the DOI actually is?

No model, no API key, no download. Just CrossRef's REST API and a comparison.

## Install

```bash
pip install ghostcite
```

## Usage

```bash
ghostcite refs.bib              # check a BibTeX file
ghostcite refs.md               # markdown reference list
ghostcite dois.txt              # bare DOI list (lookup + retraction sweep)
ghostcite refs.bib --json       # machine-readable output (for CI)
ghostcite refs.bib --dry-run    # parse + count only, no network
ghostcite refs.bib --fail-on author,year,retraction   # tune the CI gate
```

Input format is auto-detected; override with `--format {auto,bibtex,markdown,doi}`.

### Real example

Given `refs.bib`:

```bibtex
@article{li2024,
  author = {Li, X},
  year   = {2024},
  title  = {Cell wall activity in Phelipanche},
  doi    = {10.3390/plants13060869},
}
```

```text
$ ghostcite refs.bib
ghostcite: 1 entries, 1 with DOIs
  ✗ A  L1  Li (2024)  →  DOI resolves to Chen (2024) — possibly wrong DOI  [10.3390/plants13060869]
  1 A
$ echo $?
1
```

The DOI is real; the claimed first author "Li" is not — CrossRef says it's Chen.

## Input formats

| Format       | Detection                                       | Yields claimed author/year?            |
| ------------ | ----------------------------------------------- | -------------------------------------- |
| **BibTeX**   | `@article{…}` / `@…{…}` entries                 | Yes (`author`, `year`, `doi`, `title`) |
| **Markdown** | bullet refs `- **AuthorList (YYYY).** … 10.x …` | Yes                                    |
| **DOI list** | newline-delimited bare DOIs / `doi:` / DOI URLs | No — lookup + retraction sweep only    |

A DOI-list run can't detect author/year mismatches (nothing is claimed to compare
against); it reports each DOI's canonical record and retraction status, and says so.

## Severity tiers

| Tier   | Meaning                                                               | Fails CI?                       |
| ------ | --------------------------------------------------------------------- | ------------------------------- |
| **A**  | author-mismatch — claimed first author isn't in CrossRef's authors    | Yes                             |
| **B**  | year-mismatch — author matches, claimed year differs                  | Yes                             |
| **C**  | cosmetic — matches only after diacritic/initials fold (Bürger≈Burger) | No (info)                       |
| **R**  | retraction / expression-of-concern per CrossRef                       | Yes (fires regardless of A/B/C) |
| **U**  | unresolvable — DOI 404s, or no-DOI entry search was inconclusive      | No (warn)                       |
| **OK** | first author + year match                                             | —                               |

When the claimed title also diverges strongly from CrossRef's title, a Tier A
finding is annotated **"possibly wrong DOI entirely"** to distinguish a wrong-author
citation from a wrong-DOI one.

## Exit codes

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| `0`  | clean — no findings at or above the fail threshold |
| `1`  | findings present at/above the threshold            |
| `2`  | tool error (network down, unparseable input, …)    |

`--fail-on` (default `author,year,retraction`) selects which tiers force exit `1`;
pass `--fail-on none` to run as a passive reporter. Tiers `C` and `U` never force exit `1`.

## How it works

For each parsed citation:

1. If it has a DOI → `GET https://api.crossref.org/works/{doi}` for the canonical record.
2. If it has no DOI but has author/title → best-effort `GET /works?query.bibliographic=…`
   (results flagged **low-confidence**, never escalated above a warning on their own).
3. Compare claimed first-author surname (Unicode-folded, punctuation-stripped) and year
   against the canonical record; assign a severity tier.
4. Check `updated-by` / `update-to` / `relation` for retraction / expression-of-concern.

No language model is involved at any step. The comparison is pure and deterministic;
only the CrossRef client touches the network.

CrossRef requests carry a descriptive `User-Agent` with the project URL (the CrossRef
"polite pool"), never a personal email.

## CI / pre-submission gate

```yaml
# .github/workflows/citations.yml
- name: Check citations
  run: |
    pip install ghostcite
    ghostcite paper/references.bib --fail-on author,year,retraction
```

A non-zero exit fails the job, so a ghost citation blocks the merge before submission.

## Scope (v1)

`ghostcite` checks **metadata correctness** (does the DOI's record match what you
wrote), not claim support (does the source actually say what your prose claims) — that
is a separate, LLM-based concern. It does no auto-fixing, no citation-style linting,
and uses CrossRef as the single source of truth (PubMed cross-checking is a future flag).

## License

MIT — see [LICENSE](LICENSE).
