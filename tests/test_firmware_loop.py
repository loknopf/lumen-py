"""Firmware StageManager loop: deadline rotation, local-scene precedence,
tick scheduling and network-failure backoff.

The firmware ships as flat modules on CIRCUITPY, so the firmware dir goes on
sys.path and ``stagemanager`` is imported as a top-level module — exactly as
the device sees it. Time is fully simulated via the injected monotonic/sleep.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "firmware"))

import stagemanager  # noqa: E402
from stagemanager import BACKOFF_INITIAL, INF, StageManager  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        # Floor keeps simulated time advancing even for zero-length sleeps.
        self.t += max(seconds, 0.01)


class FakeDriver:
    """tick_interval=None -> static scene (returns INF)."""

    def __init__(self, tick_interval: float | None = None):
        self.group = object()
        self.scene_id = None  # only used when acting as the remote driver
        self.starts = 0
        self.ticks: list[float] = []
        self._interval = tick_interval

    def start(self) -> None:
        self.starts += 1

    def tick(self, now: float) -> float:
        self.ticks.append(now)
        return INF if self._interval is None else now + self._interval


class FakeDisplay:
    root_group = None


class FakeAPI:
    """Plays back a script of /next responses (dicts) or errors (Exceptions).

    The last entry repeats forever. Records the simulated time of every call.
    """

    def __init__(self, clock: FakeClock, script: list):
        self._clock = clock
        self._script = list(script)
        self.call_times: list[float] = []
        self.events: list[tuple] = []

    def next(self) -> dict:
        self.call_times.append(self._clock.t)
        item = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        if isinstance(item, Exception):
            raise item
        return dict(item)

    def log_event(self, event, **fields) -> None:
        self.events.append((event, fields))


def make_stage(script, local=None):
    clock = FakeClock()
    api = FakeAPI(clock, script)
    display = FakeDisplay()
    remote = FakeDriver()
    stage = StageManager(
        api=api,
        display=display,
        remote=remote,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    for scene_id, driver in (local or {}).items():
        stage.register_local_scene(scene_id, driver)
    return stage, api, display, remote, clock


def test_next_is_consulted_only_at_deadlines():
    stage, api, display, remote, clock = make_stage([{"id": "weather", "duration": 5}])
    stage.run(max_iterations=60)  # ~6 simulated seconds at the 0.1s tick cap

    assert len(api.call_times) == 2  # t=0 and t=5, nothing in between
    assert api.call_times[0] == 0.0
    assert abs(api.call_times[1] - 5.0) < 0.3
    assert display.root_group is remote.group


def test_local_registry_beats_remote_and_remote_gets_scene_id():
    local_clock = FakeDriver(tick_interval=1.0)
    stage, api, display, remote, clock = make_stage(
        [{"id": "clock", "duration": 5}, {"id": "weather", "duration": 60}],
        local={"clock": local_clock},
    )
    stage.run(max_iterations=60)

    assert local_clock.starts == 1
    assert remote.starts == 1
    assert remote.scene_id == "weather"
    assert display.root_group is remote.group  # weather is active at the end


def test_tick_scheduling_honours_driver_request():
    ticking = FakeDriver(tick_interval=1.0)
    stage, api, display, remote, clock = make_stage(
        [{"id": "clock", "duration": 60}], local={"clock": ticking}
    )
    stage.run(max_iterations=50)  # ~5 simulated seconds, single activation

    # Roughly one tick per simulated second (first fires immediately).
    assert 4 <= len(ticking.ticks) <= 7
    deltas = [b - a for a, b in zip(ticking.ticks, ticking.ticks[1:])]
    assert all(0.9 < d < 1.2 for d in deltas)


def test_static_scene_is_ticked_exactly_once_per_activation():
    stage, api, display, remote, clock = make_stage([{"id": "weather", "duration": 60}])
    stage.run(max_iterations=50)
    assert remote.ticks and len(remote.ticks) == 1


def test_failure_keeps_current_scene_and_backs_off():
    boom = RuntimeError("server down")
    local = FakeDriver(tick_interval=1.0)
    stage, api, display, remote, clock = make_stage(
        [
            {"id": "clock", "duration": 2},  # t=0
            boom,  #                           t=2  -> retry in 5
            boom,  #                           t=7  -> retry in 10
            {"id": "weather", "duration": 2},  # t=17 -> success resets backoff
            boom,  #                           t=19 -> retry in 5 again
            {"id": "weather", "duration": 1000},  # t=24
        ],
        local={"clock": local},
    )
    stage.run(max_iterations=600)

    expected = [0.0, 2.0, 7.0, 17.0, 19.0, 24.0]
    assert len(api.call_times) == len(expected)
    for got, want in zip(api.call_times, expected):
        assert abs(got - want) < 0.5, (api.call_times, expected)

    # During the outage the panel kept showing the last good scene...
    assert local.starts == 1
    # ...and it kept ticking (clock keeps running while the server is down).
    assert len(local.ticks) > 10
    # Successful advance reset the backoff for the next failure streak.
    assert stage._backoff == BACKOFF_INITIAL

    # Each failure reported itself as telemetry with the wait time actually used.
    assert [event for event, _ in api.events] == ["advance_fail"] * 3
    assert [fields["retry_in"] for _, fields in api.events] == [5, 10, 5]


def test_watchdog_fed_every_iteration():
    clock = FakeClock()
    api = FakeAPI(clock, [{"id": "weather", "duration": 5}])
    display = FakeDisplay()
    remote = FakeDriver()
    feeds = []
    stage = StageManager(
        api=api,
        display=display,
        remote=remote,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        feed_watchdog=lambda: feeds.append(clock.t),
    )
    stage.run(max_iterations=60)

    # One feed per loop iteration, regardless of whether a fetch/tick ran.
    assert len(feeds) == 60


def test_broken_tick_does_not_kill_the_loop():
    class BrokenDriver(FakeDriver):
        def tick(self, now):
            super().tick(now)
            raise ValueError("scene bug")

    broken = BrokenDriver()
    stage, api, display, remote, clock = make_stage(
        [{"id": "clock", "duration": 5}], local={"clock": broken}
    )
    stage.run(max_iterations=60)  # must not raise

    assert len(broken.ticks) > 1  # retried roughly once a second
    assert len(api.call_times) == 2  # rotation continued past the broken scene
