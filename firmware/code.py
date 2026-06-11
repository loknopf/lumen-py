# SPDX-License-Identifier: MIT
#
# lumen-py firmware entry point — Matrix Portal M4, 64x32 HUB75 panel.
#
# settings.toml must contain:
#   CIRCUITPY_WIFI_SSID = "..."
#   CIRCUITPY_WIFI_PASSWORD = "..."
#   LUMEN_SERVER = "http://192.168.x.x:8080"

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

ssid = getenv("CIRCUITPY_WIFI_SSID")
password = getenv("CIRCUITPY_WIFI_PASSWORD")
if None in (ssid, password):
    raise RuntimeError(
        "WiFi settings are kept in settings.toml, please set "
        "CIRCUITPY_WIFI_SSID and CIRCUITPY_WIFI_PASSWORD."
    )


class SyncingAPI(LumenAPI):
    """LumenAPI that piggybacks an hourly RTC sync on scene boundaries.

    The server reports (epoch_utc, tz_offset); adding the offset *before*
    setting the RTC makes time.localtime() local everywhere else on device.
    """

    _next_sync = 0.0

    def sync_time(self):
        epoch, tz_offset = self.server_time()
        rtc.RTC().datetime = time.localtime(epoch + tz_offset)
        self._next_sync = time.monotonic() + RESYNC_INTERVAL
        print("time synced:", time.localtime())

    def next(self):
        if time.monotonic() >= self._next_sync:
            try:
                self.sync_time()
            except Exception as e:  # non-fatal: clock drifts until next try
                print("time sync failed:", e)
                self._next_sync = time.monotonic() + RESYNC_RETRY
        return super().next()


matrix = Matrix()
display = matrix.display
display.brightness = BRIGHTNESS

network = Network(status_neopixel=board.NEOPIXEL, debug=False)
api = SyncingAPI(network, getenv("LUMEN_SERVER", "http://192.168.1.100:8080"))

print("lumen firmware — server:", api._base)

stage = StageManager(api=api, display=display, remote=RemoteScene(api))
stage.register_local_scene("clock", ClockScene())
stage.run()
