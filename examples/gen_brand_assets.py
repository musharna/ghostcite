#!/usr/bin/env python3
"""Render ghostcite brand/visual assets (deterministic, pure Pillow, no TTY).

Outputs into ``examples/assets/``:
  * ``logo.png``        — horizontal ghost mark + wordmark (transparent)
  * ``social.png``      — 1280x640 GitHub social-preview / OG card
  * ``demo-clean.png``  — terminal card showing a clean (no-findings) run

Run::

    python3 examples/gen_brand_assets.py

Requires the optional ``viz`` group (``pip install ghostcite[viz]`` / ``pillow``).
"""

from __future__ import annotations

import glob
import os

from PIL import Image, ImageDraw, ImageFont

FONTDIR = os.path.expanduser("~/.local/share/fonts")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
_FALLBACK_GLYPHS = "↳"

# Shared palette (One Dark-ish — matches gen_demo_card.py).
BG = (13, 17, 23)
WIN_BG = (30, 33, 39)
TITLEBAR = (40, 44, 52)
FG = (220, 223, 228)
DIM = (118, 124, 138)
GREEN = (152, 195, 121)
RED = (224, 108, 117)
MAGENTA = (198, 120, 221)
CYAN = (86, 182, 194)
GHOST = (231, 234, 242)
DOT_RED = (255, 95, 86)
DOT_YEL = (255, 189, 46)
DOT_GRN = (39, 201, 63)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _font(pattern: str, size: int) -> ImageFont.FreeTypeFont:
    hits = sorted(glob.glob(os.path.join(FONTDIR, pattern)))
    return ImageFont.truetype(hits[0] if hits else _DEJAVU, size)


def _draw_ghost(d: ImageDraw.ImageDraw, cx: int, top: int, w: int, h: int, fill) -> None:
    """A clean rounded ghost: domed head, body, scalloped hem, two eyes."""
    left, right = cx - w // 2, cx + w // 2
    dome_h = int(w * 0.62)
    # Domed head.
    d.pieslice([left, top, right, top + dome_h * 2], 180, 360, fill=fill)
    # Hem: downward half-circle bumps with empty notches between them, so it
    # renders cleanly on a transparent logo AND a dark card (no dark "teeth").
    n = 4
    seg = w / n
    bump_r = seg / 2
    by = top + h - bump_r  # chord line of the bumps; lowest point = top + h
    d.rectangle([left, top + dome_h, right, int(by)], fill=fill)
    for i in range(n):
        x0 = left + i * seg
        d.pieslice([x0, by - bump_r, x0 + seg, by + bump_r], 0, 180, fill=fill)
    # Eyes.
    eye_r = max(4, w // 14)
    ey = top + int(dome_h * 0.95)
    for ex in (cx - int(w * 0.20), cx + int(w * 0.20)):
        d.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], fill=(30, 33, 39))


def make_logo() -> str:
    # Self-contained dark banner so it reads on BOTH GitHub light and dark
    # themes (a near-white ghost on a transparent bg would vanish on light).
    W, H = 760, 220
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=24, fill=BG)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=24, outline=(40, 44, 52), width=2)
    gx = 100
    _draw_ghost(d, gx, 46, 96, 120, GHOST)
    word = _font("JetBrainsMonoNLNerdFont-Bold.ttf", 76)
    tag = _font("JetBrainsMonoNLNerdFont-Regular.ttf", 26)
    tx = 176
    d.text((tx, 62), "ghost", font=word, fill=GHOST)
    gw = d.textlength("ghost", font=word)
    d.text((tx + gw, 62), "cite", font=word, fill=CYAN)
    d.text((tx + 4, 156), "right DOI · wrong author", font=tag, fill=DIM)
    out = os.path.join(ASSETS, "logo.png")
    img.save(out)
    return f"{out} ({W}x{H})"


