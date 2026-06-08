#!/usr/bin/env python3
"""Render an animated terminal demo GIF for the ghostcite README.

Pure Pillow, no TTY / no Node. Types the ``ghostcite`` command, then reveals the
report line by line, on the same dark terminal card as ``gen_demo_card.py``.

Run::

    python3 examples/gen_demo_anim.py

Output: ``examples/assets/demo.gif``. Requires the optional ``viz`` group.
"""

from __future__ import annotations

import glob
import os

from PIL import Image, ImageDraw, ImageFont

FONTDIR = os.path.expanduser("~/.local/share/fonts")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
_FALLBACK_GLYPHS = "↳"

BG = (13, 17, 23)
WIN_BG = (30, 33, 39)
TITLEBAR = (40, 44, 52)
FG = (220, 223, 228)
DIM = (118, 124, 138)
GREEN = (152, 195, 121)
RED = (224, 108, 117)
MAGENTA = (198, 120, 221)
CYAN = (86, 182, 194)
DOT_RED, DOT_YEL, DOT_GRN = (255, 95, 86), (255, 189, 46), (39, 201, 63)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Each line is a list of (text, color) segments. Line 0 is the typed command.
CMD = "ghostcite refs.bib --cross-check pubmed"
LINES = [
    [("$ ", GREEN), (CMD, FG)],
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
    [("  2 A · 1 B · 1 R  →  ", FG), ("exit 1", CYAN)],
]


def _font(pattern, size):
    hits = sorted(glob.glob(os.path.join(FONTDIR, pattern)))
    return ImageFont.truetype(hits[0] if hits else _DEJAVU, size)


def main() -> None:
    fsize = 17
    mono = _font("JetBrainsMonoNLNerdFont-Regular.ttf", fsize)
    dejavu = ImageFont.truetype(_DEJAVU, fsize)
    titlefont = _font("JetBrainsMonoNLNerdFont-Medium.ttf", 15)
    line_h, pad_x, top_chrome, pad_top, pad_bottom = 27, 30, 48, 20, 22
    margin = 28

    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    cell = probe.textlength("M", font=mono)
    max_chars = max(sum(len(t) for t, _ in segs) for segs in LINES)
    win_w = int(cell * max_chars) + 2 * pad_x
    win_h = top_chrome + pad_top + line_h * len(LINES) + pad_bottom
    W, H = win_w + 2 * margin, win_h + 2 * margin

    def frame(visible, cmd_chars, cursor):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = margin, margin, margin + win_w, margin + win_h
        rad = 12
        d.rounded_rectangle([x0, y0, x1, y1], radius=rad, fill=WIN_BG)
        d.rounded_rectangle([x0, y0, x1, y0 + top_chrome], radius=rad, fill=TITLEBAR)
        d.rectangle([x0, y0 + top_chrome - rad, x1, y0 + top_chrome], fill=TITLEBAR)
        d.rectangle([x0, y0 + top_chrome, x1, y0 + top_chrome + rad], fill=WIN_BG)
        cy = y0 + top_chrome // 2
        for i, col in enumerate((DOT_RED, DOT_YEL, DOT_GRN)):
            cxx = x0 + 22 + i * 24
            d.ellipse([cxx - 6, cy - 6, cxx + 6, cy + 6], fill=col)
        title = "ghostcite — refs.bib"
        tw = d.textlength(title, font=titlefont)
        d.text((x0 + (win_w - tw) / 2, cy - 9), title, font=titlefont, fill=DIM)

        ty = y0 + top_chrome + pad_top
        for li in range(visible + 1):
            if li >= len(LINES):
                break
            segs = LINES[li]
            tx = x0 + pad_x
            chars_drawn = 0
            for text, color in segs:
                draw_text = text
                if li == 0 and color == FG:  # the command being typed
                    draw_text = text[:cmd_chars]
                for ch in draw_text:
                    fnt = dejavu if ch in _FALLBACK_GLYPHS else mono
                    d.text((tx, ty), ch, font=fnt, fill=color)
                    tx += cell
                    chars_drawn += 1
            if li == 0 and cursor:
                d.rectangle([tx + 1, ty + 2, tx + cell - 1, ty + fsize + 4], fill=FG)
            ty += line_h
        return img

    frames, durations = [], []

    # Phase 1: type the command (3 chars/frame), blinking cursor.
    step = 3
    for k in range(0, len(CMD) + 1, step):
        frames.append(frame(0, k, (k // step) % 2 == 0))
        durations.append(70)
    frames.append(frame(0, len(CMD), True))
    durations.append(450)  # pause before "running"

    # Phase 2: reveal output lines one at a time.
    for li in range(1, len(LINES)):
        frames.append(frame(li, len(CMD), False))
        durations.append(420)

    # Hold the final frame.
    frames.append(frame(len(LINES) - 1, len(CMD), False))
    durations.append(2600)

    out = os.path.join(ASSETS, "demo.gif")
    os.makedirs(ASSETS, exist_ok=True)
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    kb = os.path.getsize(out) / 1024
    print(f"wrote {out} ({W}x{H}, {len(frames)} frames, {kb:.0f} KB)")


if __name__ == "__main__":
    main()
