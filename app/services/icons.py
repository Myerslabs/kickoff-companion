"""Home-screen icons in the team's colors (public release Phase 3): a football in the team's accent
with white laces on a dark ground of its primary color's hue, drawn with the standard library
only and kept on disk under data/icons/ by color, so each icon is drawn once.

tools/make_icons.py uses the same drawing for the neutral icons in static/icons/ (the ones a page
links to before the team is known, and the fallback when drawing fails).
"""

from __future__ import annotations

import colorsys
import hashlib
import logging
import math
import struct
import zlib
from pathlib import Path

log = logging.getLogger("kickoff.icons")

RGB = tuple[int, int, int]
SIZES = {"icon-180.png": (180, 0.88), "icon-192.png": (192, 0.88), "icon-512.png": (512, 0.88), "icon-maskable-512.png": (512, 0.66)}
WHITE: RGB = (0xF2, 0xF4, 0xFA)
NEUTRAL_GROUND: RGB = (0x14, 0x18, 0x24)
NEUTRAL_BALL: RGB = (0xB0, 0x6A, 0x3B)  # a leather brown: the icon before a team is known


def hex_rgb(value: str | None) -> RGB | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return None
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return None


def team_colors(color: str | None, alt_color: str | None) -> tuple[RGB, RGB]:
    """(ground, ball) for a team: the ground is the primary's hue, dark; the ball is the second color
    when it is a real color (not white, black or gray), else the primary made bright enough to show."""
    primary = hex_rgb(color)
    if primary is None:
        return NEUTRAL_GROUND, NEUTRAL_BALL
    h, light, s = colorsys.rgb_to_hls(*(c / 255 for c in primary))
    ground = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, 0.12, min(0.6, max(0.3, s)) if s >= 0.12 else 0.18))
    ball = None
    alt = hex_rgb(alt_color)
    if alt is not None:
        ah, al, as_ = colorsys.rgb_to_hls(*(c / 255 for c in alt))
        if as_ >= 0.25 and 0.15 < al < 0.9:
            ball = alt
    if ball is None:
        ball = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, max(light, 0.5), max(s, 0.55)))
    return ground, ball  # type: ignore[return-value]


def _shade(x: float, y: float, scale: float, ground: RGB, ball: RGB) -> RGB:
    """The color at a point of the unit square (0..1), for a ball `scale` of the full width."""
    cx, cy = x - 0.5, y - 0.5
    angle = math.radians(-35)  # the ball: an ellipse turned 35 degrees
    u = (cx * math.cos(angle) - cy * math.sin(angle)) / scale
    v = (cx * math.sin(angle) + cy * math.cos(angle)) / scale
    if (u / 0.46) ** 2 + (v / 0.27) ** 2 > 1.0:
        return ground
    if abs(v) < 0.018 and abs(u) < 0.19:  # the seam
        return WHITE
    for i in range(-3, 3):  # six stitches across it
        if abs(u - (i + 0.5) * 0.065) < 0.012 and abs(v) < 0.06:
            return WHITE
    if 0.30 < abs(u) < 0.335:  # the stripes near each tip
        return WHITE
    return ball


def render(size: int, scale: float, ground: RGB, ball: RGB, samples: int = 3) -> bytes:
    rows = []
    n = samples * samples
    for py in range(size):
        row = bytearray([0])  # filter type 0 for this scanline
        for px in range(size):
            r = g = b = 0
            for sy in range(samples):
                for sx in range(samples):
                    color = _shade((px + (sx + 0.5) / samples) / size, (py + (sy + 0.5) / samples) / size, scale, ground, ball)
                    r, g, b = r + color[0], g + color[1], b + color[2]
            row += bytes((round(r / n), round(g / n), round(b / n)))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int, pixels: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


def icon_bytes(name: str, ground: RGB, ball: RGB, samples: int = 3) -> bytes:
    size, scale = SIZES[name]
    return png(size, render(size, scale, ground, ball, samples))


class IconStore:
    """Team icons on disk: data/icons/<colors>-<name>, drawn on first request."""

    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "icons"

    def path_for(self, name: str, ground: RGB, ball: RGB) -> Path:
        key = hashlib.sha1(f"{ground}{ball}".encode()).hexdigest()[:10]
        return self.dir / f"{key}-{name}"

    def get(self, name: str, color: str | None, alt_color: str | None) -> bytes:
        """The icon's PNG bytes; raises KeyError for an unknown name and OSError when the disk fails."""
        if name not in SIZES:
            raise KeyError(name)
        ground, ball = team_colors(color, alt_color)
        path = self.path_for(name, ground, ball)
        if path.is_file():
            return path.read_bytes()
        data = icon_bytes(name, ground, ball)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        except OSError as exc:
            log.warning("Could not keep the icon %s: %s", path.name, exc)
        return data
