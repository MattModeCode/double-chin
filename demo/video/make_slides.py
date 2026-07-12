#!/usr/bin/env python3
"""Render all slide PNGs (1920x1080) for the Myna demo and walkthrough videos.

Usage: .venv/bin/python demo/video/make_slides.py

Writes PNGs into demo/video/slides/. Pure PIL, no network access at runtime
(fonts are pre-downloaded into assets/brand/fonts/).
"""
from __future__ import annotations

import pathlib
import textwrap

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FONT_DIR = REPO_ROOT / "assets" / "brand" / "fonts"
SLIDES_DIR = pathlib.Path(__file__).resolve().parent / "slides"
SLIDES_DIR.mkdir(parents=True, exist_ok=True)

FONT_REGULAR_PATH = FONT_DIR / "JetBrainsMono-Regular.ttf"
FONT_MEDIUM_PATH = FONT_DIR / "JetBrainsMono-Medium.ttf"
FALLBACK_FONT_PATH = pathlib.Path("/System/Library/Fonts/Menlo.ttc")

# ---------------------------------------------------------------------------
# Brand tokens (MashuAI system, held per ticket)
# ---------------------------------------------------------------------------
COLOR_BG = "#0a0a0f"
COLOR_CARD = "#0f0f14"
COLOR_LOGO_SQUARE = "#0f0e13"
COLOR_LOGO_BARS = "#e1e0e0"
COLOR_TEXT_PRIMARY = "#e2e8f0"
COLOR_TEXT_SECONDARY = "#94a3b8"
COLOR_SUCCESS = "#22c55e"

W, H = 1920, 1080
MARGIN = 140  # >= 120 px per spec


def _load_font(path: pathlib.Path, size: int, fallback_index: int = 0) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size)
    if FALLBACK_FONT_PATH.exists():
        return ImageFont.truetype(str(FALLBACK_FONT_PATH), size, index=fallback_index)
    raise FileNotFoundError(f"No usable font found for {path} and no fallback available")


def font_regular(size: int) -> ImageFont.FreeTypeFont:
    return _load_font(FONT_REGULAR_PATH, size)


def font_medium(size: int) -> ImageFont.FreeTypeFont:
    return _load_font(FONT_MEDIUM_PATH, size)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def new_canvas() -> Image.Image:
    return Image.new("RGB", (W, H), COLOR_BG)


def draw_caption(draw: ImageDraw.ImageDraw) -> None:
    """Small caption bottom-left on every non-title slide."""
    f = font_regular(36)
    draw.text((MARGIN, H - MARGIN - 36), "myna — local voice clone", font=f, fill=COLOR_TEXT_SECONDARY)


def draw_heading(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, size: int = 68) -> int:
    f = font_medium(size)
    draw.text((x, y), text, font=f, fill=COLOR_TEXT_PRIMARY)
    bbox = draw.textbbox((x, y), text, font=f)
    return bbox[3]  # bottom y


def draw_body_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    size: int = 44,
    color: str = COLOR_TEXT_SECONDARY,
    max_width_chars: int = 62,
    line_spacing: int = 20,
    font_fn=font_regular,
) -> int:
    """Wrap text to max_width_chars and draw it, returning the bottom y."""
    f = font_fn(size)
    wrapped = textwrap.wrap(text, width=max_width_chars)
    cur_y = y
    for line in wrapped:
        draw.text((x, cur_y), line, font=f, fill=color)
        bbox = draw.textbbox((x, cur_y), line, font=f)
        cur_y = bbox[3] + line_spacing
    return cur_y


def rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_logo_mark(canvas: Image.Image, cx: int, cy: int, side: int) -> None:
    """Rounded-corner square containing 5 symmetric vertical bars (waveform mark)."""
    draw = ImageDraw.Draw(canvas)
    half = side // 2
    box = (cx - half, cy - half, cx + half, cy + half)
    radius = int(side * 0.18)
    rounded_rect(draw, box, radius=radius, fill=COLOR_LOGO_SQUARE)

    inner_h = side * 0.62  # inner area the bars occupy vertically
    bar_w = side * 0.09
    gap = side * 0.07
    heights_rel = [0.32, 0.62, 1.0, 0.62, 0.32]
    n = len(heights_rel)
    total_w = n * bar_w + (n - 1) * gap
    start_x = cx - total_w / 2

    for i, hrel in enumerate(heights_rel):
        bar_h = inner_h * hrel
        bx0 = start_x + i * (bar_w + gap)
        bx1 = bx0 + bar_w
        by0 = cy - bar_h / 2
        by1 = cy + bar_h / 2
        bar_radius = bar_w / 2
        rounded_rect(draw, (bx0, by0, bx1, by1), radius=bar_radius, fill=COLOR_LOGO_BARS)


def draw_wordmark(canvas: Image.Image, x: int, y: int, size: int = 96, centered_around_x: int | None = None,
                   tagline: str | None = None, tagline_size: int = 40) -> int:
    """Draw 'myna' wordmark (+ optional tagline below). Returns bottom y used."""
    draw = ImageDraw.Draw(canvas)
    f = font_medium(size)
    text = "myna"
    if centered_around_x is not None:
        bbox = draw.textbbox((0, 0), text, font=f)
        tw = bbox[2] - bbox[0]
        x = centered_around_x - tw // 2
    draw.text((x, y), text, font=f, fill=COLOR_TEXT_PRIMARY)
    bbox = draw.textbbox((x, y), text, font=f)
    bottom = bbox[3]
    if tagline:
        tf = font_regular(tagline_size)
        ty = bottom + 28
        if centered_around_x is not None:
            tbbox = draw.textbbox((0, 0), tagline, font=tf)
            tw2 = tbbox[2] - tbbox[0]
            tx = centered_around_x - tw2 // 2
        else:
            tx = x
        draw.text((tx, ty), tagline, font=tf, fill=COLOR_TEXT_SECONDARY)
        tbbox = draw.textbbox((tx, ty), tagline, font=tf)
        bottom = tbbox[3]
    return bottom


def draw_terminal_card(canvas: Image.Image, box, lines: list[str], font_size: int = 40, pad: int = 48) -> None:
    """Draw a terminal-style card (#0f0f14 rounded rect) with monospace lines inside."""
    draw = ImageDraw.Draw(canvas)
    rounded_rect(draw, box, radius=16, fill=COLOR_CARD)
    f = font_regular(font_size)
    x0, y0, x1, y1 = box
    cur_y = y0 + pad
    for line in lines:
        draw.text((x0 + pad, cur_y), line, font=f, fill=COLOR_TEXT_PRIMARY)
        bbox = draw.textbbox((x0 + pad, cur_y), line, font=f)
        cur_y = bbox[3] + 22


def save(canvas: Image.Image, name: str) -> None:
    out = SLIDES_DIR / f"{name}.png"
    canvas.save(out, "PNG")
    print(f"wrote {out}")


# ---------------------------------------------------------------------------
# DEMO slides
# ---------------------------------------------------------------------------

def slide_d1() -> None:
    """Title: logo mark 280px + 'myna' + tagline, centred."""
    c = new_canvas()
    cx = W // 2
    logo_side = 280
    logo_cy = H // 2 - 140
    draw_logo_mark(c, cx, logo_cy, logo_side)
    word_y = logo_cy + logo_side // 2 + 64
    draw_wordmark(c, 0, word_y, size=110, centered_around_x=cx, tagline="Your voice, on script.", tagline_size=44)
    save(c, "d1")


def slide_d2() -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "The reference", MARGIN, MARGIN)
    draw_body_lines(
        draw,
        "17 seconds of a stand-in voice. CMU Arctic speaker bdl.",
        MARGIN,
        y + 56,
        size=46,
    )
    draw_caption(draw)
    save(c, "d2")