def make_social() -> str:
    W, H = 1280, 640
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # Subtle top accent bar.
    d.rectangle([0, 0, W, 8], fill=MAGENTA)
    _draw_ghost(d, 150, 96, 150, 188, GHOST)
    word = _font("JetBrainsMonoNLNerdFont-Bold.ttf", 92)
    d.text((250, 120), "ghost", font=word, fill=GHOST)
    gw = d.textlength("ghost", font=word)
    d.text((250 + gw, 120), "cite", font=word, fill=CYAN)
    head = _font("JetBrainsMonoNLNerdFont-Bold.ttf", 46)
    sub = _font("JetBrainsMonoNLNerdFont-Regular.ttf", 30)
    mono = _font("JetBrainsMonoNLNerdFont-Regular.ttf", 28)
    d.text((96, 286), "Catch ghost citations.", font=head, fill=FG)
    d.text((96, 348), "Right DOI, wrong author — deterministic, no-LLM.", font=sub, fill=DIM)
    # Sample finding line.
    sy = 430
    d.text((96, sy), "✗ A", font=mono, fill=RED)
    d.text((96 + d.textlength("✗ A  ", font=mono), sy), "Li (2024)", font=mono, fill=FG)
    d.text(
        (96 + d.textlength("✗ A  Li (2024)   ", font=mono), sy),
        "→  CrossRef says Chen",
        font=mono,
        fill=DIM,
    )
    # Niche chips.
    chips = ["deterministic", "no-LLM", "CrossRef + PubMed", "CLI"]
    cx = 96
    chip_f = _font("JetBrainsMonoNLNerdFont-Medium.ttf", 24)
    for c in chips:
        tw = d.textlength(c, font=chip_f)
        d.rounded_rectangle([cx, 516, cx + tw + 32, 560], radius=22, fill=(40, 44, 52))
        d.text((cx + 16, 524), c, font=chip_f, fill=CYAN)
        cx += tw + 32 + 16
    url = _font("JetBrainsMonoNLNerdFont-Regular.ttf", 24)
    d.text((96, 590), "github.com/musharna/ghostcite", font=url, fill=DIM)
    out = os.path.join(ASSETS, "social.png")
    img.save(out)
    return f"{out} ({W}x{H})"


def _terminal_card(lines, title, outname) -> str:
    fsize = 17
    mono = _font("JetBrainsMonoNLNerdFont-Regular.ttf", fsize)
    dejavu = ImageFont.truetype(_DEJAVU, fsize)
    titlefont = _font("JetBrainsMonoNLNerdFont-Medium.ttf", 15)
    line_h, pad_x, top_chrome, pad_top, pad_bottom = 27, 30, 48, 20, 22
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    cell = probe.textlength("M", font=mono)
    max_chars = max(sum(len(t) for t, _ in segs) for segs in lines)
    win_w = int(cell * max_chars) + 2 * pad_x
    win_h = top_chrome + pad_top + line_h * len(lines) + pad_bottom
    margin = 28
    img = Image.new("RGB", (win_w + 2 * margin, win_h + 2 * margin), BG)
    d = ImageDraw.Draw(img)
    x0, y0 = margin, margin
    x1, y1 = margin + win_w, margin + win_h
    rad = 12
    d.rounded_rectangle([x0, y0, x1, y1], radius=rad, fill=WIN_BG)
    d.rounded_rectangle([x0, y0, x1, y0 + top_chrome], radius=rad, fill=TITLEBAR)
    d.rectangle([x0, y0 + top_chrome - rad, x1, y0 + top_chrome], fill=TITLEBAR)
    d.rectangle([x0, y0 + top_chrome, x1, y0 + top_chrome + rad], fill=WIN_BG)
    cy = y0 + top_chrome // 2
    for i, col in enumerate((DOT_RED, DOT_YEL, DOT_GRN)):
        cxx = x0 + 22 + i * 24
        d.ellipse([cxx - 6, cy - 6, cxx + 6, cy + 6], fill=col)
    tw = d.textlength(title, font=titlefont)
    d.text((x0 + (win_w - tw) / 2, cy - 9), title, font=titlefont, fill=DIM)
    ty = y0 + top_chrome + pad_top
    for segs in lines:
        tx = x0 + pad_x
        for text, color in segs:
            for ch in text:
                fnt = dejavu if ch in _FALLBACK_GLYPHS else mono
                d.text((tx, ty), ch, font=fnt, fill=color)
                tx += cell
        ty += line_h
    out = os.path.join(ASSETS, outname)
    img.save(out)
    return f"{out} ({img.width}x{img.height})"


def make_clean_card() -> str:
    lines = [
        [("$ ", GREEN), ("ghostcite paper/references.bib", FG)],
        [("ghostcite: 42 entries, 41 with DOIs", FG)],
        [("  0 findings — clean", GREEN)],
        [("$ ", GREEN), ("echo $?", FG)],
        [("0", FG)],
    ]
    return _terminal_card(lines, "ghostcite — clean run", "demo-clean.png")


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    for fn in (make_logo, make_social, make_clean_card):
        print("wrote", fn())


if __name__ == "__main__":
    main()
