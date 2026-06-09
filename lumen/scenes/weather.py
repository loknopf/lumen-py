"""Weather scene — current conditions + temperature.

Data source: the Open-Meteo API (no key needed), see ``lumen.sources.weather``.
Goes live when the config provides ``latitude``/``longitude`` or a ``location``
name (geocoded once via Open-Meteo); without either, ``fetch`` returns the
``demo_*`` values so the pipeline runs offline and golden tests stay
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..canvas import Canvas
from ..fonts import Color
from ..registry import register
from ..scene import RenderContext, Scene
from ..sources import weather as weather_api
from ._icons import weather_icon

_SKY: dict[str, Color] = {
    "clear": (55, 28, 0),
    "clouds": (30, 35, 48),
    "rain": (15, 22, 58),
    "snow": (38, 48, 65),
}
_SEP: dict[str, Color] = {
    "clear": (90, 55, 0),
    "clouds": (55, 60, 70),
    "rain": (25, 45, 110),
    "snow": (55, 72, 105),
}


def _temp_color(t: float) -> Color:
    if t < 5:
        return (80, 200, 255)
    if t < 20:
        return (255, 255, 255)
    if t < 30:
        return (255, 175, 70)
    return (255, 75, 40)


@dataclass
class WeatherData:
    temp_c: float
    high_c: float
    low_c: float
    condition: str  # one of: clear, clouds, rain, snow


@register
class WeatherScene(Scene):
    id = "weather"
    default_duration = 8
    ttl = 600  # weather changes slowly
    transition = "fade"

    def fetch(self, ctx: RenderContext) -> WeatherData:
        cfg = ctx.config.scene_config(self.id)
        lat, lon = cfg.get("latitude"), cfg.get("longitude")
        if lat is None or lon is None:
            location = cfg.get("location")
            if not location:
                # Demo data: keeps offline runs and golden tests working.
                return WeatherData(
                    temp_c=cfg.get("demo_temp", 18),
                    high_c=cfg.get("demo_high", 21),
                    low_c=cfg.get("demo_low", 11),
                    condition=cfg.get("demo_condition", "clear"),
                )
            lat, lon = weather_api.geocode(location)
        report = weather_api.fetch_weather(lat, lon)
        return WeatherData(
            temp_c=report.temp_c,
            high_c=report.high_c,
            low_c=report.low_c,
            condition=report.condition,
        )

    def draw(self, ctx: RenderContext) -> Canvas:
        w: WeatherData = ctx.data
        c = Canvas()

        # 2px sky-tint strip based on condition.
        sky = _SKY.get(w.condition, (30, 30, 30))
        for x in range(c.width):
            c.pixel(x, 0, sky)
            c.pixel(x, 1, (sky[0] // 2, sky[1] // 2, sky[2] // 2))

        weather_icon(c, w.condition, 1, 2)

        # Temperature colored by value, right-aligned.
        temp = f"{round(w.temp_c)}"
        tc = _temp_color(w.temp_c)
        c.text_right(57, 3, temp, tc, font="6x13")
        c.rect(58, 4, 3, 3, tc)  # degree mark in matching color

        # Condition label in the middle-right area.
        c.text(18, 14, w.condition.upper()[:6], (90, 100, 125), font="4x6")

        # Condition-tinted separator and Hi/Lo strip.
        c.hline(0, 22, c.width, _SEP.get(w.condition, (45, 45, 50)))
        c.text(2, 25, f"H{round(w.high_c)}", (255, 140, 0), font="4x6")
        c.text_right(62, 25, f"L{round(w.low_c)}", (90, 160, 255), font="4x6")
        return c
