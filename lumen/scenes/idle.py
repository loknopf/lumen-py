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
        # Richer 5px gradient strip: deep teal on left → purple on right.
        for x in range(c.width):
            t = x / (c.width - 1)
            c.vline(x, 0, 5, (int(10 + 70 * t), int(5 + 20 * t), int(85 - 35 * t)))
        # Mirror glow at the very bottom.
        for x in range(c.width):
            t = x / (c.width - 1)
            c.pixel(x, 31, (int(6 + 25 * t), int(3 + 7 * t), int(32 - 12 * t)))

        c.text_centered(6, DOW[now.weekday()], (140, 160, 250), font="5x8")
        c.hline(18, 16, 28, (35, 42, 85))  # thin separator between DOW and date
        c.text_centered(18, f"{now.day:02d} {MON[now.month - 1]}", (235, 235, 250), font="6x13")
        return c
