"""The big screen (Phase 18.6, owner 2026-10-08: "a monitor plugged into the PC", the game-day board opened full screen by
Edge in kiosk mode on a chosen monitor).

    list_screens() -> [{"index", "name", "x", "y", "width", "height", "primary"}]   Windows; [] elsewhere
    find_browser() -> path | None                                                     Edge first, then Chrome
    BoardLauncher(data_dir).open(url, screen) / .close() / .running
    kiosk_command(browser, url, screen, profile) -> list[str]                          pure, tested

The browser starts with its own profile folder (data/kiosk-profile) so it opens as a separate window at the chosen
monitor's corner instead of joining the owner's open browser. The server computer only; the route checks that.
Leaving kiosk mode is Alt+F4 at the keyboard, or the Close button in Settings.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("kickoff.screens")

BROWSER_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)
BROWSER_NAMES = ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")


def find_browser() -> str | None:
    for path in BROWSER_PATHS:
        if os.path.exists(path):
            return path
    return next((found for found in (shutil.which(name) for name in BROWSER_NAMES) if found), None)


def list_screens() -> list[dict[str, Any]]:
    """Every monitor Windows knows, in the order it lists them. Empty where this cannot ask (macOS, Linux)."""
    if not sys.platform.startswith("win"):
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        found: list[dict[str, Any]] = []

        def callback(handle: int, _dc: int, _rect: Any, _data: int) -> bool:
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(MonitorInfo)
            if ctypes.windll.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                r = info.rcMonitor
                found.append({"x": r.left, "y": r.top, "width": r.right - r.left, "height": r.bottom - r.top, "primary": bool(info.dwFlags & 1)})
            return True

        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)(callback)
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, proc, 0)
    except (OSError, AttributeError, ValueError) as exc:
        log.warning("The monitors could not be listed: %s", exc)
        return []
    return [{"index": i, "name": f"Screen {i + 1}{' (main)' if s['primary'] else ''}, {s['width']} x {s['height']}", **s} for i, s in enumerate(found)]


def kiosk_command(browser: str, url: str, screen: dict[str, Any] | None, profile: Path) -> list[str]:
    command = [browser, "--kiosk", url, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble", "--autoplay-policy=no-user-gesture-required"]
    if Path(browser).name.lower().startswith("msedge") or "edge" in browser.lower():
        command.append("--edge-kiosk-type=fullscreen")
    if screen is not None:
        command.append(f"--window-position={int(screen['x'])},{int(screen['y'])}")
        command.append(f"--window-size={int(screen['width'])},{int(screen['height'])}")
    return command


class BoardLauncher:
    def __init__(self, data_dir: Path) -> None:
        self.profile = Path(data_dir) / "kiosk-profile"
        self.process: subprocess.Popen[Any] | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def open(self, url: str, screen_index: int | None) -> dict[str, Any]:
        browser = find_browser()
        if browser is None:
            return {"error": "No Edge or Chrome was found on this computer."}
        screens = list_screens()
        screen = next((s for s in screens if s["index"] == screen_index), None) if screen_index is not None else None
        if screen_index is not None and screen is None and screens:
            return {"error": "That screen is not connected any more. Pick one again."}
        self.close()
        try:
            self.profile.mkdir(parents=True, exist_ok=True)
            self.process = subprocess.Popen(kiosk_command(browser, url, screen, self.profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603 - the browser found above, arguments built here
        except OSError as exc:
            self.process = None
            return {"error": f"The board could not be opened: {exc.strerror or exc}."}
        log.info("Game-day board opened on %s", screen["name"] if screen else "the default screen")
        return {"opened": True, "screen": screen["name"] if screen else None}

    def close(self) -> bool:
        proc, self.process = self.process, None
        if proc is None or proc.poll() is not None:
            return False
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        return True
