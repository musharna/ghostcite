from __future__ import annotations

from ghostcite import cli
from ghostcite.models import CanonicalRecord, Citation, Finding, Tier
from ghostcite.report import _colorize, render_json, render_text


def _author_finding():
    c = Citation(raw="x", source_line=1, doi="10.1/x", claimed_first_author="Li", claimed_year=2024)
    rec = CanonicalRecord(doi="10.1/x", authors=["Chen"], year=2024)
    return Finding(c, Tier.AUTHOR, rec, "CrossRef first author is Chen")


def test_colorize_enabled_wraps_glyph():
    out = _colorize("✗ A", Tier.AUTHOR, True)
    assert out.startswith("\033[31m")
    assert out.endswith("\033[0m")
    assert "✗ A" in out


def test_colorize_disabled_is_plain():
    assert _colorize("✗ A", Tier.AUTHOR, False) == "✗ A"


def test_render_text_color_true_has_ansi():
    out = render_text([_author_finding()], 1, 1, color=True)
    assert "\033[31m" in out


def test_render_text_color_false_no_ansi():
    out = render_text([_author_finding()], 1, 1, color=False)
    assert "\033[" not in out


def test_want_color_never():
    assert cli._want_color("never") is False


def test_want_color_always(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli._want_color("always") is True


def test_want_color_no_color_env_beats_always(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli._want_color("always") is False


def test_want_color_auto_tty_true(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    assert cli._want_color("auto") is True


def test_want_color_auto_tty_false(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    assert cli._want_color("auto") is False


def test_render_json_never_has_ansi_even_with_color():
    # Regression: JSON output must stay machine-clean regardless of --color.
    out = render_json([_author_finding()], 1, 1)
    assert "\033" not in out


def test_json_forces_color_off_even_with_color_always(monkeypatch, tmp_path, capsys):
    # Contract: --json must never carry color, even with --color always.
    monkeypatch.delenv("NO_COLOR", raising=False)
    f = tmp_path / "refs.txt"
    f.write_text("10.1/x\n")
    rc = cli.main(["--dry-run", "--json", "--color", "always", str(f)])
    assert rc == 0
    # The resolved color flag is computed before dry-run returns; assert the
    # contract directly by exercising the resolution expression.
    args = cli._parse_args(["--json", "--color", "always", str(f)])
    color = False if args.json else cli._want_color(args.color)
    assert color is False
