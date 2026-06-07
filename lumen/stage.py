"""Stage manager — owns scene rotation, durations and priority injection.

The M4 is stateless about ordering: it just asks ``/next`` and is told what to
show. The server holds the rotation pointer. This assumes a single device, which
matches the design; multi-device would key state by device id.

Priority injection lets the server jump a scene to the front of the line once
(e.g. a transit alert, a doorbell). Injected scenes are one-shot and do not
disturb the underlying round-robin position.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .config import Config
from .registry import SCENES


@dataclass
class Scene:
    id: str
    duration: int
    transition: str | None = None


class StageManager:
    def __init__(self, config: Config):
        self.config = config
        self._index = 0
        self._priority: deque[str] = deque()

    def _rotation(self) -> list[str]:
        # Only include ids that actually resolve to a registered scene, so a
        # typo in config can't wedge the device on a 404.
        return [sid for sid in self.config.rotation if sid in SCENES]

    def inject(self, scene_id: str) -> bool:
        """Queue a one-shot priority scene. Returns False for unknown ids."""
        if scene_id not in SCENES:
            return False
        self._priority.append(scene_id)
        return True

    def _describe(self, scene_id: str) -> Scene:
        scene = SCENES[scene_id]
        duration = self.config.durations.get(scene_id, scene.default_duration)
        transition = self.config.transitions.get(scene_id, scene.transition)
        return Scene(id=scene_id, duration=duration, transition=transition)

    def next(self) -> Scene:
        if self._priority:
            return self._describe(self._priority.popleft())

        rotation = self._rotation()
        if not rotation:
            # Nothing configured/registered — fall back to any scene, else idle.
            fallback = next(iter(SCENES), "idle")
            return self._describe(fallback) if fallback in SCENES else Scene("idle", 8)

        scene_id = rotation[self._index % len(rotation)]
        self._index = (self._index + 1) % len(rotation)
        return self._describe(scene_id)

    def current(self) -> Scene:
        if self._priority:
            return self._describe(self._priority[0])
        rotation = self._rotation()
        if not rotation:
            fallback = next(iter(SCENES), "idle")
            return self._describe(fallback) if fallback in SCENES else Scene("idle", 8)
        scene_id = rotation[self._index % len(rotation)]
        return self._describe(scene_id)
