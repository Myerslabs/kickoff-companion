"""Connecting a phone or tablet (public release Phase 4b): the addresses that reach the server and a QR
code for them, so a device joins by scanning instead of typing. The QR code is drawn here with segno
(pure Python, no network): as SVG for the connect page and the status page, and as block characters
for the server window at start.

Only the server's own addresses are ever encoded (the connect route refuses anything else), so the
code on a page always points at this server."""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

import segno

from app.config import Settings
from app.netinfo import http_url, other_urls, tablet_url

log = logging.getLogger("kickoff.connect")

QUIET_ZONE = 2  # modules of margin around the code; scanners need some
FULL, UPPER, LOWER, EMPTY = "█", "▀", "▄", " "


def addresses(settings: Settings, ip: str | None) -> list[str]:
    """Every address a device can use, best first, each ending in "/"."""
    first = tablet_url(settings, ip)
    return [f"{url}/" for url in dict.fromkeys([first, *other_urls(settings, ip)])]


def local_address(settings: Settings) -> str:
    """The address the host's own browser opens: localhost always works on the host itself."""
    return f"{http_url('localhost', settings.port, secure=settings.https)}/"


def qr(url: str) -> Any:
    return segno.make(url, error="m")


def qr_svg(url: str, *, scale: int = 6) -> str:
    """The code as an SVG document, dark squares on white whatever the page theme."""
    code = qr(url)
    svg = code.svg_inline(scale=scale, border=QUIET_ZONE, dark="#000000", light="#ffffff")
    return svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" role="img" ', 1)


def qr_text(url: str) -> str:
    """The code in block characters, two rows of squares per line. Light squares are drawn, dark ones
    are left as the window's background, so it scans in the usual dark console."""
    matrix = [list(row) for row in qr(url).matrix]
    size = len(matrix)
    light = [[True] * (size + 2 * QUIET_ZONE) for _ in range(QUIET_ZONE)]
    rows = light + [[True] * QUIET_ZONE + [not bool(cell) for cell in row] + [True] * QUIET_ZONE for row in matrix] + light
    if len(rows) % 2:
        rows.append([True] * len(rows[0]))
    lines = []
    for top, bottom in zip(rows[0::2], rows[1::2], strict=True):
        lines.append("".join(FULL if t and b else UPPER if t else LOWER if b else EMPTY for t, b in zip(top, bottom, strict=True)))
    return "\n".join(lines)


def print_qr(url: str, out: TextIO | None = None) -> bool:
    """Print the code under a heading when the window can show it. True when printed."""
    stream = out or sys.stdout
    try:
        if out is None and not stream.isatty():
            return False  # a log file or a hidden window: nobody would scan it
        stream.write(f"\nScan with a phone or tablet to open {url}\n{qr_text(url)}\n\n")
        stream.flush()
        return True
    except (UnicodeEncodeError, OSError, ValueError) as exc:
        log.info("The QR code could not be shown in this window (%s); the status page has it.", exc)
        return False
