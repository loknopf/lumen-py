"""lumen-py — server-driven ambient display backend for the Matrix Portal M4."""

# Panel geometry. The M4 drives a 64x32 HUB75 panel; the wire format is one
# big-endian RGB565 value per pixel, row-major (x fast, then y).
WIDTH = 64
HEIGHT = 32
FRAME_BYTES = WIDTH * HEIGHT * 2  # 4096

__all__ = ["WIDTH", "HEIGHT", "FRAME_BYTES"]
