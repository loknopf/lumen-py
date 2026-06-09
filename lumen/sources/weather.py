"""Weather via the Open-Meteo API (no API key required).

Two endpoints:
- forecast: current temperature + WMO weather code, plus today's min/max
  (https://open-meteo.com/en/docs)
- geocoding: resolves a place name to coordinates once, cached per name
  (https://open-meteo.com/en/docs/geocoding-api)

The WMO weather code is reduced to the four conditions the weather scene can
draw: clear / clouds / rain / snow.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass
class WeatherReport:
    temp_c: float
    high_c: float
    low_c: float
    condition: str  # one of: clear, clouds, rain, snow


@lru_cache(maxsize=32)
def geocode(name: str, *, timeout: float = 10.0) -> tuple[float, float]:
    """Resolve a place name to (latitude, longitude). Cached per name."""
    resp = httpx.get(GEOCODE_URL, params={"name": name, "count": 1}, timeout=timeout)
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise RuntimeError(f"Open-Meteo geocoding: no match for {name!r}")
    hit = results[0]
    return float(hit["latitude"]), float(hit["longitude"])


def fetch_weather(latitude: float, longitude: float, *, timeout: float = 10.0) -> WeatherReport:
    resp = httpx.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_report(resp.json())


def parse_report(payload: dict) -> WeatherReport:
    current = payload["current"]
    daily = payload["daily"]
    return WeatherReport(
        temp_c=float(current["temperature_2m"]),
        high_c=float(daily["temperature_2m_max"][0]),
        low_c=float(daily["temperature_2m_min"][0]),
        condition=condition_from_code(int(current["weather_code"])),
    )


def condition_from_code(code: int) -> str:
    """Reduce a WMO weather code to the scene's four conditions."""
    if code in (0, 1):  # clear / mainly clear
        return "clear"
    if 71 <= code <= 77 or code in (85, 86):  # snow fall / grains / showers
        return "snow"
    if 51 <= code <= 67 or 80 <= code <= 82 or 95 <= code <= 99:  # drizzle/rain/thunder
        return "rain"
    return "clouds"  # overcast, fog and anything unexpected
