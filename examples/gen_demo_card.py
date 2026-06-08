#!/usr/bin/env python3
"""Render a deterministic terminal-card demo PNG for the ghostcite README.

Pure Pillow, no TTY required. Draws a dark terminal window (rounded corners +
traffic-light dots) showing a real ``ghostcite --cross-check pubmed`` session:
the Li -> Chen ghost-citation case, a CrossRef year mismatch, and a retraction.

Run::

    python3 examples/gen_demo_card.py

Output: ``examples/assets/demo.png`` (~1040px wide). Requires the optional
``viz`` dependency group (``pip install ghostcite[viz]`` or ``pip install pillow``).
"""

from __future__ import annotations

import glob
import os

from PIL import Image, ImageDraw, ImageFont

FONTDIR = os.path.expanduser("~/.local/share/fonts")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# Glyphs the JetBrains Mono Nerd Font maps to an empty/tofu placeholder; render
# these with DejaVu (which covers them) so the card has no missing-glyph boxes.
_FALLBACK_GLYPHS = "↳"


def _font(pattern: str, size: int) -> ImageFont.FreeTypeFont:
    hits = sorted(glob.glob(os.path.join(FONTDIR, pattern)))
    path = hits[0] if hits else _DEJAVU
    return ImageFont.truetype(path, size)


def _draw_text(draw, xy, text, *, font, fallback, fill):
    """Draw monospace text, swapping to ``fallback`` for tofu glyphs.

    Returns the total advance width. Per-char so the mono cell stays aligned.
    """
    x, y = xy
    cell = draw.textlength("M", font=font)
    for ch in text:
        fnt = fallback if ch in _FALLBACK_GLYPHS else font
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += cell
    return cell * len(text)


# Palette (dark terminal, One Dark-ish).
BG_OUTER = (13, 17, 23)  # page behind the window
WIN_BG = (30, 33, 39)  # terminal body
TITLEBAR = (40, 44, 52)  # title bar
FG = (220, 223, 228)  # default text
DIM = (118, 124, 138)  # muted (DOIs, notes)
GREEN = (152, 195, 121)  # prompt
RED = (224, 108, 117)  # ✗ A / ✗ B glyphs
MAGENTA = (198, 120, 221)  # ⚠ R glyph
CYAN = (86, 182, 194)  # command emphasis
DOT_RED = (255, 95, 86)
DOT_YEL = (255, 189, 46)
DOT_GRN = (39, 201, 63)

# A "segment" is (text, color). Each line is a list of segments.
LINES: list[list[tuple[str, tuple[int, int, int]]]] = [
    [("$ ", GREEN), ("ghostcite refs.bib --cross-check pubmed", FG)],
    [("ghostcite: 3 entries, 3 with DOIs", FG)],
    [
        ("  ✗ A  ", RED),
        ("L1   Li (2024)      →  DOI resolves to Chen (2024) — possibly wrong DOI  ", FG),
        ("[10.3390/plants13060869]", DIM),
    ],
    [("         ↳ corroborated by PubMed", DIM)],
    [
        ("  ✗ B  ", RED),
        ("L8   Spies (2019)   →  CrossRef year is 2017  ", FG),
        ("[10.1093/bib/bbx115]", DIM),
    ],
    [
        ("  ⚠ R  ", MAGENTA),
        ("L15  Smith (2021)   →  RETRACTED per CrossRef  ", FG),
        ("[10.1016/s0140-6736(97)11096-0]", DIM),
    ],
    [
        ("  2 A · 1 B · 1 R  →  ", FG),
        ("exit 1", CYAN),
    ],
]


def main() -> None:
    # Layout metrics.
    fsize = 17
    mono = _font("JetBrainsMonoNLNerdFont-Regular.ttf", fsize)
    dejavu = ImageFont.truetype(_DEJAVU, fsize)
    titlefont = _font("JetBrainsMonoNLNerdFont-Medium.ttf", 15)
    line_h = 27
    pad_x = 30
    top_chrome = 48  # title bar height
    pad_top = 20
    pad_bottom = 22

    # Measure widest line to size the window. Text is monospace, so width is
    # (longest char count) * cell width — independent of which fallback font a
    # given glyph uses.
    probe = Image.new("RGB", (10, 10))
    pd = ImageDraw.Draw(probe)
    cell = pd.textlength("M", font=mono)
    max_chars = max(sum(len(t) for t, _ in segs) for segs in LINES)
    max_w = cell * max_chars

    win_w = int(max_w) + 2 * pad_x
    body_h = pad_top + line_h * len(LINES) + pad_bottom
    win_h = top_chrome + body_h

    margin = 28
    W = win_w + 2 * margin
    H = win_h + 2 * margin

    img = Image.new("RGB", (W, H), BG_OUTER)
    d = ImageDraw.Draw(img)

    # Window with rounded corners.
    x0, y0 = margin, margin
    x1, y1 = margin + win_w, margin + win_h
    radius = 12
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=WIN_BG)
    # Title bar (rounded top, square bottom via overlay).
    d.rounded_rectangle([x0, y0, x1, y0 + top_chrome], radius=radius, fill=TITLEBAR)
    d.rectangle([x0, y0 + top_chrome - radius, x1, y0 + top_chrome], fill=TITLEBAR)
    # re-cover the body seam
    d.rectangle([x0, y0 + top_chrome, x1, y0 + top_chrome + radius], fill=WIN_BG)
    d.rounded_rectangle([x0, y0 + top_chrome - radius, x1, y1], radius=radius, fill=WIN_BG)
    d.rounded_rectangle([x0, y0, x1, y0 + top_chrome], radius=radius, fill=TITLEBAR)
    d.rectangle([x0, y0 + top_chrome - radius, x1, y0 + top_chrome], fill=TITLEBAR)

    # Traffic-light dots.
    cy = y0 + top_chrome // 2
    r = 6
    for i, col in enumerate((DOT_RED, DOT_YEL, DOT_GRN)):
        cx = x0 + 22 + i * 24
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # Title label, centered.
    title = "ghostcite — refs.bib"
    tw = d.textlength(title, font=titlefont)
    d.text((x0 + (win_w - tw) / 2, cy - 9), title, font=titlefont, fill=DIM)

    # Body text (per-char draw so tofu glyphs fall back to DejaVu).
    ty = y0 + top_chrome + pad_top
    for segs in LINES:
        tx = x0 + pad_x
        for text, color in segs:
            tx += _draw_text(d, (tx, ty), text, font=mono, fallback=dejavu, fill=color)
        ty += line_h

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "demo.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print(f"wrote {out} ({W}x{H})")


if __name__ == "__main__":
    main()
