"""Clock placeholder — the real clock renders on the M4.

The per-second clock is a firmware-local scene (the server-poll model can't
deliver 1 Hz updates). This placeholder exists so "clock" can appear in the
rotation without being filtered out by the stage manager's registry guard, and
so /preview shows a card for it. The firmware resolves "clock" against its
local registry first and never fetches this frame.
"""

from __future__ import annotations

from ..canvas import Canvas
from ..registry import register
from ..scene import RenderContext, Scene


@register
class ClockScene(Scene):
    id = "clock"
    default_duration = 30
    ttl = 3600  # static card; effectively render-once

    def draw(self, ctx: RenderContext) -> Canvas:
        c = Canvas()
        c.text_centered(8, f"{ctx.now.hour:02d}:{ctx.now.minute:02d}", (0, 255, 0), font="6x13")
        c.text_centered(22, "ON DEVICE", (60, 90, 60), font="4x6")
        return c
