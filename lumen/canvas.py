"""The drawing API every scene uses.

``Canvas`` is a thin, pixel-oriented wrapper over a Pillow RGB image sized to the
panel. It exposes just the primitives that make sense at 64x32 (pixels, lines,
rects, bitmap text, blits) plus the one output that matters: ``to_rgb565()``,
the exact bytes the M4 expects on the wire.

Design choice: we draw directly rather than rasterising from an external package
(matplotlib/SVG/HTML). At 64x32, anti-aliasing smears text into mush; crisp
pixel control is the whole game. See ``fonts.py`` for the bitmap fonts.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from . import HEIGHT, WIDTH
from .fonts import BitmapFont, Color, get_font

BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)


class Canvas:
    def __init__(self, width: int = WIDTH, height: int = HEIGHT, bg: Color = BLACK):
        self.width = width
        self.height = height
        self._image_obj = Image.new("RGB", (width, height), bg)
        self._px = self._image_obj.load()

    # -- primitives ---------------------------------------------------------
    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def pixel(self, x: int, y: int, color: Color) -> None:
        if self._in_bounds(x, y):
            self._px[x, y] = color

    def clear(self, color: Color = BLACK) -> None:
        self._image_obj.paste(color, (0, 0, self.width, self.height))
        self._px = self._image_obj.load()

    def hline(self, x: int, y: int, length: int, color: Color) -> None:
        for i in range(length):
            self.pixel(x + i, y, color)

    def vline(self, x: int, y: int, length: int, color: Color) -> None:
        for i in range(length):
            self.pixel(x, y + i, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        # Integer Bresenham — exact pixels, no AA.
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(
        self, x: int, y: int, w: int, h: int, color: Color, fill: bool = False
    ) -> None:
        if fill:
            for yy in range(y, y + h):
                self.hline(x, yy, w, color)
        else:
            self.hline(x, y, w, color)
            self.hline(x, y + h - 1, w, color)
            self.vline(x, y, h, color)
            self.vline(x + w - 1, y, h, color)

    # -- text ---------------------------------------------------------------
    def text(
        self,
        x: int,
        y: int,
        text: str,
        color: Color = WHITE,
        font: str | BitmapFont = "5x8",
    ) -> int:
        f = font if isinstance(font, BitmapFont) else get_font(font)
        return f.draw(self.pixel, x, y, text, color)

    def text_centered(
        self,
        y: int,
        text: str,
        color: Color = WHITE,
        font: str | BitmapFont = "5x8",
    ) -> int:
        f = font if isinstance(font, BitmapFont) else get_font(font)
        x = (self.width - f.text_width(text)) // 2
        return f.draw(self.pixel, x, y, text, color)

    def text_right(
        self,
        x_right: int,
        y: int,
        text: str,
        color: Color = WHITE,
        font: str | BitmapFont = "5x8",
    ) -> int:
        f = font if isinstance(font, BitmapFont) else get_font(font)
        return f.draw(self.pixel, x_right - f.text_width(text), y, text, color)

    def blit(self, image: Image.Image, x: int, y: int) -> None:
        """Paste an RGB(A) image at (x, y). Alpha is honoured if present."""
        if image.mode == "RGBA":
            self._image_obj.paste(image, (x, y), image)
        else:
            self._image_obj.paste(image.convert("RGB"), (x, y))
        self._px = self._image_obj.load()

    # -- output -------------------------------------------------------------
    def image(self) -> Image.Image:
        """Return a copy of the underlying RGB image."""
        return self._image_obj.copy()

    def to_rgb565(self) -> bytes:
        """Encode to the M4 wire format: big-endian RGB565, row-major.

        Layout matches the protocol exactly:
        ``[pixel(0,0)][pixel(1,0)]...[pixel(63,31)]`` = 2 bytes x 64 x 32.
        """
        arr = np.asarray(self._image_obj, dtype=np.uint16)  # (H, W, 3)
        r = arr[..., 0] >> 3
        g = arr[..., 1] >> 2
        b = arr[..., 2] >> 3
        rgb565 = (r << 11) | (g << 5) | b
        return rgb565.astype(">u2").tobytes()

    def to_png(self, scale: int = 1) -> bytes:
        """PNG bytes, optionally nearest-neighbour upscaled for previews/tests."""
        import io

        img = self._image_obj
        if scale != 1:
            img = img.resize((self.width * scale, self.height * scale), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def from_rgb565(data: bytes, width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    """Inverse of ``Canvas.to_rgb565`` — handy for tests and frame inspection."""
    vals = np.frombuffer(data, dtype=">u2").reshape(height, width).astype(np.uint16)
    r = ((vals >> 11) & 0x1F) << 3
    g = ((vals >> 5) & 0x3F) << 2
    b = (vals & 0x1F) << 3
    rgb = np.dstack([r, g, b]).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")
