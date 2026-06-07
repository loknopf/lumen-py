"""Stage-manager behaviour: rotation order and priority injection."""

from __future__ import annotations

import lumen.scenes  # noqa: F401
from lumen.config import Config
from lumen.stage import StageManager


def test_round_robin_follows_config_order():
    cfg = Config(rotation=["weather", "github", "idle"])
    stage = StageManager(cfg)
    ids = [stage.next().id for _ in range(6)]
    assert ids == ["weather", "github", "idle", "weather", "github", "idle"]


def test_unknown_ids_are_skipped():
    cfg = Config(rotation=["weather", "does-not-exist", "idle"])
    stage = StageManager(cfg)
    ids = [stage.next().id for _ in range(4)]
    assert ids == ["weather", "idle", "weather", "idle"]


def test_priority_injection_is_one_shot_and_jumps_queue():
    cfg = Config(rotation=["weather", "github"])
    stage = StageManager(cfg)
    assert stage.next().id == "weather"
    assert stage.inject("idle") is True
    assert stage.next().id == "idle"  # injected scene jumps ahead
    assert stage.next().id == "github"  # rotation resumes where it left off


def test_inject_unknown_scene_rejected():
    stage = StageManager(Config())
    assert stage.inject("nope") is False


def test_duration_override_from_config():
    cfg = Config(rotation=["weather"], durations={"weather": 99})
    stage = StageManager(cfg)
    nxt = stage.next()
    assert nxt.id == "weather"
    assert nxt.duration == 99


def test_transition_passthrough():
    cfg = Config(rotation=["weather"])
    stage = StageManager(cfg)
    assert stage.next().transition == "fade"  # weather's default