def slide_d3() -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "The script", MARGIN, MARGIN)
    p1 = (
        "This is not the person you think it is. This voice was generated "
        "by Myna, on a laptop, from about seventeen seconds of reference audio."
    )
    p2 = (
        "Here is how it works. You enrol a voice from a short recording. "
        "You hand Myna a script — this script, in fact. It splits the "
        "script into sentences, conditions the model on your reference, and "
        "stitches the audio back together."
    )
    cur_y = y + 60
    cur_y = draw_body_lines(draw, f"“{p1}”", MARGIN, cur_y, size=42, max_width_chars=64, line_spacing=16)
    cur_y = draw_body_lines(draw, f"“{p2}”", MARGIN, cur_y + 30, size=42, max_width_chars=64, line_spacing=16)
    draw_caption(draw)
    save(c, "d3")


def slide_d4() -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "One command", MARGIN, MARGIN)
    card_box = (MARGIN, y + 70, W - MARGIN, y + 70 + 340)
    lines = [
        "$ myna say --script demo-script.txt \\",
        "    --voice standin -o out.wav --verify",
    ]
    draw_terminal_card(c, card_box, lines, font_size=40)
    draw_caption(draw)
    save(c, "d4")


def slide_d5() -> None:
    """Lower half left empty for a waveform overlay added at assembly time."""
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "The clone", MARGIN, MARGIN)
    draw_body_lines(
        draw,
        "Generated on this laptop. Nothing left the machine.",
        MARGIN,
        y + 56,
        size=46,
    )
    draw_caption(draw)
    save(c, "d5")


