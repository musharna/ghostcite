# Contributing to ghostcite

Thanks for your interest in ghostcite — a deterministic, no-LLM Python CLI that catches ghost citations by cross-checking a bibliography's claimed author/year against CrossRef, with optional PubMed verification and retraction flagging.

## Dev environment setup

ghostcite uses [`uv`](https://docs.astral.sh/uv/) for dependency management. CI resolves
dependencies on the fly via `uv run --extra dev ...` (there is no committed lockfile;
`uv.lock` is gitignored, so there is no frozen-lockfile gate). Mirror it locally:

```bash
# install all extras the test/lint/type checks need
uv sync --extra dev
```

This installs the `dev` tools (pytest, pytest-httpx, ruff, mypy, coverage). Requires **Python ≥ 3.9** (CI tests 3.9, 3.11, and 3.13).

## Running the checks (what CI runs)

CI (`.github/workflows/ci.yml`) runs these (tests on the 3.9 / 3.11 / 3.13 matrix). Run them locally before opening a PR:

```bash
# Lint + format check (gates the build)
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .

# Tests, excluding tests that hit real external APIs
uv run --extra dev pytest -m "not live" -q

# Coverage gate (85 % floor)
uv run --extra dev pytest -m "not live" --cov=ghostcite --cov-fail-under=85 -q

# Type-check (hard CI gate — type errors fail the build)
uv run --extra dev mypy src/ghostcite
```

### Tests and the `live` marker

Most of the suite runs against in-process fixtures (pytest-httpx mocks CrossRef/NCBI responses). Tests marked `live` hit the **real CrossRef API** (and optionally NCBI E-utilities) and are skipped by default in CI.

To run them locally:

```bash
# Basic live probes (CrossRef only)
uv run --extra dev pytest -m live -q

# With PubMed cross-check (supply your NCBI API key for higher rate limits)
NCBI_API_KEY=<your-key> uv run --extra dev pytest -m live -q
```

Live tests should be rare, narrowly scoped (a single known-good DOI + a known ghost), and must not assert on network-variable fields.

### Linting & formatting

Ruff is configured in `pyproject.toml` (`line-length = 100`, `target-version = py39`).
`uv run --extra dev ruff check .` is the gate; `uv run --extra dev ruff check --fix .` and
`uv run --extra dev ruff format .` apply autofixes.

### Type-checking

`uv run --extra dev mypy src/ghostcite` is a **hard CI gate** (the `types` job has no `continue-on-error`, so type errors fail the build). Keep it green — add annotations to new/changed code.

## Running ghostcite locally for manual testing

```bash
# Check a BibTeX file
uv run --extra dev ghostcite refs.bib

# Read from stdin (pipe from another tool)
cat refs.bib | uv run --extra dev ghostcite -

# With PubMed cross-check and colored output
uv run --extra dev ghostcite --cross-check pubmed --color always refs.bib

# Never fail the exit code (report only, no CI gate)
uv run --extra dev ghostcite --fail-on none refs.bib
```

## Commits & pull requests

- **CI must pass.** Ruff, the `not live` test suite, and the 85 % coverage gate must be green across the full Python matrix.
- Keep changes focused and add tests for new behavior. Use the `live` marker only for tests that genuinely need to hit a real external API.
- Update [`CHANGELOG.md`](CHANGELOG.md) for any user-facing change.
- Update docs (`README.md`, `docs/`) when you change install/usage/config surface.
- **Commit style:** conventional commits (`fix:`, `feat:`, `docs:`, `chore:`, `test:`, `refactor:`). No trailers required.
