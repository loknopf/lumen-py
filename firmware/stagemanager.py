"""Deadline-driven scene loop for the Matrix Portal M4.

Hardware-agnostic by construction: display, API client, drivers and clock
functions are injected, so this module imports and runs on CPython (see
tests/test_firmware_loop.py). CircuitPython-specific code lives in drivers.py
and code.py.

A scene driver is anything with:
    group               displayio.Group shown while the scene is active
    start()             called once per activation; draws/fetches the first frame
    tick(now) -> float  updates if needed; returns monotonic time of the next
                        wanted tick (INF = static, just wait for the deadline)
"""

import time

INF = float("inf")

#: Max sleep per loop iteration; keeps the loop responsive for future work
#: (buttons, watchdog feed) without busy-spinning.
TICK_CAP = 0.1

BACKOFF_INITIAL = 5
BACKOFF_MAX = 60


class StageManager:
    def __init__(
        self,
        api,
        display,
        remote,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self._api = api
        self._display = display  # needs only .root_group
        self._remote = remote  # shared driver for all server-rendered scenes
        self._local_scenes = {}
        self._monotonic = monotonic
        self._sleep = sleep
        self._backoff = BACKOFF_INITIAL
        self._driver = None

    def register_local_scene(self, id: str, scene):
        self._local_scenes[id] = scene

    def _resolve(self, scene_id):
        driver = self._local_scenes.get(scene_id)
        if driver is None:
            driver = self._remote
            driver.scene_id = scene_id
        return driver

    def _advance(self):
        """Fetch /next and activate that scene. Returns the new deadline."""
        info = self._api.next()
        driver = self._resolve(info["id"])
        # start() before the group swap: if the fetch fails mid-way the old
        # scene stays intact on the panel.
        driver.start()
        self._display.root_group = driver.group
        self._driver = driver
        self._backoff = BACKOFF_INITIAL
        return self._monotonic() + info.get("duration", 8)

    def run(self, max_iterations=None):
        """Run the scene loop forever. max_iterations is test-only scaffolding."""
        deadline = -1.0  # already expired: first iteration fetches immediately
        next_tick = INF

        while max_iterations is None or max_iterations > 0:
            if max_iterations is not None:
                max_iterations -= 1

            now = self._monotonic()

            if now >= deadline:
                try:
                    deadline = self._advance()
                    next_tick = now  # let the fresh scene tick right away
                except Exception as ex:  # server/network down: keep current scene
                    print("advance failed:", ex)
                    deadline = now + self._backoff
                    self._backoff = min(self._backoff * 2, BACKOFF_MAX)

            if self._driver is not None and now >= next_tick:
                try:
                    next_tick = self._driver.tick(now)
                except Exception as ex:  # broken scene must not kill the loop
                    print("tick failed:", ex)
                    next_tick = now + 1.0

            wake = min(next_tick, deadline)
            self._sleep(min(TICK_CAP, max(0.0, wake - self._monotonic())))
