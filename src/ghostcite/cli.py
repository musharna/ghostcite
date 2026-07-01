from __future__ import annotations

import argparse
import os
import sys
from contextlib import ExitStack

from ghostcite import __version__
from ghostcite.api import _process_citation
from ghostcite.compare import cross_check_openalex, cross_check_pubmed
from ghostcite.crossref import CrossRefClient
from ghostcite.models import Finding, Tier
from ghostcite.openalex import OpenAlexClient
from ghostcite.parsers import parse
from ghostcite.pubmed import PubMedClient
from ghostcite.report import render_json, render_text
from ghostcite.retractions import (
    RetractionDBError,
    default_cache_path,
    fetch_retractions,
    resolve_db,
)

_TIER_BY_NAME = {
    "author": Tier.AUTHOR,
    "title": Tier.TITLE,
    "year": Tier.YEAR,
    "retraction": Tier.RETRACTION,
    "support": Tier.SUPPORT,
    "venue": Tier.VENUE,
}


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="ghostcite",
        description="Catch ghost citations: cross-check claimed author/year against CrossRef.",
        epilog=(
            "subcommands:\n"
            "  fetch-retractions   download the Retraction Watch snapshot for offline use "
            "(see `ghostcite fetch-retractions --help`)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"ghostcite {__version__}")
    p.add_argument(
        "file",
        nargs="*",
        default=None,
        help="bibliography file(s) or directory to scan (.bib, markdown refs, or "
        "DOI list); directories are walked for *.bib/*.md. Use '-' for stdin.",
    )
    p.add_argument("--format", choices=["auto", "bibtex", "markdown", "doi"], default="auto")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--dry-run", action="store_true", help="parse + count only, no network")
    p.add_argument(
        "--fail-on",
        default="author,title,year,retraction",
        help="comma list of tiers that cause exit 1, or 'none' "
        "(choices: author,title,year,retraction,support,venue,none)",
    )
    p.add_argument(
        "--max-rps",
        type=float,
        default=None,
        help="cap outbound requests per second (proactive rate pacing)",
    )
    p.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="colorize tier glyphs (default auto; honors NO_COLOR)",
    )
    p.add_argument(
        "--cross-check",
        default="none",
        help="comma-separated sources to corroborate findings against "
        "(choices: pubmed, openalex; default none)",
    )
    p.add_argument(
        "--ncbi-email",
        default=os.environ.get("NCBI_EMAIL"),
        help="contact email for NCBI E-utilities (or set NCBI_EMAIL)",
    )
    p.add_argument(
        "--ncbi-api-key",
        default=os.environ.get("NCBI_API_KEY"),
        help="NCBI API key for higher rate limits (or set NCBI_API_KEY)",
    )
    p.add_argument(
        "--openalex-mailto",
        default=os.environ.get("OPENALEX_MAILTO"),
        help="contact email for OpenAlex polite pool (or set OPENALEX_MAILTO)",
    )
    p.add_argument(
        "--retraction-db",
        default=None,
        help="path to a Retraction Watch CSV snapshot (authoritative retraction "
        "source; 'none' forces live CrossRef even if a cache exists)",
    )
    p.add_argument(
        "--semantic",
        action="store_true",
        help="enable the opt-in semantic claim-support layer (needs a backend)",
    )
    p.add_argument("--semantic-backend", choices=["openai", "anthropic"], default="openai")
    p.add_argument("--semantic-model", default=os.environ.get("GHOSTCITE_SEMANTIC_MODEL", ""))
    p.add_argument("--semantic-base-url", default=os.environ.get("GHOSTCITE_SEMANTIC_BASE_URL"))
    p.add_argument("--semantic-api-key", default=os.environ.get("GHOSTCITE_SEMANTIC_API_KEY"))
    p.add_argument(
        "--claims",
        default=None,
        help="path to a JSON list of {claim, doi} to claim-support check (semantic)",
    )
    p.add_argument(
        "--no-doi-probe",
        action="store_true",
        help="skip the doi.org HEAD probe used to refine unresolvable-DOI messages",
    )
    p.add_argument(
        "--badge",
        default=None,
        help="write a shields.io endpoint badge JSON (citation health) to this path",
    )
    args = p.parse_args(argv)
    if args.max_rps is not None and args.max_rps <= 0:
        p.error("--max-rps must be > 0")
    # Parse --cross-check into a validated set of source names.
    _KNOWN_SOURCES = {"pubmed", "openalex"}
    raw = args.cross_check.strip().lower()
    if raw == "none":
        args.cross_sources = set()
    else:
        parts = {s.strip() for s in raw.split(",") if s.strip()}
        unknown = parts - _KNOWN_SOURCES
        if unknown:
            p.error(
                f"unknown --cross-check source(s): {', '.join(sorted(unknown))}; "
                f"valid choices are: {', '.join(sorted(_KNOWN_SOURCES))}"
            )
        args.cross_sources = parts
    # Validate --fail-on tier names up front so a typo doesn't silently disable
    # the CI gate (an unknown tier would otherwise drop to an empty fail-set).
    fo = args.fail_on.strip().lower()
    if fo != "none":
        fo_parts = {s.strip() for s in fo.split(",") if s.strip()}
        fo_unknown = fo_parts - set(_TIER_BY_NAME)
        if fo_unknown:
            p.error(
                f"unknown --fail-on tier(s): {', '.join(sorted(fo_unknown))}; "
                f"valid choices are: {', '.join(sorted(_TIER_BY_NAME))}, none"
            )
    return args


