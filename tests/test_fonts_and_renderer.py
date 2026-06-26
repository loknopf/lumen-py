"""Font rendering and renderer fallback/caching behaviour."""

from __future__ import annotations

import lumen.scenes  # noqa: F401
from lumen.canvas import Canvas
from lumen.config import Config
from lumen.fonts import get_font
from lumen.renderer import FrameRenderer, error_frame


def test_font_loads_and_has_ascii():
    f = get_font("5x8")
    assert f.text_width("A") > 0
    assert f.height == 8


def test_text_draws_some_pixels():
    c = Canvas()
    c.text(0, 0, "A", (255, 255, 255), font="5x8")
    # The glyph 'A' should light up several pixels.
    lit = sum(1 for p in c.to_rgb565() if p != 0)
    assert lit > 0


def test_error_frame_is_valid_length():
    assert len(error_frame("BOOM")) == 4096


def test_renderer_returns_error_frame_for_unknown_scene():
    r = FrameRenderer(Config())
    assert len(r.frame("nonexistent", 0)) == 4096


def test_renderer_caches_within_ttl():
    r = FrameRenderer(Config())
    first = r.frame("weather", 0)
    second = r.frame("weather", 0)
    assert first == second  # served from cache, identical bytes


def test_renderer_falls_back_to_last_good_on_failure(monkeypatch):
    r = FrameRenderer(Config())
    good = r.frame("weather", 0)

    # Force the next render to blow up, then confirm we still get the last good.
    from lumen.registry import SCENES

    def boom(ctx):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(SCENES["weather"], "draw", boom)
    r.invalidate("weather")
    assert r.frame("weather", 0) == good
