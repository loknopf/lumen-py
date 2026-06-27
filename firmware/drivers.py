"""Scene drivers — the CircuitPython-only half of the firmware.

Both drivers follow the StageManager contract (group / start / tick) and obey
the one allocation rule that matters on a SAMD51: allocate in __init__, only
mutate in start()/tick(). Recreating labels or buffers per tick fragments the
heap and ends in MemoryError hours later.
"""

import gc
import io
import math
import random
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
        # CircuitPython build, flip swap_bytes_in_element. (Slow fallback:
        # per-pixel loop bitmap[i % 64, i // 64] = buf[2i] << 8 | buf[2i+1].)
        bitmaptools.readinto(
            self._bitmap,
            io.BytesIO(self._buf),
            bits_per_pixel=16,
            element_size=2,
            swap_bytes_in_element=True,
        )

    def tick(self, now):
        return float("inf")  # static until the scene deadline


class ClockScene:
    """Analog clock + scrolling starfield + time-of-day ambient colour.

    Left half  — analog clock face with sweeping hour/minute/second hands.
    Right half — digital HH:MM and :SS labels floating over the starfield.
    Full canvas — stars drift left at varying speeds; background and star
                  colour shift slowly through a sky palette keyed to the hour.

    The bitmap is redrawn at 4 Hz so the starfield and second hand animate
    smoothly. Labels are updated at 1 Hz only — Label.text allocates on the
    heap and must not run every tick on a SAMD51.
    """

    # (hour, background_24bit, star_24bit, hand_24bit)
    _SKY = [
        (0, 0x000022, 0x8888FF, 0xFFFFFF),  # midnight : deep navy,   cold blue stars
        (6, 0x180A00, 0xFFAA44, 0xFFDD88),  # dawn     : dark amber,  warm gold stars
        (
            12,
            0x001830,
            0x44FFFF,
            0xFFFFFF,
        ),  # noon     : dark teal,   bright white stars
        (18, 0x1A0020, 0xFF6622, 0xFFCC88),  # dusk     : deep purple, orange stars
        (24, 0x000022, 0x8888FF, 0xFFFFFF),  # (wraps back to midnight)
    ]

    _NUM_STARS = 20
    _CX, _CY = 16, 15  # analog clock centre pixel
    _R_FACE = 13  # tick-mark outer radius
    _R_SEC = 11  # second hand length
    _R_MIN = 9  # minute hand length
    _R_HR = 6  # hour hand length

    def __init__(self):
        self.group = displayio.Group()

        # Single RGB565 bitmap — starfield + clock are drawn here every tick
        self._bmp = displayio.Bitmap(WIDTH, HEIGHT, 65536)
        shader = displayio.ColorConverter(input_colorspace=displayio.Colorspace.RGB565)
        self.group.append(displayio.TileGrid(self._bmp, pixel_shader=shader))

        # Digital labels on the right half, layered above the bitmap
        self._lbl_hm = Label(terminalio.FONT, text="00:00", color=0xFFFFFF)
        self._lbl_s = Label(terminalio.FONT, text=":00", color=0x888888)
        _, _, w1, h1 = self._lbl_hm.bounding_box
        _, _, w2, h2 = self._lbl_s.bounding_box
        gap = 2
        top = (HEIGHT - h1 - gap - h2) // 2
        self._lbl_hm.x = 32 + (32 - w1) // 2
        self._lbl_hm.y = top
        self._lbl_s.x = 32 + (32 - w2) // 2
        self._lbl_s.y = top + h1 + gap
        self.group.append(self._lbl_hm)
        self.group.append(self._lbl_s)

        # Stars as plain lists so we can mutate x in-place — no allocation in tick
        self._stars = [
            [random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1), (i % 3) + 1]
            for i in range(self._NUM_STARS)
        ]

        # Clock-face tick marks pre-computed once; stored as tuples (immutable/cheap)
        self._ticks = []
        for i in range(12):
            a = i * math.pi / 6 - math.pi / 2
            rout = self._R_FACE
            rin = self._R_FACE - (2 if i % 3 == 0 else 1)
            self._ticks.append(
                (
                    self._CX + round(rout * math.cos(a)),
                    self._CY + round(rout * math.sin(a)),
                    self._CX + round(rin * math.cos(a)),
                    self._CY + round(rin * math.sin(a)),
                )
            )

        self._shown = None  # (h, m, s) guards Label.text writes
        self._tick_mono = None  # monotonic time of last RTC second tick

    def start(self):
        self._shown = None
        self._tick_mono = None
        self._redraw()

    def tick(self, now):
        self._redraw()
        return now + 0.25

    # ── colour helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _lerp(c1, c2, t):
        r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
        r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
        return (
            (round(r1 + (r2 - r1) * t) << 16)
            | (round(g1 + (g2 - g1) * t) << 8)
            | round(b1 + (b2 - b1) * t)
        )

    @staticmethod
    def _rgb565(c):
        return ((c & 0xF80000) >> 8) | ((c & 0x00FC00) >> 5) | ((c & 0x0000F8) >> 3)

    def _sky_colors(self, h, m):
        fh = h + m / 60
        for i in range(len(self._SKY) - 1):
            h0, bg0, s0, hd0 = self._SKY[i]
            h1, bg1, s1, hd1 = self._SKY[i + 1]
            if h0 <= fh < h1:
                t = (fh - h0) / (h1 - h0)
                return (
                    self._lerp(bg0, bg1, t),
                    self._lerp(s0, s1, t),
                    self._lerp(hd0, hd1, t),
                )
        return self._SKY[-1][1], self._SKY[-1][2], self._SKY[-1][3]

    def _hand_endpoint(self, angle, radius):
        return (
            self._CX + round(radius * math.sin(angle)),
            self._CY - round(radius * math.cos(angle)),
        )

    # ── main draw ─────────────────────────────────────────────────────────────

    def _redraw(self):
        mono = time.monotonic()
        lt = time.localtime()
        h, m, s = lt.tm_hour, lt.tm_min, lt.tm_sec
        current = (h, m, s)

        # Track when each RTC second fires so the second hand can sweep smoothly
        if current != self._shown:
            self._tick_mono = mono
        frac = 0.0 if self._tick_mono is None else min(1.0, mono - self._tick_mono)

        bg_c, star_c, hand_c = self._sky_colors(h, m)
        bg565 = self._rgb565(bg_c)
        star565 = self._rgb565(star_c)
        hand565 = self._rgb565(hand_c)
        # Tick marks at one-third star brightness so they don't compete with hands
        face565 = self._rgb565(
            (((star_c >> 16) & 0xFF) // 3 << 16)
            | (((star_c >> 8) & 0xFF) // 3 << 8)
            | ((star_c & 0xFF) // 3)
        )

        # 1. Flood-fill background
        bitmaptools.fill_region(self._bmp, 0, 0, WIDTH, HEIGHT, bg565)

        # 2. Stars — draw at current position then advance for next tick
        for star in self._stars:
            x, y, spd = star
            self._bmp[x, y] = star565
            star[0] = (x - spd) % WIDTH

        # 3. Clock-face tick marks
        for x1, y1, x2, y2 in self._ticks:
            bitmaptools.draw_line(self._bmp, x1, y1, x2, y2, face565)

        # 4. Clock hands — second hand sweeps smoothly using monotonic sub-second
        sec_a = (s + frac) * math.pi / 30
        min_a = (m + (s + frac) / 60) * math.pi / 30
        hr_a = (h % 12 + m / 60) * math.pi / 6

        for angle, radius in (
            (sec_a, self._R_SEC),
            (min_a, self._R_MIN),
            (hr_a, self._R_HR),
        ):
            ex, ey = self._hand_endpoint(angle, radius)
            bitmaptools.draw_line(self._bmp, self._CX, self._CY, ex, ey, hand565)

        self._bmp[self._CX, self._CY] = hand565  # centre pivot dot

        # 5. Labels — only when the second actually changes (Label.text allocates)
        if current != self._shown:
            self._lbl_hm.text = "%02d:%02d" % (h, m)
            self._lbl_s.text = ":%02d" % s
            self._shown = current