def _want_color(mode: str) -> bool:
    """Resolve --color {auto,always,never} against NO_COLOR + TTY state.

    NO_COLOR (presence, any value) disables color even when ``always`` is set,
    per https://no-color.org/.
    """
    if "NO_COLOR" in os.environ:
        return False
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def _fetch_retractions_main(argv) -> int:
    p = argparse.ArgumentParser(
        prog="ghostcite fetch-retractions",
        description="Download the Retraction Watch snapshot for offline use.",
    )
    p.add_argument(
        "--mailto",
        default=os.environ.get("GHOSTCITE_MAILTO"),
        help="contact email (required by Crossref Labs; or set GHOSTCITE_MAILTO)",
    )
    p.add_argument(
        "--dest",
        default=None,
        help="output CSV path (default: the XDG cache location)",
    )
    a = p.parse_args(argv)
    dest = a.dest or default_cache_path()
    try:
        meta = fetch_retractions(a.mailto or "", dest)
    except RetractionDBError as e:
        print(f"ghostcite: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # network/HTTP - fail loud
        print(f"ghostcite: fetch-retractions failed: {e}", file=sys.stderr)
        return 2
    print(
        f"ghostcite: wrote {meta['row_count']} retraction records to {dest}\n"
        "Retraction data: Crossref + Retraction Watch (The Center for Scientific "
        "Integrity), retrieved via Crossref Labs."
    )
    return 0


_SCAN_SUFFIXES = (".bib", ".md", ".markdown")


def _collect_input_files(paths: list[str]) -> list[str]:
    """Expand positional args into an ordered, de-duplicated list of files.

    A directory is walked recursively for ``*.bib``/``*.md`` (hidden directories
    such as ``.git``/``.venv``/``.claude`` are skipped so a bare ``ghostcite .``
    scans the project without dredging up VCS internals). A plain file is kept
    verbatim regardless of extension (so explicit DOI-list files still work).
    """
    from pathlib import Path

    files: list[str] = []
    for raw in paths:
        pth = Path(raw)
        if pth.is_dir():
            matches: set[Path] = set()
            for suffix in _SCAN_SUFFIXES:
                matches.update(pth.rglob(f"*{suffix}"))
            for m in sorted(matches):
                rel_parents = m.relative_to(pth).parts[:-1]
                if any(part.startswith(".") for part in rel_parents):
                    continue
                files.append(str(m))
        else:
            files.append(str(pth))
    # De-duplicate while preserving first-seen order (overlapping paths).
    return list(dict.fromkeys(files))


def _fail_tiers(fail_on: str) -> set[Tier]:
    if fail_on.strip().lower() == "none":
        return set()
    return {_TIER_BY_NAME[n.strip()] for n in fail_on.split(",") if n.strip() in _TIER_BY_NAME}


def _exit_code(fail_on: str, findings: list[Finding]) -> int:
    fail_tiers = _fail_tiers(fail_on)
    return 1 if any(f.tier in fail_tiers for f in findings) else 0


def _claims_main(args) -> int:
    import json as _json

    try:
        with open(args.claims, encoding="utf-8") as _fh:
            pairs = _json.loads(_fh.read())
        assert isinstance(pairs, list)
    except (OSError, ValueError, AssertionError) as e:
        print(f"ghostcite: cannot read --claims file: {e}", file=sys.stderr)
        return 2

    from ghostcite.cache import DoiCache
    from ghostcite.semantic import backends as _backends
    from ghostcite.semantic import support as _support

    try:
        backend = _backends.build_backend(
            args.semantic_backend,
            base_url=args.semantic_base_url,
            api_key=args.semantic_api_key,
            model=args.semantic_model or "default",
        )
    except _backends.SemanticBackendError as e:
        print(f"ghostcite: {e}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    try:
        with CrossRefClient(max_rps=args.max_rps) as client:
            provider = _support.AbstractProvider(client=client, cache=DoiCache())
            for item in pairs:
                if not isinstance(item, dict):
                    continue
                claim = item.get("claim")
                doi = item.get("doi")
                if not claim or not doi:
                    continue
                f = _support.check_claim_support(
                    claim, doi, backend=backend, source_provider=provider
                )
                if f is not None:
                    findings.append(f)
    except Exception as e:  # fail-loud: backend OR abstract-fetch transport error → exit 2
        print(f"ghostcite: claim-support check failed: {e}", file=sys.stderr)
        return 2

    color = False if args.json else _want_color(args.color)
    out = (
        render_json(findings, len(pairs), len(pairs))
        if args.json
        else render_text(findings, len(pairs), len(pairs), color=color)
    )
    print(out)
    return _exit_code(args.fail_on, findings)


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "fetch-retractions":
        return _fetch_retractions_main(argv[1:])
    args = _parse_args(argv)

    if args.claims:
        return _claims_main(args)

    paths = args.file or []
    if not paths:
        print("ghostcite: a bibliography file, directory, or '-' is required", file=sys.stderr)
        return 2

    if args.semantic:
        print(
            "ghostcite: --semantic on a bibliography has no claims to check; "
            "pass --claims <file.json> with {claim, doi} pairs. Running core checks only.",
            file=sys.stderr,
        )

    citations = []
    if "-" in paths:
        if len(paths) != 1:
            print("ghostcite: '-' (stdin) cannot be combined with other paths", file=sys.stderr)
            return 2
        text = sys.stdin.read()
        if not text.strip():
            print("ghostcite: no input on stdin", file=sys.stderr)
            return 2
        try:
            citations = parse(text, fmt=args.format)
        except ValueError as e:
            print(f"ghostcite: {e}", file=sys.stderr)
            return 2
    else:
        files = _collect_input_files(paths)
        if not files:
            print(
                "ghostcite: no .bib/.md files found under the given path(s)",
                file=sys.stderr,
            )
            return 0
        tag_source = len(files) > 1
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as e:
                print(f"ghostcite: cannot read {fp}: {e}", file=sys.stderr)
                return 2
            try:
                file_cites = parse(text, fmt=args.format)
            except ValueError as e:
                print(f"ghostcite: {fp}: {e}", file=sys.stderr)
                return 2
            if tag_source:
                for c in file_cites:
                    c.source_file = fp
            citations.extend(file_cites)

    color = False if args.json else _want_color(args.color)
    with_doi = sum(1 for c in citations if c.doi)
    if args.dry_run:
        if args.json:
            import json as _json

            print(
                _json.dumps(
                    {
                        "dry_run": True,
                        "total": len(citations),
                        "with_doi": with_doi,
                        "without_doi": len(citations) - with_doi,
                    }
                )
            )
        else:
            print(
                f"ghostcite: would check {len(citations)} entries "
                f"({with_doi} via DOI, {len(citations) - with_doi} via search)."
            )
        return 0

    try:
        rdb = resolve_db(args.retraction_db)
    except RetractionDBError as e:
        print(f"ghostcite: {e}", file=sys.stderr)
        return 2
    retraction_source = rdb.source_label if rdb else "CrossRef live"

    findings: list[Finding] = []
    cross_sources = args.cross_sources
    try:
        with ExitStack() as stack:
            client = stack.enter_context(CrossRefClient(max_rps=args.max_rps))
            pmclient = None
            if "pubmed" in cross_sources:
                pmclient = stack.enter_context(
                    PubMedClient(
                        max_rps=args.max_rps,
                        email=args.ncbi_email,
                        api_key=args.ncbi_api_key,
                    )
                )
            oaclient = None
            if "openalex" in cross_sources:
                oaclient = stack.enter_context(
                    OpenAlexClient(
                        max_rps=args.max_rps,
                        mailto=args.openalex_mailto,
                    )
                )
            for c in citations:
                cite_findings, rec = _process_citation(
                    c, client=client, retraction_db=rdb, probe_doi=not args.no_doi_probe
                )
                if pmclient is not None:
                    if c.doi:
                        pm = pmclient.lookup_by_doi(c.doi)
                    else:
                        pm = pmclient.lookup_by_doi_meta(
                            c.claimed_first_author, c.claimed_year, c.claimed_title
                        )
                    cross_check_pubmed(c, rec, cite_findings, pm)
                if oaclient is not None and c.doi:
                    oa = oaclient.lookup_by_doi(c.doi)
                    cross_check_openalex(c, rec, cite_findings, oa)
                findings.extend(cite_findings)
    except Exception as e:  # fail-loud: surface, keep partial findings
        print(f"ghostcite: cross-check error: {e}", file=sys.stderr)
        out = (
            render_json(findings, len(citations), with_doi, retraction_source=retraction_source)
            if args.json
            else render_text(
                findings, len(citations), with_doi, color=color, retraction_source=retraction_source
            )
        )
        print(out)
        return 2

    out = (
        render_json(findings, len(citations), with_doi, retraction_source=retraction_source)
        if args.json
        else render_text(
            findings, len(citations), with_doi, color=color, retraction_source=retraction_source
        )
    )
    print(out)

    if args.badge:
        from ghostcite.report import render_badge

        try:
            with open(args.badge, "w", encoding="utf-8") as bf:
                bf.write(render_badge(findings, _fail_tiers(args.fail_on)))
        except OSError as e:
            print(f"ghostcite: could not write badge to {args.badge}: {e}", file=sys.stderr)

    return _exit_code(args.fail_on, findings)
