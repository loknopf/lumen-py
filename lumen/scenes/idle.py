"""Idle scene — ambient date card.

The per-second clock lives on the M4 (it needs a refresh rate the server-poll
model can't provide). This server-side idle scene is the calmer ambient fallback:
day-of-week and date with a soft gradient bar. No external data.
"""

from __future__ import annotations

from datetime import datetime

from ..canvas import Canvas
from ..registry import register
from ..scene import RenderContext, Scene

DOW = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


@register
class IdleScene(Scene):
    id = "idle"
    default_duration = 6
    ttl = 30
    transition = "fade"

    def draw(self, ctx: RenderContext) -> Canvas:
        now: datetime = ctx.now
        c = Canvas()
        # Soft ambient gradient strip across the top.
        for x in range(c.width):
            t = x / (c.width - 1)
            c.vline(x, 0, 3, (int(20 + 60 * t), int(10 + 20 * t), int(60 - 40 * t)))

        c.text_centered(8, DOW[now.weekday()], (120, 140, 220), font="5x8")
        c.text_centered(18, f"{now.day:02d} {MON[now.month - 1]}", (220, 220, 220), font="6x13")
        return c
