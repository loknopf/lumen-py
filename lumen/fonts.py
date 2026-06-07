"""Minimal BDF bitmap-font support.

These are pixel fonts (no anti-aliasing), which is exactly what a 64x32 LED
matrix wants: every glyph maps to crisp, fully-on or fully-off pixels. That also
makes rendering deterministic, which the golden-image tests rely on.

Three public-domain Misc-Fixed fonts are vendored under ``assets/fonts``:

    "4x6"  - tiny, for dense labels
    "5x8"  - the workhorse body font
    "6x13" - larger, for headline numbers

Usage::

    font = get_font("5x8")
    font.draw(set_pixel, x, y, "HELLO", (255, 255, 255))
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Callable, Iterable

Color = tuple[int, int, int]
SetPixel = Callable[[int, int, Color], None]


@dataclass(frozen=True)
class Glyph:
    """A single rasterised character.

    ``rows`` is a list of bbh rows, each a list of bbw 0/1 bits, top row first.
    ``advance`` is how far the pen moves right after drawing (device width).
    ``xoff`` / ``yoff`` are the BDF bounding-box offsets for this glyph.
    """

    rows: list[list[int]]
    advance: int
    xoff: int
    yoff: int
    width: int
    height: int


class BitmapFont:
    def __init__(self, fbb: tuple[int, int, int, int], glyphs: dict[int, Glyph]):
        # FONTBOUNDINGBOX: width, height, x-offset, y-offset
        self.fbb_w, self.fbb_h, self.fbb_xoff, self.fbb_yoff = fbb
        self.glyphs = glyphs
        # Distance from the top of the cell down to the baseline.
        self.baseline = self.fbb_h + self.fbb_yoff

    @property
    def height(self) -> int:
        return self.fbb_h

    def _glyph(self, ch: str) -> Glyph | None:
        return self.glyphs.get(ord(ch)) or self.glyphs.get(ord(" "))

    def text_width(self, text: str) -> int:
        """Pixel advance of ``text`` (sum of per-glyph device widths)."""
        total = 0
        for ch in text:
            g = self._glyph(ch)
            if g is not None:
                total += g.advance
        return total

    def iter_pixels(self, x: int, y: int, text: str) -> Iterable[tuple[int, int]]:
        """Yield absolute (px, py) for every lit pixel of ``text``.

        ``(x, y)`` is the top-left of the text cell, which is the intuitive
        anchor for layout on a tiny panel.
        """
        pen = x
        for ch in text:
            g = self._glyph(ch)
            if g is None:
                continue
            # Translate BDF (baseline / y-up) coordinates to top-left / y-down.
            gx0 = pen + (g.xoff - self.fbb_xoff)
            gy0 = y + (self.fbb_h + self.fbb_yoff) - (g.yoff + g.height)
            for r, row in enumerate(g.rows):
                for c, bit in enumerate(row):
                    if bit:
                        yield gx0 + c, gy0 + r
            pen += g.advance

    def draw(self, set_pixel: SetPixel, x: int, y: int, text: str, color: Color) -> int:
        """Draw ``text`` via ``set_pixel`` callbacks. Returns the end pen x."""
        for px, py in self.iter_pixels(x, y, text):
            set_pixel(px, py, color)
        return x + self.text_width(text)


def _parse_bdf(text: str) -> BitmapFont:
    fbb = (0, 0, 0, 0)
    glyphs: dict[int, Glyph] = {}
    lines = text.splitlines()
    i = 0
    enc = dwidth = bbx = None
    bitmap: list[str] = []
    while i < len(lines):
        parts = lines[i].split()
        kw = parts[0] if parts else ""
        if kw == "FONTBOUNDINGBOX":
            fbb = tuple(int(v) for v in parts[1:5])  # type: ignore[assignment]
        elif kw == "STARTCHAR":
            enc = dwidth = bbx = None
            bitmap = []
        elif kw == "ENCODING":
            enc = int(parts[1])
        elif kw == "DWIDTH":
            dwidth = (int(parts[1]), int(parts[2]))
        elif kw == "BBX":
            bbx = tuple(int(v) for v in parts[1:5])
        elif kw == "BITMAP":
            i += 1
            while i < len(lines) and not lines[i].startswith("ENDCHAR"):
                bitmap.append(lines[i].strip())
                i += 1
            if enc is not None and bbx is not None:
                glyphs[enc] = _build_glyph(bbx, dwidth, bitmap)
        i += 1
    return BitmapFont(fbb, glyphs)


def _build_glyph(bbx, dwidth, bitmap) -> Glyph:
    bbw, bbh, bbxoff, bbyoff = bbx
    rows: list[list[int]] = []
    for hexrow in bitmap:
        if not hexrow:
            continue
        width_bits = len(hexrow) * 4
        val = int(hexrow, 16)
        rows.append([(val >> (width_bits - 1 - c)) & 1 for c in range(bbw)])
    advance = dwidth[0] if dwidth else bbw
    return Glyph(rows=rows, advance=advance, xoff=bbxoff, yoff=bbyoff, width=bbw, height=bbh)


@lru_cache(maxsize=None)
def get_font(name: str) -> BitmapFont:
    """Load a vendored font by name (e.g. ``"5x8"``). Cached after first load."""
    resource = files("lumen.assets.fonts").joinpath(f"{name}.bdf")
    return _parse_bdf(resource.read_text(encoding="latin-1"))
