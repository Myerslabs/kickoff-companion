"""Home-screen icons in the team's colors (public release Phase 3): a football in the team's accent
with white laces on a dark ground of its primary color's hue, drawn with the standard library
only and kept on disk under data/icons/ by color, so each icon is drawn once.

The program's icon (owner 2026-10-23, the icon board https://claude.ai/artifact/CAnmauKcs6mpTcndK3PBWQ): the Myers Labs
sun, the app's own loading sun (static/js/ui/states.js), on the app's charcoal. tools/make_icons.py draws it for the
neutral icons in static/icons/ (the ones a page links to before the team is known, and the fallback when drawing fails),
the browser tab, the tray and the program; the team's own home-screen icon stays the football.

    sun_png(size, rounded=True, small=False, scale=1.0)   the sun on its tile: rounded with transparent corners for the
                                                          tab, the tray and the program; square for a home screen
    ico_bytes(pngs)                                       a Windows .ico holding PNG images of several sizes
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


# --- the program's icon: the Myers Labs sun ------------------------------------------------------------------------------
# The drawing in the units of the loading sun's 56-unit box: the tile (corner radius 12, a 1.5 border), the glow (r 14 at a
# quarter), eight rays (round-capped strokes from r 15.5 to 22, 3.2 wide) and the core (r 10). Under 48 px the sturdier one:
# no glow, rays from r 15 to 23 and 5.2 wide, the core r 11.5, so a 16 px tab or tray icon is still a sun.

SUN: RGB = (0xFF, 0xD1, 0x66)  # the loading sun's gold (--stale in static/css/tokens.css)
TILE: RGB = (0x1C, 0x1F, 0x26)  # the charcoal panel
TILE_EDGE: RGB = (0x2D, 0x32, 0x3C)
SUN_FULL = {"glow": 14.0, "ray_in": 15.5, "ray_out": 22.0, "ray_width": 3.2, "core": 10.0}
SUN_SMALL = {"glow": 0.0, "ray_in": 15.0, "ray_out": 23.0, "ray_width": 5.2, "core": 11.5}
SMALL_BELOW = 48


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)  # type: ignore[return-value]


def _sun_shade(x: float, y: float, rounded: bool, small: bool, scale: float) -> tuple[RGB, float]:
    """(color, alpha) at a point of the 56-unit box: the tile, then the sun drawn `scale` times its size about the middle."""
    if rounded:
        qx, qy = max(abs(x - 28) - 16, 0.0), max(abs(y - 28) - 16, 0.0)  # a rounded square: 56 wide, corners of radius 12
        edge = 12 - math.hypot(qx, qy)
        if edge < 0:
            return TILE, 0.0
        color: RGB = TILE_EDGE if (edge < 1.5 and not small) else TILE
    else:
        color = TILE
    shape = SUN_SMALL if small else SUN_FULL
    sx, sy = (x - 28) / scale, (y - 28) / scale
    r = math.hypot(sx, sy)
    if shape["glow"] and r <= shape["glow"]:
        color = _mix(color, SUN, 0.25)
    half = shape["ray_width"] / 2
    for k in range(8):
        a = k * math.pi / 4
        dx, dy = math.sin(a), -math.cos(a)
        t = min(max(sx * dx + sy * dy, shape["ray_in"]), shape["ray_out"])
        if math.hypot(sx - t * dx, sy - t * dy) <= half:
            return SUN, 1.0
    if r <= shape["core"]:
        return SUN, 1.0
    return color, 1.0


def sun_pixels(size: int, rounded: bool = True, small: bool | None = None, scale: float = 1.0, samples: int = 4) -> bytes:
    """RGBA scanlines of the sun icon at `size` px, `samples` squared samples a pixel."""
    small = size < SMALL_BELOW if small is None else small
    rows = []
    n = samples * samples
    unit = 56 / size
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            r = g = b = a = 0.0
            for j in range(samples):
                for i in range(samples):
                    color, alpha = _sun_shade((px + (i + 0.5) / samples) * unit, (py + (j + 0.5) / samples) * unit, rounded, small, scale)
                    r, g, b, a = r + color[0] * alpha, g + color[1] * alpha, b + color[2] * alpha, a + alpha
            if a > 0:
                row += bytes((round(r / a), round(g / a), round(b / a), round(255 * a / n)))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return b"".join(rows)


def png_rgba(size: int, pixels: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


def sun_png(size: int, rounded: bool = True, small: bool | None = None, scale: float = 1.0, samples: int = 4) -> bytes:
    return png_rgba(size, sun_pixels(size, rounded, small, scale, samples))


def ico_bytes(pngs: list[bytes]) -> bytes:
    """A Windows .ico holding each PNG as an image of its own size (Windows reads PNG images since Vista)."""
    entries = b""
    offset = 6 + 16 * len(pngs)
    for data in pngs:
        size = struct.unpack(">I", data[16:20])[0]
        dimension = 0 if size >= 256 else size  # 0 stands for 256
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(pngs)) + entries + b"".join(pngs)


SUN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56">
<!-- Kickoff Companion's icon (owner 2026-10-23): the Myers Labs sun, the app's loading sun, on the charcoal tile; the sturdy
     drawing a browser tab needs (no glow, thick rays). Drawn by tools/make_icons.py. -->
<rect width="56" height="56" rx="12" fill="#1C1F26"/>
<path d="M28 5v8M28 43v8M5 28h8M43 28h8M11.7 11.7l5.7 5.7M38.6 38.6l5.7 5.7M11.7 44.3l5.7-5.7M38.6 17.4l5.7-5.7" stroke="#FFD166" stroke-width="5.2" stroke-linecap="round" fill="none"/>
<circle cx="28" cy="28" r="11.5" fill="#FFD166"/>
</svg>
"""


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
