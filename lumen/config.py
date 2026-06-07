"""Configuration.

Everything environment- or deployment-specific lives here and loads from a TOML
file (``config.toml`` by default, overridable with ``LUMEN_CONFIG``). Scenes read
their settings off ``config.scenes[...]`` so adding scene config never touches the
server. Sensible defaults mean the whole thing also runs with no config file at
all (handy for tests and first boot).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class ActiveHours(BaseModel):
    # Informational for the server; the M4 owns sleep scheduling. Exposed via
    # /next so the device could in principle defer to server-side config.
    start: str = "07:00"
    end: str = "00:00"


class Config(BaseModel):
    width: int = 64
    height: int = 32

    #: Ordered rotation of scene ids the stage manager cycles through.
    rotation: list[str] = Field(default_factory=lambda: ["weather", "transit", "github", "countdown", "idle"])

    #: Per-scene duration override (seconds). Falls back to the scene's default.
    durations: dict[str, int] = Field(default_factory=dict)

    #: Per-scene transition override (slide/fade/wipe/dissolve).
    transitions: dict[str, str] = Field(default_factory=dict)

    active_hours: ActiveHours = Field(default_factory=ActiveHours)

    #: Free-form per-scene settings, keyed by scene id.
    scenes: dict[str, dict] = Field(default_factory=dict)

    def scene_config(self, scene_id: str) -> dict:
        return self.scenes.get(scene_id, {})


def load_config(path: str | os.PathLike | None = None) -> Config:
    if path is None:
        path = os.environ.get("LUMEN_CONFIG", "config.toml")
    p = Path(path)
    if not p.exists():
        return Config()
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    return Config.model_validate(data)
