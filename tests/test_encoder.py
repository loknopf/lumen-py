"""RGB565 wire-format tests — the protocol's most failure-prone detail."""

from __future__ import annotations

import numpy as np

from lumen import FRAME_BYTES, HEIGHT, WIDTH
from lumen.canvas import Canvas, from_rgb565


def test_frame_is_exactly_4096_bytes():
    assert Canvas().to_rgb565().__len__() == FRAME_BYTES == 4096


def test_white_pixel_is_0xffff_big_endian():
    c = Canvas()
    c.pixel(0, 0, (255, 255, 255))
    data = c.to_rgb565()
    assert data[0:2] == b"\xff\xff"  # big-endian 0xFFFF


def test_pure_red_encoding():
    c = Canvas()
    c.pixel(0, 0, (255, 0, 0))
    # R=0b11111 in the top 5 bits -> 0xF800
    assert c.to_rgb565()[0:2] == b"\xf8\x00"


def test_pure_blue_encoding():
    c = Canvas()
    c.pixel(0, 0, (0, 0, 255))
    assert c.to_rgb565()[0:2] == b"\x00\x1f"


def test_row_major_layout():
    # Pixel (1, 0) is the second value; pixel (0, 1) is at offset WIDTH.
    c = Canvas()
    c.pixel(1, 0, (255, 0, 0))
    c.pixel(0, 1, (0, 0, 255))
    data = c.to_rgb565()
    assert data[2:4] == b"\xf8\x00"
    assert data[WIDTH * 2 : WIDTH * 2 + 2] == b"\x00\x1f"


def test_roundtrip_preserves_quantized_colors():
    c = Canvas()
    c.pixel(3, 4, (248, 252, 248))  # already on the 565 grid
    img = from_rgb565(c.to_rgb565())
    assert np.asarray(img)[4, 3].tolist() == [248, 252, 248]
    assert img.size == (WIDTH, HEIGHT)
