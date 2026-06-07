"""Regenerate golden reference images for every registered scene.

    python -m tools.update_golden          # update all
    python -m tools.update_golden weather   # update specific scenes

Run this only when a visual change is intentional, then review the PNG diff in
your VCS before committing.
"""

from __future__ import annotations

import sys

import lumen.scenes  # noqa: F401  -- registers scenes
from lumen.registry import SCENES

from tests.golden_utils import GOLDEN_DIR, golden_path, render_scene


def main(argv: list[str]) -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    targets = argv or sorted(SCENES)
    for scene_id in targets:
        if scene_id not in SCENES:
            print(f"skip unknown scene: {scene_id}")
            continue
        img = render_scene(scene_id)
        path = golden_path(scene_id)
        img.save(path)
        # Clean up any stale .actual.png left by a previous failing run.
        actual = path.with_suffix(".actual.png")
        if actual.exists():
            actual.unlink()
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
