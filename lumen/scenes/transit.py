"""Transit scene — next departures.

Real data source (per design): the RMV OpenData API. ``fetch`` is a STUB
returning static departures. To go live, call the RMV ``departureBoard`` endpoint
with cfg["stop_id"] and map results into a list of ``Departure``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..canvas import Canvas
from ..fonts import get_font
from ..registry import register
from ..scene import RenderContext, Scene


@dataclass
class Departure:
    line: str  # e.g. "U4", "12"
    destination: str
    minutes: int  # minutes until departure
    color: tuple[int, int, int] = (255, 180, 0)


@register
class TransitScene(Scene):
    id = "transit"
    default_duration = 10
    ttl = 30  # departures are time-sensitive
    transition = "slide"

    def fetch(self, ctx: RenderContext) -> list[Departure]:
        # --- STUB: swap for an RMV departureBoard call on cfg["stop_id"] -----
        return [
            Departure("U4", "Enkheim", 3, (220, 60, 60)),
            Departure("12", "Hbf", 7, (60, 120, 220)),
            Departure("S6", "Friedberg", 12, (60, 180, 90)),
        ]

    def draw(self, ctx: RenderContext) -> Canvas:
        deps: list[Departure] = ctx.data
        c = Canvas()
        font = get_font("5x8")
        for i, d in enumerate(deps[:3]):
            y = 1 + i * 10
            # Dim separator above rows 2 and 3.
            if i > 0:
                c.hline(0, y - 1, c.width, (22, 22, 22))
            # Line badge: colored chip with the line code knocked out in black.
            label = d.line
            w = font.text_width(label) + 2
            c.rect(0, y, w, 9, d.color, fill=True)
            c.text(1, y + 1, label, (0, 0, 0), font="5x8")
            # Minutes with urgency coloring: red ≤3, yellow ≤7, plain otherwise.
            mins = f"{d.minutes}'"
            min_color = (
                (255, 60, 60) if d.minutes <= 3 else
                (255, 200, 50) if d.minutes <= 7 else
                (210, 210, 210)
            )
            min_x = 63 - font.text_width(mins)
            c.text(min_x, y + 1, mins, min_color, font="5x8")
            # Destination, clipped to the pixels between badge and minutes.
            dest_x = w + 2
            avail = (min_x - 2) - dest_x
            c.text(dest_x, y + 1, _fit(font, d.destination, avail), (200, 200, 200), font="5x8")
        return c


def _fit(font, text: str, max_px: int) -> str:
    """Trim ``text`` (adding a '.' marker) until it fits within ``max_px``."""
    if font.text_width(text) <= max_px:
        return text
    while text and font.text_width(text + ".") > max_px:
        text = text[:-1]
    return text + "." if text else ""
