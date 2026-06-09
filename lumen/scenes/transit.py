"""Transit scene — next departures.

Data source: the RMV OpenData API (HAFAS ``departureBoard``), see
``lumen.sources.rmv``. Goes live when station ids (config) and an access id
(config ``api_key`` or ``RMV_API_KEY`` env var) are present; otherwise ``fetch``
returns demo departures so the pipeline runs offline and golden tests stay
deterministic.

Station config — a single ``stop_id``, or several stations via ``stops``
(strings, or tables with per-station filters). Optional top-level ``lines``
and ``direction`` apply to every station without its own. ``direction``
takes the stop id of a journey's last stop (API-side filter, section 2.24.1):

    stop_id = "3000010"
    # or:
    stops = ["3000010", { id = "3000011", lines = ["U4", "U16"], direction = "3001234" }]
    lines = ["S6"]

Display modes (``mode`` key) — ``"full"`` (default) shows three rows with the
destination text; ``"compact"`` drops the destination (e.g. when a direction
filter already implies it) and instead fits four rows showing line, scheduled
departure clock time, the live delay and minutes to departure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta

from ..canvas import Canvas
from ..fonts import get_font
from ..registry import register
from ..scene import RenderContext, Scene
from ..sources import rmv


@dataclass
class Departure:
    line: str  # e.g. "U4", "12"
    destination: str
    minutes: int  # minutes until departure
    color: tuple[int, int, int] = (255, 180, 0)
    delay: int | None = None  # minutes vs schedule; None = no realtime data


@register
class TransitScene(Scene):
    id = "transit"
    default_duration = 10
    ttl = 30  # departures are time-sensitive
    transition = "slide"

    def fetch(self, ctx: RenderContext) -> list[Departure]:
        cfg = ctx.config.scene_config(self.id)
        stops = _stop_entries(cfg)
        access_id = cfg.get("api_key") or os.environ.get("RMV_API_KEY")
        if not stops or not access_id:
            # Demo data: keeps offline runs and golden tests working. The
            # fourth row and the delays only show in compact mode.
            return [
                Departure("U4", "Enkheim", 3, (220, 60, 60), delay=0),
                Departure("12", "Hbf", 7, (60, 120, 220), delay=2),
                Departure("S6", "Friedberg", 12, (60, 180, 90), delay=None),
                Departure("S8", "Wiesbaden", 21, (60, 180, 90), delay=6),
            ]
        rows = rmv.fetch_boards(
            stops,
            access_id,
            now=ctx.now,
            base_url=cfg.get("base_url", rmv.DEFAULT_BASE_URL),
            duration=cfg.get("duration", 60),
        )
        return [
            Departure(
                line=r.line,
                destination=r.direction,
                minutes=max(0, round((r.when - ctx.now).total_seconds() / 60)),
                color=r.color,
                delay=r.delay_min,
            )
            for r in rows
        ]

    def draw(self, ctx: RenderContext) -> Canvas:
        mode = ctx.config.scene_config(self.id).get("mode", "full")
        if mode == "compact":
            return self._draw_compact(ctx)
        return self._draw_full(ctx)

    def _draw_full(self, ctx: RenderContext) -> Canvas:
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

    def _draw_compact(self, ctx: RenderContext) -> Canvas:
        """Four destination-less rows: line, scheduled time, delay, minutes."""
        deps: list[Departure] = ctx.data
        c = Canvas()
        font = get_font("4x6")
        for i, d in enumerate(deps[:4]):
            y = 1 + i * 8
            if i > 0:
                c.hline(0, y - 1, c.width, (22, 22, 22))
            # Line badge, same chip style as full mode but 4x6-sized.
            w = font.text_width(d.line) + 2
            c.rect(0, y, w, 7, d.color, fill=True)
            c.text(1, y + 1, d.line, (0, 0, 0), font="4x6")
            # Scheduled clock time (the timetable the rider knows).
            scheduled = ctx.now + timedelta(minutes=d.minutes - (d.delay or 0))
            c.text(max(w + 2, 17), y + 1, scheduled.strftime("%H:%M"), (160, 160, 160), font="4x6")
            # Delay against schedule; nothing shown without realtime data.
            delay = _delay_style(d.delay)
            if delay is not None:
                c.text(40, y + 1, delay[0], delay[1], font="4x6")
            # Minutes until departure, same urgency colors as full mode.
            mins = f"{d.minutes}'"
            min_color = (
                (255, 60, 60) if d.minutes <= 3 else
                (255, 200, 50) if d.minutes <= 7 else
                (210, 210, 210)
            )
            c.text_right(63, y + 1, mins, min_color, font="4x6")
        return c


def _delay_style(delay: int | None) -> tuple[str, tuple[int, int, int]] | None:
    """Text + color for a delay: green on time, yellow small, red big, cyan early."""
    if delay is None:
        return None
    if delay < 0:
        return f"{delay}", (80, 200, 255)
    if delay == 0:
        return "+0", (0, 170, 80)
    if delay <= 4:
        return f"+{delay}", (255, 200, 50)
    return f"+{delay}", (255, 60, 60)


def _stop_entries(cfg: dict) -> list[rmv.StopSpec]:
    """Resolve the station list from config into ``StopSpec`` entries.

    ``stops`` entries may be plain ids or tables with ``id`` and optional
    per-station ``lines`` / ``direction`` filters; the top-level ``lines`` and
    ``direction`` are the fallbacks. A lone ``stop_id`` keeps working.
    """
    global_lines = cfg.get("lines") or None
    global_direction = str(cfg["direction"]) if cfg.get("direction") else None
    entries: list[rmv.StopSpec] = []
    for stop in cfg.get("stops", []):
        if isinstance(stop, dict):
            if stop.get("id"):
                entries.append(
                    rmv.StopSpec(
                        id=str(stop["id"]),
                        lines=stop.get("lines") or global_lines,
                        direction=str(stop["direction"]) if stop.get("direction") else global_direction,
                    )
                )
        elif stop:
            entries.append(rmv.StopSpec(id=str(stop), lines=global_lines, direction=global_direction))
    if not entries and cfg.get("stop_id"):
        entries.append(
            rmv.StopSpec(id=str(cfg["stop_id"]), lines=global_lines, direction=global_direction)
        )
    return entries


def _fit(font, text: str, max_px: int) -> str:
    """Trim ``text`` (adding a '.' marker) until it fits within ``max_px``."""
    if font.text_width(text) <= max_px:
        return text
    while text and font.text_width(text + ".") > max_px:
        text = text[:-1]
    return text + "." if text else ""
