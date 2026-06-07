"""Weather scene — current conditions + temperature.

Real data source (per design): a weather API. The ``fetch`` below is a clearly
marked STUB returning static demo data so the pipeline runs offline. To go live,
replace the body of ``fetch`` with an HTTP call (e.g. Open-Meteo, no key needed)
and map the response into ``WeatherData``. Nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..canvas import Canvas
from ..registry import register
from ..scene import RenderContext, Scene
from ._icons import weather_icon


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
        # --- STUB: swap for a real API call keyed on cfg["location"] ---------
        return WeatherData(
            temp_c=cfg.get("demo_temp", 18),
            high_c=cfg.get("demo_high", 21),
            low_c=cfg.get("demo_low", 11),
            condition=cfg.get("demo_condition", "clear"),
        )

    def draw(self, ctx: RenderContext) -> Canvas:
        w: WeatherData = ctx.data
        c = Canvas()
        weather_icon(c, w.condition, 1, 1)

        # Big temperature, right-aligned, with a degree ring.
        temp = f"{round(w.temp_c)}"
        end = c.text_right(57, 3, temp, (255, 255, 255), font="6x13")
        c.rect(58, 4, 3, 3, (255, 255, 255))  # degree mark

        # Hi / Lo strip along the bottom.
        c.hline(0, 22, c.width, (40, 40, 40))
        c.text(2, 25, f"H{round(w.high_c)}", (255, 140, 0), font="4x6")
        c.text_right(62, 25, f"L{round(w.low_c)}", (90, 160, 255), font="4x6")
        return c
