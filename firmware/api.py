"""Thin HTTP client for the lumen device protocol.

Every fetch closes its response in a finally block: the ESP32 coprocessor has
a handful of sockets, and one leaked response after an exception is how the
firmware runs for an hour and then can't connect anymore.

Every network call also carries an explicit timeout and must raise rather
than block forever: StageManager's backoff/retry (stagemanager.py) only
triggers on a raised exception.
"""

import json
import time

FETCH_TIMEOUT = 8  # seconds; bounds /next, /health and the /frame connect+headers phase
STREAM_BUDGET = 10  # seconds; total time allowed to drain a /frame body
METRIC_TIMEOUT = 3  # seconds; telemetry must never be able to stall the display loop


class LumenAPI:
    def __init__(
        self,
        network,
        base_url,
        base_port,
        metrics_url=None,
        metrics_port=None,
        rot=None,
    ):
        self._network = network
        self._base = (base_url + ":" + base_port).rstrip("/")
        self._metric = None
        if metrics_url and metrics_port:
            self._metric = (metrics_url + ":" + metrics_port).rstrip("/")
        self._rot = "0" if rot is None else rot

    def _get_json(self, path):
        start = time.monotonic()
        resp = self._network.fetch(self._base + path, timeout=FETCH_TIMEOUT)
        end = time.monotonic()
        try:
            return json.loads(resp.text)
        finally:
            resp.close()
            self._log_api_timing(end - start)

    def next(self):
        """GET /next -> {"id", "duration", "transition"?}"""
        return self._get_json("/next")

    def server_time(self):
        """GET /health -> (epoch_utc, tz_offset_seconds, active_start, active_end)."""
        health = self._get_json("/health")
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
        end = time.monotonic()
        try:
            offset = 0
            stream_start = time.monotonic()
            for chunk in resp.iter_content(chunk_size=512):
                n = len(chunk)
                if offset + n <= len(buf):
                    buf[offset : offset + n] = chunk
                offset += n
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
            self._log_api_timing(end - start)

    def log_measurement(self, data):
        """Best-effort send of a line-protocol value to telegraf.

        Telemetry must never be able to stall the display loop, so failures
        (including timeouts) are bounded and swallowed here rather than
        propagating.
        """
        if not self._metric:
            return
        try:
            self._network._wifi.requests.post(
                self._metric + "/telegraf",
                data=f"{data}",
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=METRIC_TIMEOUT,
            )
        except Exception as e:  # non-fatal: telemetry is best-effort
            print("telemetry post failed:", e)

    def _log_api_timing(self, duration):
        lp = "api_timing,device=matrixportal,endpoint=influxdb duration_ms={:.1f}".format(
            duration
        )
        self.log_measurement(lp)
