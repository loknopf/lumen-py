"""Countdown scene — time remaining to a target date.

Data source (per design): server config. Set the target under
``[scenes.countdown]`` in config.toml::

    [scenes.countdown]
    target = "2026-08-15"
    label = "PORTO"

With no config it falls back to a demo target so the pipeline still renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..canvas import Canvas
from ..registry import register
from ..scene import RenderContext, Scene


@dataclass
class CountdownData:
    days: int
    label: str


@register
class CountdownScene(Scene):
    id = "countdown"
    default_duration = 8
    ttl = 3600  # only changes at midnight
    transition = "wipe"

    def fetch(self, ctx: RenderContext) -> CountdownData:
        cfg = ctx.config.scene_config(self.id)
        target_str = cfg.get("target", "2026-08-15")
        label = cfg.get("label", "PORTO")
        target = date.fromisoformat(target_str)
        today = ctx.now.date() if isinstance(ctx.now, datetime) else ctx.now
        days = (target - today).days
        return CountdownData(days=days, label=label[:10])

    def draw(self, ctx: RenderContext) -> Canvas:
        d: CountdownData = ctx.data
        c = Canvas()
        c.text_centered(1, d.label, (255, 180, 0), font="5x8")
        c.text_centered(11, f"{d.days}", (255, 255, 255), font="6x13")
        unit = "DAYS" if d.days != 1 else "DAY"
        c.text_centered(26, unit, (120, 120, 120), font="4x6")
        return c
