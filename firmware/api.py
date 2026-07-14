"""Thin HTTP client for the lumen device protocol.

Every fetch closes its response in a finally block: the ESP32 coprocessor has
a handful of sockets, and one leaked response after an exception is how the
firmware runs for an hour and then can't connect anymore.
"""

import json
import time


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
        resp = self._network.fetch(self._base + path)
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
            self._base + "/frame/" + scene_id + "?rot=" + self._rot
        )
        end = time.monotonic()
        try:
            offset = 0
            for chunk in resp.iter_content(chunk_size=512):
                n = len(chunk)
                if offset + n <= len(buf):
                    buf[offset : offset + n] = chunk
                offset += n
            return offset
        finally:
            resp.close()
            self._log_api_timing(end - start)

    def log_measurement(self, data):
        """Send a line-protocol data value to a telegraf instance, collecting metrics"""
        if self._metric:
            self._network._wifi.requests.post(
                self._metric + "/telegraf",
                data=f"{data}",
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )

    def _log_api_timing(self, duration):
        lp = "api_timing,device=matrixportal,endpoint=influxdb duration_ms={:.1f}".format(
            duration
        )
        self.log_measurement(lp)
