"""Shared test fixtures.

The golden tests need *deterministic* rendering, so every scene is rendered with
a frozen clock and the default (stub) config. Because the scenes use bitmap fonts
and integer primitives (no anti-aliasing), identical inputs produce byte-identical
output — which makes exact-match golden comparison reliable.
"""

from __future__ import annotations

from datetime import datetime

import pytest

import lumen.scenes  # noqa: F401  -- registers all scenes
from lumen.config import Config
from lumen.scene import RenderContext

# A fixed instant used for every golden render. Chosen so date/countdown output
# is stable: a Saturday.
FROZEN_NOW = datetime(2026, 6, 6, 9, 30, 0)


@pytest.fixture
def frozen_now() -> datetime:
    return FROZEN_NOW


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def make_ctx(config):
    def _make(now: datetime = FROZEN_NOW) -> RenderContext:
        return RenderContext(now=now, config=config)

    return _make
