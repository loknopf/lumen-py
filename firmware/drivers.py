"""Scene drivers — the CircuitPython-only half of the firmware.

Both drivers follow the StageManager contract (group / start / tick) and obey
the one allocation rule that matters on a SAMD51: allocate in __init__, only
mutate in start()/tick(). Recreating labels or buffers per tick fragments the
heap and ends in MemoryError hours later.
"""

import gc
import io
import time

import bitmaptools
import displayio
import terminalio
from adafruit_display_text.label import Label

WIDTH = 64
HEIGHT = 32
FRAME_BYTES = WIDTH * HEIGHT * 2  # RGB565, matches lumen.FRAME_BYTES


class RemoteScene:
    """One shared driver for every server-rendered scene.

    The StageManager retargets ``scene_id`` before calling start(), so all
    remote scenes funnel through a single 4 KB buffer and a single bitmap.
    """

    def __init__(self, api):
        self._api = api
        self.scene_id = None
        self._buf = bytearray(FRAME_BYTES)
        self._bitmap = displayio.Bitmap(WIDTH, HEIGHT, 65536)
        shader = displayio.ColorConverter(input_colorspace=displayio.Colorspace.RGB565)
        self.group = displayio.Group()
        self.group.append(displayio.TileGrid(self._bitmap, pixel_shader=shader))

    def start(self):
        gc.collect()  # defragment before the big read
        n = self._api.frame_into(self.scene_id, self._buf)
        if n != FRAME_BYTES:
            raise ValueError("frame %s: got %d bytes" % (self.scene_id, n))
        # Wire format is big-endian RGB565. If colors come out wrong on a new
        # CircuitPython build, flip swap_bytes. (Slow fallback: per-pixel loop
        # bitmap[i % 64, i // 64] = buf[2i] << 8 | buf[2i+1].)
        bitmaptools.readinto(
            self._bitmap,
            io.BytesIO(self._buf),
            bits_per_pixel=16,
            swap_bytes=True,
        )

    def tick(self, now):
        return float("inf")  # static until the scene deadline


class ClockScene:
    """HH:MM:SS local clock, redrawn only when the RTC second changes."""

    def __init__(self, color=0x00FF00):
        self.group = displayio.Group()
        self._label = Label(terminalio.FONT, text="00:00:00", color=color)
        _, _, w, h = self._label.bounding_box
        self._label.x = (WIDTH - w) // 2
        self._label.y = HEIGHT // 2
        self.group.append(self._label)
        self._shown = None

    def start(self):
        self._shown = None  # force a redraw, never show a stale time
        self._redraw()

    def tick(self, now):
        self._redraw()
        # Poll the RTC at 4 Hz instead of sleeping 1 s: a drifting 1 s sleep
        # makes displayed seconds visibly skip/stutter.
        return now + 0.25

    def _redraw(self):
        t = time.localtime()
        current = (t.tm_hour, t.tm_min, t.tm_sec)
        if current != self._shown:  # Label.text assignment allocates; skip no-ops
            self._label.text = "%02d:%02d:%02d" % current
            self._shown = current
