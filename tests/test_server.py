"""Device-protocol endpoints over the FastAPI test client."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from lumen import FRAME_BYTES
from lumen.server import app

client = TestClient(app)


def test_health_reports_server_time_for_rtc_sync():
    body = client.get("/health").json()
    assert body["ok"] is True
    assert abs(body["epoch"] - time.time()) < 5
    # Sanity bounds: real-world UTC offsets are within +/-14 h.
    assert -14 * 3600 <= body["tz_offset"] <= 14 * 3600


def test_health_lists_clock_placeholder_scene():
    body = client.get("/health").json()
    assert "clock" in body["scenes"]


def test_clock_frame_is_servable_like_any_scene():
    # The firmware never fetches it, but the placeholder must still honour
    # the frame protocol (e.g. for /preview and debugging).
    resp = client.get("/frame/clock?rot=0")
    assert resp.status_code == 200
    assert len(resp.content) == FRAME_BYTES
