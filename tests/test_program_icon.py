"""The program's icon (owner 2026-10-23, the board https://claude.ai/artifact/CAnmauKcs6mpTcndK3PBWQ, "as drawn, A and B
included"): the Myers Labs sun, the app's loading sun, on the app's charcoal tile, for the program, the tray, the
browser tab on every page and the home-screen icons before a team is picked; the team's own home-screen icon stays the
football. The drawing is the standard library's, like the team icons'."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from app.services.icons import SUN, TILE, ico_bytes, sun_png
from app.services.launcher import Launcher
from tools.package import build

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "static" / "icons"


def decode(data: bytes) -> tuple[int, int, list[bytes]]:
    """(size, channels, rows) of a PNG the drawing wrote (filter 0 on every row)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    size = struct.unpack(">I", data[16:20])[0]
    kind = data[25]
    channels = {2: 3, 6: 4}[kind]
    idat = b""
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        if tag == b"IDAT":
            idat += data[pos + 8:pos + 8 + length]
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = 1 + size * channels
    return size, channels, [raw[i * stride + 1:(i + 1) * stride] for i in range(size)]


def pixel(rows: list[bytes], channels: int, x: int, y: int) -> tuple[int, ...]:
    return tuple(rows[y][x * channels:(x + 1) * channels])


def test_the_sun_sits_on_its_tile_with_clear_corners():
    size, channels, rows = decode(sun_png(64))
    assert (size, channels) == (64, 4)
    assert pixel(rows, channels, 32, 32)[:3] == SUN and pixel(rows, channels, 32, 32)[3] == 255, "the core is the loading sun's gold"
    assert pixel(rows, channels, 0, 0)[3] == 0, "a rounded tile: the corner is clear"
    assert pixel(rows, channels, 4, 32)[:3] in (TILE, (0x2D, 0x32, 0x3C)) or pixel(rows, channels, 4, 32)[3] == 255
    assert pixel(rows, channels, 32, 2)[3] == 255, "the tile reaches the edge in the middle of a side"


def test_a_home_screen_icon_is_square_and_a_small_one_is_sturdy():
    size, channels, rows = decode(sun_png(48, rounded=False))
    assert pixel(rows, channels, 0, 0) == (*TILE, 255), "a home screen rounds the corners itself"
    small = decode(sun_png(16))
    golden = sum(1 for y in range(16) for x in range(16) if pixel(small[2], 4, x, y)[0] > 180 and pixel(small[2], 4, x, y)[1] > 120)
    assert golden >= 50, "at 16 px the core and the rays still read as a sun (a fifth of the tile and more)"


def test_the_ico_holds_every_size_in_order():
    pngs = [sun_png(16), sun_png(32), sun_png(256, samples=1)]
    data = ico_bytes(pngs)
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind, count) == (0, 1, 3)
    widths = [data[6 + 16 * i] for i in range(3)]
    assert widths == [16, 32, 0], "256 is written as 0"
    first_offset = struct.unpack("<I", data[6 + 12:6 + 16])[0]
    assert data[first_offset:first_offset + 8] == b"\x89PNG\r\n\x1a\n"


def test_the_drawn_files_ship_and_every_page_wears_the_sun_in_its_tab():
    for name in ("icon-180.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "icon-256.png", "sun-32.png", "sun.svg", "kickoff.ico"):
        assert (ICONS / name).is_file(), name
    size, channels, rows = decode((ICONS / "icon-192.png").read_bytes())
    assert size == 192 and pixel(rows, channels, 96, 96)[:3] == SUN, "the neutral home-screen icon is the sun now"
    for page in ("index", "status", "welcome", "demo", "setup", "portal"):
        html = (ROOT / "static" / f"{page}.html").read_text(encoding="utf-8")
        assert 'href="/static/icons/sun.svg"' in html and 'href="/static/icons/sun-32.png"' in html, page
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon" sizes="180x180" href="/icons/icon-180.png"' in index, "the team's home-screen icon stays"


def test_the_program_the_tray_and_the_shortcuts_carry_it(tmp_path: Path):
    files = build.write_staging(tmp_path / "out")
    assert files["icon"].read_bytes() == (ICONS / "kickoff.ico").read_bytes(), "the program is built with the drawn .ico"
    tray = (ROOT / "tools" / "tray.ps1").read_text(encoding="utf-8")
    assert "ExtractAssociatedIcon($Program)" in tray and 'static\\icons\\kickoff.ico' in tray
    launcher = Launcher(ROOT, platform="win32", runner=lambda args: (0, ""))
    assert launcher.windows_icon() == str(ICONS / "kickoff.ico")
    script = launcher._lnk_script(tmp_path / "Kickoff Companion.lnk", False)
    assert f"$s.IconLocation = '{ICONS / 'kickoff.ico'},0'" in script
