"""Status scene — service health from a Gatus status page.

Data source: the Gatus public API (no key needed), see ``lumen.sources.gatus``.
Goes live once the config provides the status page ``url``; otherwise ``fetch``
returns demo services so the pipeline runs offline and golden tests stay
deterministic.

Layout: a header with the overall verdict, a one-pixel timeline of the last
hour (one column per minute, worst state across all services), and a 2x4 grid
of services, each a status dot plus a short label.

Config::

    url = "https://status.example.com"
    groups = ["Public", "Services", "Infrastructure", "Certificates"]  # filter + order
    fold = { Certificates = "TLS" }      # collapse a group into one tile
    labels = { public_portfolio = "SITE" }  # per endpoint key; 7 chars fit

Labels default to the endpoint name, upper-cased and trimmed to fit. With more
than eight services, unhealthy ones are kept on screen first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..canvas import Canvas
from ..fonts import Color, get_font
from ..registry import register
from ..scene import RenderContext, Scene
from ..sources import gatus
from ..sources.gatus import Check, EndpointStatus
from .transit import _fit

#: Bright colors for dots, labels and the verdict.
STATE_COLOR: dict[str, Color] = {
    "up": (57, 211, 83),
    "deg": (255, 200, 50),
    "down": (255, 60, 60),
    "none": (90, 90, 90),
}
#: The timeline runs dimmer so problems stand out against a calm baseline.
TIMELINE_COLOR: dict[str, Color] = {
    "up": (20, 90, 35),
    "deg": (200, 150, 30),
    "down": (255, 50, 50),
    "none": (28, 28, 28),
}
LABEL_UP: Color = (200, 200, 200)

TIMELINE_MINUTES = 64  # one column per minute across the panel
SLOTS = 8  # 2 columns x 4 rows


@dataclass
class Service:
    label: str
    state: str  # up / deg / down / none


@dataclass
class StatusData:
    services: list[Service]
    timeline: list[str] = field(default_factory=list)  # per minute, oldest first


@register
class StatusScene(Scene):
    id = "status"
    default_duration = 8
    ttl = 60  # Gatus checks every minute
    transition = "wipe"

    def fetch(self, ctx: RenderContext) -> StatusData:
        cfg = ctx.config.scene_config(self.id)
        url = cfg.get("url")
        if not url:
            # Demo data: keeps offline runs and golden tests working.
            timeline = ["up"] * TIMELINE_MINUTES
            timeline[20:22] = ["down", "down"]
            timeline[-6:] = ["deg"] * 6
            return StatusData(
                services=[
                    Service("SITE", "up"),
                    Service("DRAW", "up"),
                    Service("GRAFANA", "up"),
                    Service("N8N", "up"),
                    Service("CLOUD", "deg"),
                    Service("PROXY", "up"),
                    Service("TLS", "up"),
                ],
                timeline=timeline,
            )
        endpoints = gatus.fetch_statuses(url, page_size=TIMELINE_MINUTES)
        endpoints = _select_groups(endpoints, cfg.get("groups"))
        now = ctx.now.astimezone(timezone.utc)
        return StatusData(
            services=_services(endpoints, cfg.get("fold") or {}, cfg.get("labels") or {}),
            timeline=_timeline(endpoints, now),
        )

    def draw(self, ctx: RenderContext) -> Canvas:
        s: StatusData = ctx.data
        c = Canvas()
        font = get_font("4x6")

        # Header: title left, overall verdict right.
        verdict, color = _verdict([svc.state for svc in s.services])
        c.text(1, 1, "STATUS", (150, 150, 150), font="4x6")
        c.text_right(63, 1, verdict, color, font="4x6")

        # Last hour as a one-pixel strip doubling as the header divider.
        strip = s.timeline[-c.width:]
        for x, state in enumerate(strip, start=c.width - len(strip)):
            c.pixel(x, 7, TIMELINE_COLOR[state])

        # Service grid, filled column by column.
        for i, svc in enumerate(_visible(s.services)):
            x = 0 if i < SLOTS // 2 else 33
            y = 9 + (i % (SLOTS // 2)) * 6
            c.rect(x, y + 1, 3, 3, STATE_COLOR[svc.state], fill=True)
            label_color = LABEL_UP if svc.state == "up" else STATE_COLOR[svc.state]
            c.text(x + 4, y, _fit(font, svc.label, 28), label_color, font="4x6")
        return c


def _verdict(states: list[str]) -> tuple[str, Color]:
    """Header text: the count of the worst failing state, or ALL OK."""
    for state, word in (("down", "DOWN"), ("deg", "WARN")):
        n = states.count(state)
        if n:
            return f"{n} {word}", STATE_COLOR[state]
    if "up" in states:
        return "ALL OK", STATE_COLOR["up"]
    return "....", STATE_COLOR["none"]


def _select_groups(endpoints: list[EndpointStatus], groups: list[str] | None) -> list[EndpointStatus]:
    """Keep only ``groups`` (in that order); all of them, API order, if unset."""
    if not groups:
        return endpoints
    order = {g: i for i, g in enumerate(groups)}
    kept = [ep for ep in endpoints if ep.group in order]
    return sorted(kept, key=lambda ep: order[ep.group])


def _services(
    endpoints: list[EndpointStatus], fold: dict[str, str], labels: dict[str, str]
) -> list[Service]:
    """One tile per endpoint; a folded group becomes one tile with its worst state."""
    services: list[Service] = []
    folded: dict[str, Service] = {}
    for ep in endpoints:
        if ep.group in fold:
            tile = folded.get(ep.group)
            if tile is None:
                tile = folded[ep.group] = Service(fold[ep.group].upper(), ep.state)
                services.append(tile)
            else:
                tile.state = gatus.worst([tile.state, ep.state])
        else:
            services.append(Service(labels.get(ep.key, ep.name).upper(), ep.state))
    return services


def _timeline(endpoints: list[EndpointStatus], now: datetime) -> list[str]:
    """Worst state across endpoints at the end of each of the last minutes.

    Each endpoint holds the state of its latest check until the next one, so
    services checked less often than every minute don't leave gaps.
    """
    timeline = []
    for i in range(TIMELINE_MINUTES):
        t = now - timedelta(minutes=TIMELINE_MINUTES - 1 - i)
        timeline.append(gatus.worst(_state_at(ep.checks, t) for ep in endpoints))
    return timeline


def _state_at(checks: list[Check], t: datetime) -> str:
    state = "none"
    for check in checks:  # oldest first
        if check.when > t:
            break
        state = check.state
    return state


def _visible(services: list[Service]) -> list[Service]:
    """At most SLOTS services; on overflow the unhealthy ones win the slots."""
    if len(services) <= SLOTS:
        return services
    ranked = sorted(range(len(services)), key=lambda i: -gatus.RANK[services[i].state])
    return [services[i] for i in sorted(ranked[:SLOTS])]

