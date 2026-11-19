"""Bring over another install's files (FEAT-13). The packaged program and the uvx install keep .env, data/ and logs/ in
%LOCALAPPDATA%\\Kickoff Companion. On a first start in a fresh clone (setup mode: no key or team yet) the welcome page
offers to copy that install's key and team (.env) and its data (settings, notes, the archive, the season loads, the facts, the trivia file)
into this project, once. Nothing is moved: the other install keeps its own files.

    find_public(environ) -> Path | None             the packaged install's folder when it holds a .env
    summary(source) -> {path, team, files, bytes, archive, notes} | None
    copy_into(source, env_path, data_dir) -> {copied, skipped, bytes, envKeys}

Left behind: the cache database (kickoff.db and its -wal and -shm, which this server already has open; the calls come
back from CFBD), the test league's pickles (data/demo), Claude Code's scratch folder, and DATA_DIR and LOG_DIR, which
name the other install's own places. A setting already in this .env stays as it is. Batch 3 (owner 2026-11-19): the app
follows one team, so the copied settings lose their extra primary teams, secondary teams and My teams ticker
(one_team_only)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.envfile import set_values
from app.services.prefs import RETIRED_TEAM_FIELDS, SETTINGS_FILE, one_team

log = logging.getLogger("kickoff.import")

PUBLIC_FOLDER = "Kickoff Companion"  # the packaged program's app-data folder (app/paths.py APP_FOLDER_TITLE)
SKIP_DIRS = frozenset({"demo", "ai-scratch"})
SKIP_FILE = re.compile(r"^kickoff\.db(-wal|-shm|-journal)?$", re.IGNORECASE)
SKIP_KEYS = frozenset({"DATA_DIR", "LOG_DIR"})
LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def find_public(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path | None:
    env = os.environ if environ is None else environ
    base = str(env.get("LOCALAPPDATA", "")).strip()
    folder = (Path(base) if base else (home or Path.home()) / "AppData" / "Local") / PUBLIC_FOLDER
    return folder if (folder / ".env").is_file() else None


def read_env(path: Path) -> dict[str, str]:
    """NAME -> value from a .env: comments and blank lines skipped, one level of quotes taken off."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("Could not read %s: %s", path, exc)
        return values
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            continue
        name, value = match.group(1).upper(), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if any(ch in value for ch in "\r\n\x00"):
            continue
        values[name] = value
    return values


def data_folder(source: Path, values: Mapping[str, str]) -> Path:
    named = str(values.get("DATA_DIR") or "").strip()
    if not named:
        return source / "data"
    path = Path(os.path.expandvars(named))
    return path if path.is_absolute() else source / path


def _files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    found = []
    for path in folder.rglob("*"):
        rel = path.relative_to(folder)
        if not path.is_file() or (rel.parts and rel.parts[0] in SKIP_DIRS) or SKIP_FILE.match(path.name):
            continue
        found.append(path)
    return found


def summary(source: Path | None) -> dict[str, Any] | None:
    """What a copy would bring, for the welcome page. Reads only."""
    if source is None or not (source / ".env").is_file():
        return None
    values = read_env(source / ".env")
    data = data_folder(source, values)
    files = _files(data)
    count = lambda sub, pattern: len(list((data / sub).glob(pattern))) if (data / sub).is_dir() else 0  # noqa: E731
    return {
        "path": str(source),
        "team": values.get("TEAM") or None,
        "hasKey": bool(values.get("CFBD_API_KEY")),
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files if p.exists()),
        "archive": count("archive", "*.json"),
        "notes": len([p for p in (data / "notes").glob("*.json") if not p.name.startswith("_")]) if (data / "notes").is_dir() else 0,
    }


def one_team_only(path: Path) -> bool:
    """Batch 3 (owner 2026-11-19: "Let's just have one team listed, and a change team for the switch"): the public
    install's settings may hold more primary teams, secondary teams and the My teams ticker; the copy drops them (the
    team lists emptied, the ticker every game) and keeps every other setting. True when the file was rewritten. A file
    that cannot be read or is not an object is left alone: the settings store reports it and applies the defaults."""
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        log.warning("Import: could not read %s to drop the old team picks: %s", path, exc)
        return False
    if not isinstance(raw, dict):
        return False
    cleared = one_team()
    if all(raw.get(key, cleared[key]) == cleared[key] for key in RETIRED_TEAM_FIELDS):
        return False
    raw.update(cleared)
    try:
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("Import: could not drop the old team picks from %s: %s", path, exc)
        return False
    log.info("Import: dropped the public install's extra teams and My teams ticker (one team since batch 3)")
    return True


def copy_into(source: Path, env_path: Path, data_dir: Path) -> dict[str, Any]:
    """Copy the other install's settings and data here. A setting this .env already has stays; data files are copied
    over this fresh install's (it has nothing yet but defaults). Returns what was done."""
    values = read_env(source / ".env")
    if not values:
        raise ValueError(f"{source / '.env'} holds no settings")
    mine = read_env(env_path) if env_path.is_file() else {}
    carried = {k: v for k, v in values.items() if k not in SKIP_KEYS and not str(mine.get(k) or "").strip()}
    data = data_folder(source, values)
    copied, skipped, size = 0, 0, 0
    for path in _files(data):
        target = data_dir / path.relative_to(data)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
            size += path.stat().st_size
        except OSError as exc:
            skipped += 1
            log.warning("Import: could not copy %s: %s", path, exc)
    one_team_only(data_dir / SETTINGS_FILE)
    if carried:
        set_values(env_path, carried)  # last: a copy that stops half way leaves setup mode on, so it can run again
    log.warning("Brought over the install in %s: %d settings, %d files (%d skipped), %.1f MB", source, len(carried), copied, skipped, size / 1e6)
    return {"copied": copied, "skipped": skipped, "bytes": size, "envKeys": sorted(carried)}
