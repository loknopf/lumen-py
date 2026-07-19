"""Thin HTTP client for the lumen device protocol, plus MQTT telemetry.

Every fetch closes its response in a finally block: the ESP32 coprocessor has
a handful of sockets, and one leaked response after an exception is how the
firmware runs for an hour and then can't connect anymore.

Every network call also carries an explicit timeout and must raise rather
than block forever: StageManager's backoff/retry (stagemanager.py) only
triggers on a raised exception.

Telemetry (api_timing / device_vitals / resilience_event) is a separate,
best-effort channel published as InfluxDB line protocol to an MQTT broker —
it must never be able to stall the display loop, so every telemetry failure
(including a dead broker connection) is bounded and swallowed here.
"""

import gc
import json
import time

import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_esp32spi import adafruit_esp32spi_socketpool

FETCH_TIMEOUT = 8  # seconds; bounds /next, /health and the /frame connect+headers phase
STREAM_BUDGET = 10  # seconds; total time allowed to drain a /frame body
METRIC_TIMEOUT = 3  # seconds; telemetry must never be able to stall the display loop


class LumenAPI:
    def __init__(
        self,
        network,
        base_url,
        base_port,
        mqtt_broker=None,
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password=None,
        device_id="matrixportal",
        rot=None,
        feed_watchdog=lambda: None,
    ):
        self._network = network
        self._base = (base_url + ":" + base_port).rstrip("/")
        self._rot = "0" if rot is None else rot
        self._device_id = device_id
        self._topic = "lumen/" + device_id + "/telemetry"
        self._boot_mono = time.monotonic()
        # Fed after every blocking network op below, so a genuinely wedged
        # call (e.g. a stuck ESP32 coprocessor) is still caught by the
        # hardware watchdog well within its timeout, while a normal slow
        # call chain (sync + heartbeat + next, or a slow frame stream)
        # doesn't false-trip it.
        self._feed_watchdog = feed_watchdog

        # mqtt_broker is optional: telemetry is a nice-to-have, so a missing
        # broker config must not stop the device protocol from working.
        self._mqtt = None
        if mqtt_broker:
            pool = adafruit_esp32spi_socketpool.SocketPool(self._network._wifi.esp)
            self._mqtt = MQTT.MQTT(
                broker=mqtt_broker,
                port=mqtt_port,
                username=mqtt_username,
                password=mqtt_password,
                socket_pool=pool,
                socket_timeout=METRIC_TIMEOUT,
                connect_retries=1,
            )

    def reconnect(self):
        """Hard-reset the ESP32 co-processor and reassociate WiFi.

        Recovery path for the failure mode this module's docstring warns
        about: a leaked/exhausted socket can wedge the co-processor's socket
        table for HTTP fetches while WiFi association keeps failing.

        MQTT is disconnected *before* the reset to be able to reconnect to the broker
        after the connection to WiFi has been restored and is not blocked by a stale reference
        to that (then dead) socket.
        """
        if self._mqtt is not None:
            try:
                self._mqtt.disconnect()
            except Exception:
                pass  # best-effort: the registry cleanup is what matters here
        self._network._wifi.esp.reset()
        self._network.connect()
        self._feed_watchdog()

    def _ensure_mqtt(self):
        if self._mqtt is None:
            return False
        if self._mqtt.is_connected():
            return True
        try:
            self._mqtt.connect()
            return True
        except Exception as e:  # non-fatal: telemetry is best-effort
            print("mqtt connect failed:", e)
            return False
        finally:
            self._feed_watchdog()

    def _publish(self, line):
        if not self._ensure_mqtt():
            return
        try:
            self._mqtt.publish(self._topic, line)
        except Exception as e:  # non-fatal: telemetry is best-effort
            print("mqtt publish failed:", e)
        finally:
            self._feed_watchdog()

    def _get_json(self, path, endpoint):
        start = time.monotonic()
        resp = self._network.fetch(self._base + path, timeout=FETCH_TIMEOUT)
        self._feed_watchdog()
        end = time.monotonic()
        try:
            return json.loads(resp.text)
        finally:
            resp.close()
            self._log_api_timing(endpoint, end - start)

    def next(self):
        """GET /next -> {"id", "duration", "transition"?}"""
        return self._get_json("/next", "next")

    def server_time(self):
        """GET /health -> (epoch_utc, tz_offset_seconds, active_start, active_end)."""
        health = self._get_json("/health", "health")
        return (
            health["epoch"],
            health["tz_offset"],
            health.get("active_start", "07:00"),
            health.get("active_end", "00:00"),
        )

    def frame_into(self, scene_id, buf):
        """Stream /frame/{id} into buf. Returns total bytes received."""
        start = time.monotonic()
        resp = self._network.fetch(
            self._base + "/frame/" + scene_id + "?rot=" + self._rot,
            timeout=FETCH_TIMEOUT,
        )
        self._feed_watchdog()
        end = time.monotonic()
        try:
            offset = 0
            stream_start = time.monotonic()
            for chunk in resp.iter_content(chunk_size=512):
                n = len(chunk)
                if offset + n <= len(buf):
                    buf[offset : offset + n] = chunk
                offset += n
                self._feed_watchdog()
                # A stall after partial data (headers arrived, body froze) isn't
                # covered by the fetch() timeout above, which only bounds
                # connect+headers — bound the whole stream too.
                if time.monotonic() - stream_start > STREAM_BUDGET:
                    raise TimeoutError(
                        "frame %s: stalled after %d bytes" % (scene_id, offset)
                    )
            return offset
        finally:
            resp.close()
            self._log_api_timing("frame", end - start)

    def log_measurement(self, data):
        """Best-effort publish of a pre-formatted line-protocol value."""
        self._publish(f"{data}")

    def log_event(self, event, **fields):
        """Best-effort publish of a resilience_event line (boot, sync_fail, ...).

        Line protocol requires string field values to be quoted (bare tokens
        parse as int/float/bool) — numeric fields are written bare, anything
        else is quoted.
        """
        parts = ['event="{}"'.format(event)]
        for k, v in fields.items():
            if isinstance(v, bool):
                parts.append("{}={}".format(k, str(v).lower()))
            elif isinstance(v, (int, float)):
                parts.append("{}={}".format(k, v))
            else:
                parts.append('{}="{}"'.format(k, v))
        line = "resilience_event,device={} {}".format(self._device_id, ",".join(parts))
        self._publish(line)

    def log_vitals(self):
        """Best-effort publish of a device_vitals heartbeat line."""
        try:
            free_mem = gc.mem_free()
        except Exception:
            free_mem = -1
        try:
            rssi = self._network._wifi.esp.ap_info.rssi
        except Exception:
            rssi = 0
        uptime = time.monotonic() - self._boot_mono
        line = "device_vitals,device={} free_mem={},uptime_s={:.1f},wifi_rssi={}".format(
            self._device_id, free_mem, uptime, rssi
        )
        self._publish(line)

    def _log_api_timing(self, endpoint, duration):
        lp = "api_timing,device={},endpoint={} duration_ms={:.1f}".format(
            self._device_id, endpoint, duration * 1000
        )
        self.log_measurement(lp)
