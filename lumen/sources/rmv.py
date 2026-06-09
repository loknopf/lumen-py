"""RMV departure board via the HAFAS ReST interface.

Implements the ``departureBoard`` service:

    GET <baseUrl>/departureBoard?accessId=...&id=<stop>&format=json

The JSON shape follows the documented XML-to-JSON conversion: the root
``DepartureBoard`` element is dropped, attributes become object properties and
repeated elements become arrays. Each ``Departure`` carries ``name``, planned
``date``/``time``, realtime ``rtDate``/``rtTime`` when available, ``direction``
and a ``Product`` element with line code, category (``catOut``) and an optional
icon background colour we reuse for the line badge.

All times in the response are local to the stop (no offset in the strings);
callers pass a naive local ``now`` and the server is assumed to run in the
same timezone as the stops it displays.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

import httpx

DEFAULT_BASE_URL = "https://www.rmv.de/hapi"

#: Fallback badge colours keyed by HAFAS product category (``catOut``).
_CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "S": (60, 180, 90),
    "U": (220, 60, 60),
    "Tram": (60, 120, 220),
    "STR": (60, 120, 220),
    "Bus": (160, 90, 220),
    "ICE": (240, 240, 240),
    "IC": (240, 240, 240),
    "RE": (230, 80, 80),
    "RB": (230, 80, 80),
}
_DEFAULT_COLOR = (255, 180, 0)


@dataclass
class RmvDeparture:
    line: str  # display code, e.g. "U4", "S6", "12"
    direction: str
    when: datetime  # realtime if reported, else planned
    color: tuple[int, int, int]
    track: str | None = None
    delay_min: int | None = None  # realtime vs planned; None = no realtime data


@dataclass
class StopSpec:
    """One station of a (multi-)board request, with optional filters."""

    id: str
    lines: Sequence[str | int] | None = None
    direction: str | None = None  # stop id of the journey's last stop


def fetch_departures(
    stop_id: str,
    access_id: str,
    *,
    now: datetime,
    base_url: str = DEFAULT_BASE_URL,
    duration: int = 60,
    max_journeys: int = 20,
    lines: Sequence[str | int] | None = None,
    direction: str | None = None,
    timeout: float = 10.0,
) -> list[RmvDeparture]:
    """Return upcoming departures for ``stop_id``, soonest first.

    ``lines`` restricts the board to the given line codes (e.g. ``["U4", "16"]``,
    matched case-insensitively). The filter is passed to the API (``lines``
    request parameter, section 2.24.1) and re-applied client-side, since the
    server-side filter needs extended line data in the HAFAS back end.

    ``direction`` restricts the board to vehicles heading toward the given
    stop: per section 2.24.1 it takes the station/stop ID of the last stop on
    the journey and is filtered entirely by the API.
    """
    params: dict = {
        "accessId": access_id,
        "id": stop_id,
        "duration": duration,
        "maxJourneys": max_journeys,
        "format": "json",
    }
    if lines:
        params["lines"] = ",".join(str(code) for code in lines)
    if direction:
        params["direction"] = direction
    resp = httpx.get(
        f"{base_url.rstrip('/')}/departureBoard", params=params, timeout=timeout
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errorCode" in payload:
        raise RuntimeError(
            f"RMV departureBoard: {payload['errorCode']} {payload.get('errorText', '')}".strip()
        )
    return parse_departures(payload, now=now, lines=lines)


def fetch_boards(
    stops: Sequence[StopSpec],
    access_id: str,
    *,
    now: datetime,
    base_url: str = DEFAULT_BASE_URL,
    duration: int = 60,
    timeout: float = 10.0,
) -> list[RmvDeparture]:
    """Merged departure board over several stations, soonest first."""
    rows: list[RmvDeparture] = []
    for stop in stops:
        rows.extend(
            fetch_departures(
                stop.id,
                access_id,
                now=now,
                base_url=base_url,
                duration=duration,
                lines=stop.lines,
                direction=stop.direction,
                timeout=timeout,
            )
        )
    rows.sort(key=lambda d: d.when)
    return rows


def parse_departures(
    payload: dict, *, now: datetime, lines: Sequence[str | int] | None = None
) -> list[RmvDeparture]:
    """Map a departureBoard JSON payload to ``RmvDeparture`` rows.

    Cancelled and already-departed journeys are dropped, as is anything not
    matching the optional ``lines`` filter; the rest are sorted by effective
    departure time.
    """
    wanted = {_norm_line(code) for code in lines} if lines else None
    raw = payload.get("Departure", [])
    if isinstance(raw, dict):  # single XML element converts to an object
        raw = [raw]

    result: list[RmvDeparture] = []
    for dep in raw:
        if _is_cancelled(dep):
            continue
        planned = _parse_dt(dep.get("date"), dep.get("time"))
        actual = _parse_dt(dep.get("rtDate") or dep.get("date"), dep.get("rtTime"))
        when = actual or planned
        if when is None or when < now - timedelta(seconds=30):
            continue
        product = _product(dep)
        label = _line_label(dep, product)
        if wanted is not None and _norm_line(label) not in wanted:
            continue
        delay = None
        if actual is not None and planned is not None:
            delay = round((actual - planned).total_seconds() / 60)
        result.append(
            RmvDeparture(
                line=label,
                direction=dep.get("direction", ""),
                when=when,
                color=_line_color(product),
                track=dep.get("rtTrack") or dep.get("track"),
                delay_min=delay,
            )
        )
    result.sort(key=lambda d: d.when)
    return result


def _norm_line(code: str | int) -> str:
    """Normalise a line code for comparison: "u 16" == "U16"."""
    return str(code).replace(" ", "").casefold()


def _is_cancelled(dep: dict) -> bool:
    cancelled = dep.get("cancelled", False)
    if isinstance(cancelled, str):
        cancelled = cancelled.lower() == "true"
    return bool(cancelled)


def _parse_dt(date: str | None, time: str | None) -> datetime | None:
    if not date or not time:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{time}")
    except ValueError:
        return None


def _product(dep: dict) -> dict:
    product = dep.get("Product", {})
    if isinstance(product, list):  # multiple Product elements convert to an array
        product = product[0] if product else {}
    return product


def _line_label(dep: dict, product: dict) -> str:
    label = product.get("line") or product.get("displayNumber")
    if label:
        return str(label)
    # Fall back to the departure name ("Bus 73", "S9"): last token is the code.
    name = str(dep.get("name", "")).strip()
    return name.split()[-1] if name else "?"


def _line_color(product: dict) -> tuple[int, int, int]:
    bg = product.get("icon", {}).get("backgroundColor", {})
    try:
        color = (int(bg["r"]), int(bg["g"]), int(bg["b"]))
    except (KeyError, TypeError, ValueError):
        color = None
    # Near-black chips would swallow the knocked-out black label text.
    if color is not None and sum(color) >= 90:
        return color
    return _CATEGORY_COLORS.get(str(product.get("catOut", "")).strip(), _DEFAULT_COLOR)
