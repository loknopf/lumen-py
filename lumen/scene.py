"""Scene base class and render context.

A scene is the unit of extensibility. To add one you:

1. Subclass ``Scene``, set ``id`` and (optionally) ``default_duration`` / ``ttl``.
2. Implement ``draw(ctx) -> Canvas``.
3. Decorate the class with ``@register`` (see ``registry.py``).
4. Add the id to the rotation in your config.

That's it — no firmware changes, no server wiring. The stage manager and frame
endpoint discover the scene through the registry.

Data fetching is intentionally separated from drawing. Override ``fetch(ctx)`` to
return whatever your ``draw`` needs; its result is cached for ``ttl`` seconds so a
slow upstream API never blocks an M4 frame request. Scenes that need no external
data can ignore ``fetch`` entirely.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .canvas import Canvas


@dataclass
class RenderContext:
    """Everything a scene needs to render, with no hidden global state.

    ``now`` is injected (not read from the wall clock inside scenes) so that
    rendering is deterministic and golden tests can freeze time.
    """

    now: datetime
    config: Any  # lumen.config.Config — typed loosely to avoid an import cycle
    data: Any = None  # result of fetch(), populated by the renderer
    rot: int = 0


class Scene(ABC):
    #: Stable identifier used in the protocol (``/frame/{id}``) and rotation.
    id: str = ""
    #: How long the M4 should display this scene, in seconds (overridable in config).
    default_duration: int = 8
    #: How long a rendered frame stays cached before re-render, in seconds.
    ttl: int = 60
    #: Optional transition hint passed through ``/next`` (slide/fade/wipe/dissolve).
    transition: str | None = None

    def fetch(self, ctx: RenderContext) -> Any:
        """Return the data ``draw`` needs. Default: nothing. Override for APIs."""
        return None

    @abstractmethod
    def draw(self, ctx: RenderContext) -> Canvas:
        """Render the scene into a fresh Canvas and return it."""

    # Convenience used by tests and tools.
    def render(self, ctx: RenderContext) -> Canvas:
        if ctx.data is None:
            ctx.data = self.fetch(ctx)
        canvas = self.draw(ctx)
        if ctx.rot:
            canvas = canvas.rotate(ctx.rot)
        return canvas
