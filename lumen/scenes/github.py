"""GitHub scene — commit activity / streak.

Real data source (per design): the GitHub REST/GraphQL API. ``fetch`` is a STUB.
To go live, query the contributions calendar for cfg["username"] and map it into
``GithubData`` (today's count, current streak, last 7 days).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..canvas import Canvas
from ..registry import register
from ..scene import RenderContext, Scene

GH_GREEN = (57, 211, 83)


@dataclass
class GithubData:
    today: int
    streak: int
    week: list[int] = field(default_factory=list)  # contributions per day, oldest first


@register
class GithubScene(Scene):
    id = "github"
    default_duration = 8
    ttl = 300
    transition = "dissolve"

    def fetch(self, ctx: RenderContext) -> GithubData:
        # --- STUB: swap for a GitHub contributions query on cfg["username"] --
        return GithubData(today=7, streak=23, week=[2, 5, 1, 8, 3, 6, 7])

    def draw(self, ctx: RenderContext) -> Canvas:
        g: GithubData = ctx.data
        c = Canvas()
        c.text(1, 1, "GITHUB", GH_GREEN, font="4x6")

        # Today's count, large.
        c.text(1, 9, f"{g.today}", (255, 255, 255), font="6x13")
        c.text(1 + 14, 14, "TODAY", (120, 120, 120), font="4x6")

        # Streak, top-right.
        c.text_right(63, 1, f"{g.streak}d", GH_GREEN, font="4x6")

        # Last-7-days bar chart along the bottom.
        peak = max(g.week) or 1
        base_y = 31
        for i, v in enumerate(g.week):
            h = max(1, round(6 * v / peak))
            x = 1 + i * 4
            c.rect(x, base_y - h, 3, h, GH_GREEN, fill=True)
        return c
