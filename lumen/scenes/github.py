"""GitHub scene — commit activity / streak.

Data source: the GitHub GraphQL API (contributions calendar), see
``lumen.sources.github``. Goes live when both a username (config) and a token
(config ``token`` or ``GITHUB_TOKEN`` env var) are present; otherwise ``fetch``
returns demo data so the pipeline runs offline and golden tests stay
deterministic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..canvas import Canvas
from ..registry import register
from ..scene import RenderContext, Scene
from ..sources import github as github_api

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
        cfg = ctx.config.scene_config(self.id)
        username = cfg.get("username")
        token = cfg.get("token") or os.environ.get("GITHUB_TOKEN")
        if not username or not token:
            # Demo data: keeps offline runs and golden tests working.
            return GithubData(today=7, streak=23, week=[2, 5, 1, 8, 3, 6, 7])
        stats = github_api.fetch_contributions(username, token, today=ctx.now.date())
        return GithubData(today=stats.today, streak=stats.streak, week=stats.week)

    def draw(self, ctx: RenderContext) -> Canvas:
        g: GithubData = ctx.data
        c = Canvas()
        c.text(1, 1, "GITHUB", GH_GREEN, font="4x6")

        # Today's count, large.
        c.text(1, 9, f"{g.today}", (255, 255, 255), font="6x13")
        c.text(1 + 14, 14, "TODAY", (120, 120, 120), font="4x6")

        # Streak and 7D label, top-right.
        c.text_right(63, 1, f"{g.streak}d", GH_GREEN, font="4x6")
        c.text_right(63, 17, "7D", (45, 85, 45), font="4x6")

        # Green divider separating the stats area from the bar chart.
        c.hline(0, 23, c.width, (28, 58, 28))

        # Last-7-days bar chart with bottom-to-top brightness gradient.
        peak = max(g.week) or 1
        base_y = 31
        for i, v in enumerate(g.week):
            h = max(1, round(7 * v / peak))
            x = 1 + i * 4
            for dy in range(h):
                t = dy / max(h - 1, 1)
                br = int(70 + 140 * t)
                c.hline(x, base_y - dy, 3, (int(br * 0.27), br, int(br * 0.39)))
        return c
