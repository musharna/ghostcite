<!-- Thanks for contributing to ghostcite! -->

## What does this PR do?

<!-- A short description of the change and the motivation. Link any related issue. -->

Fixes #

## Component(s) touched

<!-- Check all that apply -->

- [ ] core checker (`ghostcite/checker.py`)
- [ ] CrossRef client (`ghostcite/crossref.py`)
- [ ] PubMed client (`ghostcite/pubmed.py`)
- [ ] BibTeX parser (`ghostcite/parser.py`)
- [ ] CLI (`ghostcite/cli.py`)
- [ ] docs / CI / packaging

## Checklist

- [ ] `uv run --extra dev ruff check .` passes
- [ ] `uv run --extra dev ruff format --check .` passes
- [ ] `uv run --extra dev pytest -m "not live" -q` passes
- [ ] Coverage stays at or above 85 % (`--cov=ghostcite --cov-fail-under=85`)
- [ ] Added/updated tests for the change (used the `live` marker only where a real API call is genuinely required)
- [ ] Updated `CHANGELOG.md` for any user-facing change
- [ ] Updated docs (`README.md`, `docs/`) if install/usage/config surface changed
