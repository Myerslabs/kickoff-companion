"""Run with Claude: one run that refreshes what Claude Code wrote on the page on screen (batch 4 part 3, owner 2026-11-19).

The owner: "the clauder run button is hard to find unless it tells you. I want to make it easier. I also want to make it read
whats already there and add to it if not already. Each run should see what is in the current page and refresh it with
updated info, or additional info." The menu's opening level has the one row ("add it in the top layer of the menu"); a tap
sends the page's address here. The page maps to the pieces Claude wrote on it, each run through its own runner with what the
page holds now and the refresh rules (writing.refresh_text): out of date corrected or removed, the new added, never a part
emptied. Each page refreshes only inside its window (services/refresh_windows.py). Every run leaves a line per piece in
data/claude/refresh-log.jsonl with what changed ("leave a log somewhere, but dont show it").

Pure parts, testable without the app:

    Page(kind, game_id)                 the page a route names, or None for a page Claude wrote nothing on
    page_of(route) -> Page | None       "#program=123?tab=pre" -> Page("pre", 123); "#postgame=9" -> Page("post", 9); ...
    diff(before, after) -> dict         {added, removed, changed, paths: {added: [...], removed: [...], changed: [...]}}
    RefreshLog(data_dir).add(row)       one JSON line a piece; an unwritable log is logged, never raised
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("kickoff.refresh")

LOG_FILE = Path("claude") / "refresh-log.jsonl"
MAX_PATHS = 40  # paths kept per kind of change in one log line
MAX_LOG_BYTES = 2_000_000  # past this the log starts over beside its old copy (refresh-log.1.jsonl)

# the route ids that carry Claude's writing, and the page kind each one is (route ids from static/js/app.js's BUILT)
PAGES = {"program": "pre", "postgame": "post", "preseason": "preseason", "season": "season", "review": "book", "newspaper": "paper", "picks": "picks", "top25": "picks", "trivia": "trivia", "blame": "season"}
LABELS = {"pre": "The Pre-Game Program", "post": "The Post-Game Program", "preseason": "The Preseason Magazine", "season": "My Team", "book": "The season book", "paper": "The Newspaper", "picks": "The Picks of the week", "trivia": "The trivia"}


@dataclass(frozen=True)
class Page:
    kind: str
    game_id: int | None = None

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, "This page")


_ROUTE = re.compile(r"^#?([a-z0-9]+)(?:=([^?&#]*))?")


def page_of(route: Any) -> Page | None:
    """The page a route names. Another team's page (#season=Georgia), a past season's book (#review=2025) and every page
    Claude wrote nothing on are None."""
    if not isinstance(route, str):
        return None
    match = _ROUTE.match(route.strip())
    if not match:
        return None
    rid, arg = match.group(1), (match.group(2) or "").strip()
    if re.search(r"[?&]team=", route):
        return None  # batch 3: another team's page (a switched device, #season?team=Georgia): Claude wrote ours only
    kind = PAGES.get(rid)
    if kind == "pre" and re.search(r"[?&]tab=post\b", route):
        kind = "post"  # a played game's Post-Game reached through #program
    if kind is None:
        return None
    if kind in ("pre", "post"):
        if arg.isdigit() and int(arg) > 0:
            return Page(kind, int(arg))
        return Page(kind, None) if kind == "pre" and not arg else None  # the bare #program is the next game's
    if kind == "trivia":
        return Page(kind, None)  # the next game's
    if arg:  # #season=Georgia, #review=2025, #preseason=...: not our current season's page
        return None
    return Page(kind)


def _flatten(value: Any, prefix: str = "", out: dict[str, str] | None = None) -> dict[str, str]:
    out = {} if out is None else out
    if isinstance(value, dict):
        for key, inner in value.items():
            _flatten(inner, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            _flatten(inner, f"{prefix}[{i}]", out)
        if not value:
            out[prefix] = "[]"
    else:
        out[prefix] = json.dumps(value, ensure_ascii=False, default=str)
    return out


IGNORED = re.compile(r"(^|\.)(writtenAt|savedAt|checkedAt|updatedAt|model|author)$")


def diff(before: Any, after: Any) -> dict[str, Any]:
    """What a refresh changed, leaf by leaf (time stamps left out): counts and the first paths of each."""
    a = {k: v for k, v in _flatten(before).items() if not IGNORED.search(k)} if before is not None else {}
    b = {k: v for k, v in _flatten(after).items() if not IGNORED.search(k)} if after is not None else {}
    added = sorted(k for k in b if k not in a)
    removed = sorted(k for k in a if k not in b)
    changed = sorted(k for k in b if k in a and a[k] != b[k])
    return {"added": len(added), "removed": len(removed), "changed": len(changed), "paths": {"added": added[:MAX_PATHS], "removed": removed[:MAX_PATHS], "changed": changed[:MAX_PATHS]}}


class RefreshLog:
    """data/claude/refresh-log.jsonl: a line a piece a run. The app never shows it (owner 2026-11-19)."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / LOG_FILE

    def add(self, row: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > MAX_LOG_BYTES:
                self.path.replace(self.path.with_name("refresh-log.1.jsonl"))
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        except OSError:
            log.exception("The refresh log could not be written (%s)", self.path)

    def rows(self) -> list[dict[str, Any]]:
        """Every line it can read (for the tests and a look by hand); a damaged line is skipped."""
        out: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return out
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out
