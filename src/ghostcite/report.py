from __future__ import annotations

import json

from ghostcite.models import Finding, Tier

_GLYPH = {
    Tier.AUTHOR: "✗ A",
    Tier.TITLE: "✗ T",
    Tier.YEAR: "✗ B",
    Tier.COSMETIC: "· C",
    Tier.RETRACTION: "⚠ R",
    Tier.UNRESOLVABLE: "? U",
    Tier.SUPPORT: "≈ S",
    Tier.VENUE: "· V",
}

_ANSI = {
    Tier.AUTHOR: "\033[31m",
    Tier.TITLE: "\033[31m",
    Tier.YEAR: "\033[31m",
    Tier.RETRACTION: "\033[35m",
    Tier.COSMETIC: "\033[2m",
    Tier.UNRESOLVABLE: "\033[2m",
    Tier.SUPPORT: "\033[33m",
    Tier.VENUE: "\033[2m",
}
_RESET = "\033[0m"


def _colorize(glyph: str, tier: Tier, enabled: bool) -> str:
    """Wrap a tier glyph (and only the glyph) in its ANSI color when enabled."""
    if not enabled:
        return glyph
    code = _ANSI.get(tier)
    if not code:
        return glyph
    return f"{code}{glyph}{_RESET}"


def _finding_line(f: Finding, color: bool) -> list[str]:
    loc = f"L{f.citation.source_line}" if f.citation.source_line else "—"
    if f.citation.source_file:
        loc = f"{f.citation.source_file}:{loc}"
    who = f.citation.claimed_first_author or f.citation.doi or "?"
    yr = f"({f.citation.claimed_year})" if f.citation.claimed_year else ""
    doi = f"  [{f.citation.doi}]" if f.citation.doi else ""
    glyph = _colorize(_GLYPH[f.tier], f.tier, color)
    out = [f"  {glyph}  {loc}  {who} {yr}  →  {f.message}{doi}"]
    if f.cross_check:
        out.append(f"        ↳ {f.cross_check}")
    return out


def render_text(
    findings: list[Finding],
    total: int,
    with_doi: int,
    *,
    color: bool = False,
    retraction_source: str | None = None,
) -> str:
    findings = [f for f in findings if f.tier is not Tier.OK]
    lines = [f"ghostcite: {total} entries, {with_doi} with DOIs"]
    if retraction_source:
        lines.append(f"  retractions: {retraction_source}")
    if not findings:
        lines.append("  0 findings — clean")
        return "\n".join(lines)
    det = [f for f in findings if f.deterministic]
    sem = [f for f in findings if not f.deterministic]
    for f in sorted(det, key=lambda x: x.citation.source_line or 0):
        lines.extend(_finding_line(f, color))
    if sem:
        lines.append("  — semantic (non-deterministic) —")
        for f in sorted(sem, key=lambda x: x.citation.source_line or 0):
            lines.extend(_finding_line(f, color))
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.tier.value] = counts.get(f.tier.value, 0) + 1
    summary = " · ".join(f"{n} {t}" for t, n in sorted(counts.items()))
    lines.append(f"  {summary}")
    return "\n".join(lines)


def render_badge(findings: list[Finding], fail_on_tiers: set[Tier]) -> str:
    """Serialize a shields.io endpoint badge JSON keyed to the active --fail-on tiers.

    Green/clean when no finding is at/above the fail threshold (matches the exit code);
    red/N-issue(s) otherwise. Warn-only tiers (V/U/C) do not turn it red.
    """
    failing = [f for f in findings if f.tier in fail_on_tiers]
    n = len(failing)
    if n == 0:
        message, color = "clean", "brightgreen"
    else:
        message, color = (f"{n} issue" if n == 1 else f"{n} issues"), "red"
    return json.dumps(
        {"schemaVersion": 1, "label": "ghostcite", "message": message, "color": color}
    )


def render_json(
    findings: list[Finding],
    total: int,
    with_doi: int,
    *,
    retraction_source: str | None = None,
) -> str:
    findings = [f for f in findings if f.tier is not Tier.OK]
    payload = {
        "schema_version": 1,
        "summary": {
            "total": total,
            "with_doi": with_doi,
            "findings": len(findings),
            "retraction_source": retraction_source,
        },
        "findings": [
            {
                "tier": f.tier.value,
                "deterministic": f.deterministic,
                "file": f.citation.source_file,
                "line": f.citation.source_line,
                "claimed_author": f.citation.claimed_first_author,
                "claimed_year": f.citation.claimed_year,
                "doi": f.citation.doi,
                "message": f.message,
                "cross_check": f.cross_check,
                "canonical_authors": f.canonical.authors if f.canonical else None,
                "canonical_year": f.canonical.year if f.canonical else None,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