def slide_d6() -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "Verified", MARGIN, MARGIN)

    big_f = font_medium(140)
    big_text = "0.954"
    draw.text((MARGIN, y + 60), big_text, font=big_f, fill=COLOR_TEXT_PRIMARY)
    bbox = draw.textbbox((MARGIN, y + 60), big_text, font=big_f)
    big_bottom = bbox[3]

    draw_body_lines(
        draw,
        "speaker similarity vs reference — strong match (same-speaker threshold 0.75)",
        MARGIN,
        big_bottom + 40,
        size=42,
        max_width_chars=58,
    )

    # PASS chip
    chip_f = font_medium(34)
    chip_text = "PASS"
    chip_pad_x, chip_pad_y = 28, 14
    tb = draw.textbbox((0, 0), chip_text, font=chip_f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    chip_x0 = MARGIN
    chip_y0 = big_bottom + 40 + 150
    chip_box = (chip_x0, chip_y0, chip_x0 + tw + chip_pad_x * 2, chip_y0 + th + chip_pad_y * 2)
    rounded_rect(draw, chip_box, radius=8, outline=COLOR_SUCCESS, width=3)
    draw.text((chip_x0 + chip_pad_x, chip_y0 + chip_pad_y - tb[1]), chip_text, font=chip_f, fill=COLOR_SUCCESS)

    draw_caption(draw)
    save(c, "d6")


# ---------------------------------------------------------------------------
# WALKTHROUGH slides
# ---------------------------------------------------------------------------

def slide_w1() -> None:
    c = new_canvas()
    cx = W // 2
    logo_side = 220
    logo_cy = H // 2 - 200
    draw_logo_mark(c, cx, logo_cy, logo_side)
    word_y = logo_cy + logo_side // 2 + 50
    bottom = draw_wordmark(c, 0, word_y, size=64, centered_around_x=cx)
    draw = ImageDraw.Draw(c)
    title_f = font_medium(72)
    title = "How Myna works"
    tb = draw.textbbox((0, 0), title, font=title_f)
    tw = tb[2] - tb[0]
    draw.text((cx - tw // 2, bottom + 40), title, font=title_f, fill=COLOR_TEXT_PRIMARY)
    tb2 = draw.textbbox((cx - tw // 2, bottom + 40), title, font=title_f)

    sub_f = font_regular(42)
    sub = "Narrated by the clone itself."
    sb = draw.textbbox((0, 0), sub, font=sub_f)
    sw = sb[2] - sb[0]
    draw.text((cx - sw // 2, tb2[3] + 36), sub, font=sub_f, fill=COLOR_TEXT_SECONDARY)
    save(c, "w1")


def _walkthrough_slide(name: str, heading: str, support_lines: list[str], body_size: int = 44) -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, heading, MARGIN, MARGIN)
    cur_y = y + 60
    for line in support_lines:
        cur_y = draw_body_lines(draw, line, MARGIN, cur_y, size=body_size, max_width_chars=60, line_spacing=16)
        cur_y += 26
    draw_caption(draw)
    save(c, name)


def slide_w2() -> None:
    _walkthrough_slide(
        "w2",
        "What it is",
        [
            "A command line tool that clones a voice from a few seconds of audio.",
            "Enrol once, then hand it any script — it reads that script back, entirely on your machine.",
        ],
    )


def slide_w3() -> None:
    _walkthrough_slide(
        "w3",
        "No training, just conditioning",
        [
            "Myna conditions a pretrained speech model on your reference clip.",
            "Enrolment prepares your best fifteen seconds of audio; the model does the rest at generation time.",
        ],
    )


def slide_w4() -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "The pipeline", MARGIN, MARGIN)
    card_box = (MARGIN, y + 70, W - MARGIN, y + 70 + 220)
    lines = ["script -> chunk -> condition (once) -> generate (MPS) -> stitch -> verify"]
    draw_terminal_card(c, card_box, lines, font_size=34)
    draw_caption(draw)
    save(c, "w4")


def slide_w5() -> None:
    _walkthrough_slide(
        "w5",
        "Clone your own voice",
        [
            "docs/recording-scripts.md — two public-domain scripts, about 15 minutes.",
            "Read them into any recorder in a quiet room, then enrol.",
        ],
    )


def slide_w6() -> None:
    _walkthrough_slide(
        "w6",
        "Trust but verify",
        [
            "A resemblyzer speaker embedding compares clone against reference by cosine similarity.",
            "Threshold 0.75 marks a same-speaker match.",
        ],
    )


def slide_w7() -> None:
    c = new_canvas()
    draw = ImageDraw.Draw(c)
    y = draw_heading(draw, "Honest limits", MARGIN, MARGIN)
    bullets = [
        "mirrors timbre and pace, not vocabulary",
        "register outside the reference needs re-recording",
        "refuses to score silence",
    ]
    cur_y = y + 70
    f = font_regular(44)
    dot_f = font_regular(44)
    for b in bullets:
        draw.text((MARGIN, cur_y), "—", font=dot_f, fill=COLOR_TEXT_SECONDARY)
        wrapped = textwrap.wrap(b, width=56)
        line_y = cur_y
        for i, line in enumerate(wrapped):
            draw.text((MARGIN + 70, line_y), line, font=f, fill=COLOR_TEXT_SECONDARY)
            bbox = draw.textbbox((MARGIN + 70, line_y), line, font=f)
            line_y = bbox[3] + 12
        cur_y = line_y + 34
    draw_caption(draw)
    save(c, "w7")


def slide_w8() -> None:
    c = new_canvas()
    cx = W // 2
    logo_side = 220
    logo_cy = H // 2 - 160
    draw_logo_mark(c, cx, logo_cy, logo_side)
    word_y = logo_cy + logo_side // 2 + 50
    bottom = draw_wordmark(c, 0, word_y, size=90, centered_around_x=cx, tagline="Your voice, on script.", tagline_size=42)
    draw = ImageDraw.Draw(c)
    sub_f = font_regular(38)
    sub = "MIT-licensed engine. Local only."
    sb = draw.textbbox((0, 0), sub, font=sub_f)
    sw = sb[2] - sb[0]
    draw.text((cx - sw // 2, bottom + 40), sub, font=sub_f, fill=COLOR_TEXT_SECONDARY)
    save(c, "w8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    slide_d1()
    slide_d2()
    slide_d3()
    slide_d4()
    slide_d5()
    slide_d6()
    slide_w1()
    slide_w2()
    slide_w3()
    slide_w4()
    slide_w5()
    slide_w6()
    slide_w7()
    slide_w8()
    print("all slides written to", SLIDES_DIR)


if __name__ == "__main__":
    main()
