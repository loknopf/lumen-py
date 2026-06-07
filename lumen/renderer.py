"""Frame rendering with TTL caching and a hard fallback.

The M4 fetches ``/frame/{id}`` on every rotation, but upstream data (weather,
transit) changes slowly — so we cache encoded frames per scene for ``scene.ttl``
seconds. A frame request therefore never blocks on a slow API.

Two guarantees the protocol demands:
- ``/frame`` must *always* return exactly FRAME_BYTES valid bytes.
- A failing scene must not take down the display. On render error we serve the
  last good frame if we have one, otherwise a generated error frame.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from . import FRAME_BYTES
from .canvas import Canvas
from .config import Config
from .registry import SCENES
from .scene import RenderContext, Scene


@dataclass
class _CacheEntry:
    data: bytes
    expires_at: float


class FrameRenderer:
    def __init__(self, config: Config, now_fn=datetime.now):
        self.config = config
        self._now_fn = now_fn
        self._cache: dict[str, _CacheEntry] = {}
        self._last_good: dict[str, bytes] = {}

    def _render_scene(self, scene: Scene) -> bytes:
        ctx = RenderContext(now=self._now_fn(), config=self.config)
        canvas = scene.render(ctx)
        data = canvas.to_rgb565()
        if len(data) != FRAME_BYTES:
            raise ValueError(
                f"scene {scene.id!r} produced {len(data)} bytes, expected {FRAME_BYTES}"
            )
        return data

    def frame(self, scene_id: str) -> bytes:
        scene = SCENES.get(scene_id)
        if scene is None:
            return error_frame(f"NO {scene_id}")

        entry = self._cache.get(scene_id)
        if entry is not None and entry.expires_at > time.monotonic():
            return entry.data

        try:
            data = self._render_scene(scene)
        except Exception as exc:  # noqa: BLE001 - never let a scene break the panel
            import logging

            logging.getLogger("lumen").exception("scene %s failed: %s", scene_id, exc)
            return self._last_good.get(scene_id) or error_frame(f"ERR {scene_id}")

        self._cache[scene_id] = _CacheEntry(data, time.monotonic() + scene.ttl)
        self._last_good[scene_id] = data
        return data

    def invalidate(self, scene_id: str | None = None) -> None:
        if scene_id is None:
            self._cache.clear()
        else:
            self._cache.pop(scene_id, None)


def error_frame(message: str) -> bytes:
    """A red diagnostic frame, guaranteed FRAME_BYTES long."""
    canvas = Canvas()
    canvas.clear((40, 0, 0))
    canvas.rect(0, 0, canvas.width, canvas.height, (180, 0, 0))
    canvas.text_centered(13, message[:12], (255, 120, 120), font="4x6")
    return canvas.to_rgb565()
