"""Tiny hand-drawn icons. Everything is primitives so it stays crisp at 64x32."""

from __future__ import annotations

from ..canvas import Canvas
from ..fonts import Color

YELLOW: Color = (255, 200, 40)
CLOUD: Color = (180, 190, 200)
RAIN: Color = (80, 150, 255)
SNOW: Color = (220, 235, 255)


def _disc(c: Canvas, cx: int, cy: int, r: int, color: Color) -> None:
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                c.pixel(cx + dx, cy + dy, color)


def sun(c: Canvas, x: int, y: int) -> None:
    cx, cy = x + 7, y + 7
    for ang in range(0, 360, 45):
        import math

        dx = round(6 * math.cos(math.radians(ang)))
        dy = round(6 * math.sin(math.radians(ang)))
        c.pixel(cx + dx, cy + dy, YELLOW)
    _disc(c, cx, cy, 3, YELLOW)


def _cloud(c: Canvas, x: int, y: int, color: Color = CLOUD) -> None:
    _disc(c, x + 5, y + 8, 3, color)
    _disc(c, x + 9, y + 6, 4, color)
    c.rect(x + 4, y + 8, 8, 3, color, fill=True)


def cloud(c: Canvas, x: int, y: int) -> None:
    _cloud(c, x, y)


def rain(c: Canvas, x: int, y: int) -> None:
    _cloud(c, x, y)
    for i in range(3):
        c.vline(x + 5 + i * 3, y + 11, 3, RAIN)


def snow(c: Canvas, x: int, y: int) -> None:
    _cloud(c, x, y)
    for i in range(3):
        c.pixel(x + 5 + i * 3, y + 12, SNOW)


ICONS = {"clear": sun, "clouds": cloud, "rain": rain, "snow": snow}


def weather_icon(c: Canvas, condition: str, x: int, y: int) -> None:
    ICONS.get(condition, sun)(c, x, y)
