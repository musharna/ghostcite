from __future__ import annotations

import argparse
import sys

from ghostcite.compare import evaluate
from ghostcite.crossref import CrossRefClient
from ghostcite.models import Finding, Tier
from ghostcite.parsers import parse
from ghostcite.report import render_json, render_text

_TIER_BY_NAME = {
    "author": Tier.AUTHOR,
    "year": Tier.YEAR,
    "retraction": Tier.RETRACTION,
}


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="ghostcite",
        description="Catch ghost citations: cross-check claimed author/year against CrossRef.",
    )
    p.add_argument("file", help="bibliography file (.bib, markdown refs, or DOI list)")
    p.add_argument(
        "--format", choices=["auto", "bibtex", "markdown", "doi"], default="auto"
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--dry-run", action="store_true", help="parse + count only, no network"
    )
    p.add_argument(
        "--fail-on",
        default="author,year,retraction",
        help="comma list of tiers that cause exit 1, or 'none' "
        "(choices: author,year,retraction,none)",
    )
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
        print(
            f"ghostcite: would check {len(citations)} entries "
            f"({with_doi} via DOI, {len(citations) - with_doi} via search)."
        )
        return 0

    findings: list[Finding] = []
    try:
        with CrossRefClient() as client:
            for c in citations:
                if c.doi:
                    rec = client.lookup_by_doi(c.doi)
                else:
                    rec = client.search_bibliographic(
                        c.claimed_first_author, c.claimed_year, c.claimed_title
                    )
                findings.extend(evaluate(c, rec))
    except Exception as e:  # fail-loud: surface, keep partial findings
        print(f"ghostcite: CrossRef error: {e}", file=sys.stderr)
        out = (
            render_json(findings, len(citations), with_doi)
            if args.json
            else render_text(findings, len(citations), with_doi)
        )
        print(out)
        return 2

    out = (
        render_json(findings, len(citations), with_doi)
        if args.json
        else render_text(findings, len(citations), with_doi)
    )
    print(out)

    if args.fail_on.strip().lower() == "none":
        return 0
    fail_tiers = {
        _TIER_BY_NAME[n.strip()]
        for n in args.fail_on.split(",")
        if n.strip() in _TIER_BY_NAME
    }
    return 1 if any(f.tier in fail_tiers for f in findings) else 0
