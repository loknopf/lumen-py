"""Thin HTTP client for the lumen device protocol.

Every fetch closes its response in a finally block: the ESP32 coprocessor has
a handful of sockets, and one leaked response after an exception is how the
firmware runs for an hour and then can't connect anymore.
"""

import json


class LumenAPI:
    def __init__(self, network, base_url):
        self._network = network
        self._base = base_url.rstrip("/")

    def _get_json(self, path):
        resp = self._network.fetch(self._base + path)
        try:
            return json.loads(resp.text)
        finally:
            resp.close()

    def next(self):
        """GET /next -> {"id", "duration", "transition"?}"""
        return self._get_json("/next")

    def server_time(self):
        """GET /health -> (epoch_utc, tz_offset_seconds)."""
        health = self._get_json("/health")
        return health["epoch"], health["tz_offset"]

    def frame_into(self, scene_id, buf):
        """Stream /frame/{id} into buf. Returns total bytes received."""
        resp = self._network.fetch(self._base + "/frame/" + scene_id)
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
