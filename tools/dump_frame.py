"""Dump a scene to artifacts for hardware bring-up / manual inspection.

    python -m tools.dump_frame weather

Writes:
    weather.bin  - raw 4096-byte RGB565 frame (exactly what /frame returns)
    weather.png  - 8x upscaled PNG preview

Useful for sanity-checking the wire format against the M4 without the server.
"""

from __future__ import annotations

import sys
from datetime import datetime

import lumen.scenes  # noqa: F401
from lumen.config import load_config
from lumen.registry import SCENES
from lumen.scene import RenderContext


def main(argv: list[str]) -> int:
    if not argv:
        print(f"usage: python -m tools.dump_frame <scene_id>   ({', '.join(sorted(SCENES))})")
        return 2
    scene_id = argv[0]
    scene = SCENES.get(scene_id)
    if scene is None:
        print(f"unknown scene: {scene_id}")
        return 1
    ctx = RenderContext(now=datetime.now(), config=load_config())
    canvas = scene.render(ctx)

    with open(f"{scene_id}.bin", "wb") as fh:
        fh.write(canvas.to_rgb565())
    with open(f"{scene_id}.png", "wb") as fh:
        fh.write(canvas.to_png(scale=8))
    print(f"wrote {scene_id}.bin (4096 bytes) and {scene_id}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
