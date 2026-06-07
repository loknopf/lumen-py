"""Helpers shared by the golden test and the update tool."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from lumen.config import Config
from lumen.registry import SCENES
from lumen.scene import RenderContext

GOLDEN_DIR = Path(__file__).parent / "golden"

# Must match tests/conftest.py::FROZEN_NOW for reproducible renders.
FROZEN_NOW = datetime(2026, 6, 6, 9, 30, 0)


def render_scene(scene_id: str) -> Image.Image:
    scene = SCENES[scene_id]
    ctx = RenderContext(now=FROZEN_NOW, config=Config())
    return scene.render(ctx).image()


def golden_path(scene_id: str) -> Path:
    return GOLDEN_DIR / f"{scene_id}.png"
