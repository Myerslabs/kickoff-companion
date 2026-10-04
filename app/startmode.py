"""Which app a start runs: the demo (the made-up league) or this install's own team (public release Phase 9b).

A fresh install has no CFBD key yet, so it starts in the demo: everything works on made-up data, and the demo's
welcome page (/demo) explains what a key does before anyone needs one. "Use my own team" there switches to the
real app, which asks for the key and the team (/welcome). After setup the app starts on the real team; the menu's
Demo item switches back to the demo for showing a friend, and "Back to my team" returns.

The choice is one small file, data/startup.json ({"mode": "demo"} or {"mode": "app"}). With no file (or a broken
one) the demo runs while setup is needed and the app runs once it is done."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("kickoff.startmode")

MODE_FILE = "startup.json"
DEMO = "demo"
APP = "app"


def mode_path(data_dir: Path) -> Path:
    return Path(data_dir) / MODE_FILE


def saved_mode(data_dir: Path) -> str | None:
    """The mode the file asks for, or None when there is no usable file."""
    path = mode_path(data_dir)
    if not path.is_file():
        return None
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("%s could not be read (%s); the default start applies", path.name, exc)
        return None
    mode = raw.get("mode") if isinstance(raw, dict) else None
    return mode if mode in (DEMO, APP) else None


def start_mode(settings: Any) -> str:
    """demo or app for this start: the saved choice, else the demo while setup is needed."""
    saved = saved_mode(settings.data_dir)
    if saved is not None:
        return saved
    return DEMO if settings.setup_needed else APP


def save_mode(data_dir: Path, mode: str) -> None:
    if mode not in (DEMO, APP):
        raise ValueError(f"unknown start mode {mode!r}")
    path = mode_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".startup-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"mode": mode}, handle)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    log.info("Next start: %s", "the demo" if mode == DEMO else "this install's own team")
