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
RECONNECT_AFTER = 5  # consecutive advance() failures before trying a network reconnect
HARD_RESET_AFTER = 10  # consecutive advance() failures before giving up and hard-resetting


class StageManager:
    def __init__(
        self,
        api,
        display,
        remote,
        monotonic=time.monotonic,
        sleep=time.sleep,
        feed_watchdog=lambda: None,
        reconnect=lambda: None,
        hard_reset=lambda: None,
    ) -> None:
        self._api = api
        self._display = display  # needs only .root_group
        self._remote = remote  # shared driver for all server-rendered scenes
        self._local_scenes = {}
        self._monotonic = monotonic
        self._sleep = sleep
        # Backstop for hangs that api.py's own timeouts can't reach (e.g. a
        # wedged ESP32 coprocessor blocking below the Python level). code.py
        # wires the real microcontroller.watchdog.feed; tests/CPython get the
        # no-op default so the loop stays hardware-agnostic.
        self._feed_watchdog = feed_watchdog
        # Escalation path for a *sustained* advance() failure streak, wired to
        # real hardware by code.py. Kept as injected callables (like
        # feed_watchdog) so this module stays hardware-agnostic.
        self._reconnect = reconnect
        self._hard_reset = hard_reset
        self._backoff = BACKOFF_INITIAL
        self._consecutive_fails = 0
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
        self._consecutive_fails = 0
        return self._monotonic() + info.get("duration", 8)

    def run(self, max_iterations=None):
        """Run the scene loop forever. max_iterations is test-only scaffolding."""
        deadline = -1.0  # already expired: first iteration fetches immediately
        next_tick = INF

        while max_iterations is None or max_iterations > 0:
            if max_iterations is not None:
                max_iterations -= 1

            self._feed_watchdog()
            now = self._monotonic()

            if now >= deadline:
                try:
                    deadline = self._advance()
                    next_tick = now  # let the fresh scene tick right away
                except Exception as ex:  # server/network down: keep current scene
                    print("advance failed:", ex)
                    retry_in = self._backoff
                    deadline = now + retry_in
                    self._backoff = min(self._backoff * 2, BACKOFF_MAX)
                    self._consecutive_fails += 1
                    reason = "{}: {}".format(type(ex).__name__, ex)
                    self._api.log_event(
                        "advance_fail",
                        retry_in=retry_in,
                        reason=reason,
                        consecutive_fails=self._consecutive_fails,
                    )

                    # A failure streak that survives several backoff cycles while
                    # MQTT/telemetry keeps working (see api.py) points at something
                    # scoped to the fetch path — e.g. a co-processor socket table
                    # wedged by a leaked response — rather than a dead network.
                    # Try a lighter-weight reconnect before escalating further.
                    if self._consecutive_fails == RECONNECT_AFTER:
                        print("advance: reconnecting after", self._consecutive_fails, "failures")
                        try:
                            self._reconnect()
                            print("reconnect: succeeded")
                        except Exception as rex:  # best-effort: keep retrying advance either way
                            print("reconnect failed:", rex)

                    # Reconnect didn't help either: give up and force a real reset,
                    # through a dedicated callback rather than by starving the
                    # watchdog. That makes this an explicit, telemetered decision
                    # instead of a side effect of an unrelated timeout firing.
                    if self._consecutive_fails >= HARD_RESET_AFTER:
                        print("advance: giving up after", self._consecutive_fails, "failures")
                        self._api.log_event(
                            "giving_up",
                            consecutive_fails=self._consecutive_fails,
                            reason=reason,
                        )
                        self._hard_reset()

            self._feed_watchdog()

            if self._driver is not None and now >= next_tick:
                try:
                    next_tick = self._driver.tick(now)
                except Exception as ex:  # broken scene must not kill the loop
                    print("tick failed:", ex)
                    next_tick = now + 1.0

            wake = min(next_tick, deadline)
            self._sleep(min(TICK_CAP, max(0.0, wake - self._monotonic())))
