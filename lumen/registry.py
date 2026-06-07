"""Scene registry.

Scenes register themselves at import time via the ``@register`` decorator, so the
rest of the system never hard-codes a scene list. Importing ``lumen.scenes`` pulls
in every scene module and populates ``SCENES``.
"""

from __future__ import annotations

from .scene import Scene

SCENES: dict[str, Scene] = {}


def register(cls: type[Scene]) -> type[Scene]:
    """Class decorator: instantiate the scene and add it to the registry."""
    instance = cls()
    if not instance.id:
        raise ValueError(f"{cls.__name__} must define a non-empty `id`")
    if instance.id in SCENES:
        raise ValueError(f"duplicate scene id: {instance.id!r}")
    SCENES[instance.id] = instance
    return cls


def get_scene(scene_id: str) -> Scene | None:
    return SCENES.get(scene_id)


def all_scenes() -> dict[str, Scene]:
    return dict(SCENES)
