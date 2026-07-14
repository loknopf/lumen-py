# SPDX-License-Identifier: MIT
#
# lumen-py firmware entry point — Matrix Portal M4, 64x32 HUB75 panel.
#
# settings.toml must contain:
#   CIRCUITPY_WIFI_SSID = "..."
#   CIRCUITPY_WIFI_PASSWORD = "..."
#   LUMEN_SERVER = "http://192.168.x.x:8080"

import alarm
import alarm.time
import time
from os import getenv

import board
import rtc
from adafruit_matrixportal.matrix import Matrix
from adafruit_matrixportal.network import Network
from api import LumenAPI
from drivers import ClockScene, RemoteScene
from stagemanager import StageManager

BRIGHTNESS = 0.3
RESYNC_INTERVAL = 3600  # re-sync the RTC from the server once an hour
RESYNC_RETRY = 300  # ...but retry sooner after a failed sync
SLEEP_CHECK_INTERVAL = 60  # re-check active hours independently of RTC resync

def _parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


def _is_active(active_start, active_end):
    start = _parse_hhmm(active_start)
    end = _parse_hhmm(active_end)
    if end == 0:
        end = 86400  # "00:00" means midnight = end of day
    lt = time.localtime()
    now = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
    return start <= now < end


def _secs_until_active(active_start):
    start = _parse_hhmm(active_start)
    lt = time.localtime()
    now = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
    diff = start - now
    return diff if diff > 0 else diff + 86400


def _maybe_deep_sleep(active_start, active_end):
    if not _is_active(active_start, active_end):
        secs = _secs_until_active(active_start)
        print("outside active hours — deep sleep for", secs, "s until", active_start)
        time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + secs)
        alarm.exit_and_deep_sleep_until_alarms(time_alarm)


ssid = getenv("CIRCUITPY_WIFI_SSID")
password = getenv("CIRCUITPY_WIFI_PASSWORD")
if None in (ssid, password):
    raise RuntimeError(
        "WiFi settings are kept in settings.toml, please set "
        "CIRCUITPY_WIFI_SSID and CIRCUITPY_WIFI_PASSWORD."
    )


class SyncingAPI(LumenAPI):
    """LumenAPI that piggybacks an hourly RTC sync on scene boundaries.

    The server reports (epoch_utc, tz_offset, active_start, active_end); adding
    the offset *before* setting the RTC makes time.localtime() local everywhere
    else on device. Independently of the resync, active_hours is re-checked
    every SLEEP_CHECK_INTERVAL so the device reacts promptly to the window
    boundary rather than waiting for the next (hourly) RTC sync.
    """

    _next_sync = 0.0
    _next_sleep_check = 0.0
    _active_start = "07:00"
    _active_end = "00:00"
    _synced = False

    def sync_time(self):
        epoch, tz_offset, active_start, active_end = self.server_time()
        rtc.RTC().datetime = time.localtime(epoch + tz_offset)
        self._active_start = active_start
        self._active_end = active_end
        self._next_sync = time.monotonic() + RESYNC_INTERVAL
        self._synced = True
        print("time synced:", time.localtime())

    def next(self):
        now = time.monotonic()
        if now >= self._next_sync:
            try:
                self.sync_time()
            except Exception as e:  # non-fatal: clock drifts until next try
                print("time sync failed:", e)
                self._next_sync = now + RESYNC_RETRY
        # Gated on _synced: without a real RTC value yet, localtime() is
        # meaningless and would risk sleeping on garbage time.
        if self._synced and now >= self._next_sleep_check:
            self._next_sleep_check = now + SLEEP_CHECK_INTERVAL
            _maybe_deep_sleep(self._active_start, self._active_end)
        return super().next()


matrix = Matrix()
display = matrix.display
display.rotation = int(getenv("LUMEN_ROTATION_DEG", 0))
display.brightness = BRIGHTNESS

network = Network(status_neopixel=board.NEOPIXEL, debug=False)
api = SyncingAPI(
    network,
    getenv("LUMEN_SERVER", "http://192.168.1.100"),
    getenv("LUMEN_PORT", "8080"),
    getenv("METRICS_SERVER", None),
    getenv("METRICS_PORT", None),
)

print("lumen firmware — server:", api._base)

stage = StageManager(api=api, display=display, remote=RemoteScene(api))
stage.register_local_scene("clock", ClockScene())
stage.run()
