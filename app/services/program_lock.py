"""The Pre-Game Program locked at kickoff (the Prompts phase, wave B, owner 2026-10-13: "I want the pre-game program to be
kind of locked in, so we can see expectations vs result ... like a pretest, post test").

At kickoff the housekeeping loop (app/maintenance.py) takes what the program said and writes it once to
data/season/<year>/program/<game_id>.json: the line, the pregame win probability, both teams' season profile rows, the
leaders side by side, the edges and the notes' author. It is never written again. After the final the program page
reads it back beside the game's own numbers (GET /api/program/<id>/locked; static/js/ui/results.js).

    ProgramLock(data_dir, season)
      path(game_id), has(game_id), load(game_id) -> dict | None
      save(game_id, snapshot) -> bool      False when one is there already (the first lock wins)
    snapshot(data, now) -> dict            the slice of the program's data worth keeping
    lock_due(kickoff, completed, now)      kickoff has passed by no more than LOCK_WINDOW and the game is not final
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.lock")

FORMAT = 1
LOCK_WINDOW = timedelta(hours=6)  # a server down at kickoff still locks on its next start; a day later is the result, not the expectation
PROFILE_KEYS = ("ppg", "ypg", "ypp", "pass_ypg", "rush_ypg", "third", "to_lost_pg", "opp_ppg", "ypg_d", "ypp_d")  # what the results band pairs with the box


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def lock_due(kickoff: Any, completed: Any, now: datetime) -> bool:
    kick = parse_iso(kickoff) if not isinstance(kickoff, datetime) else kickoff
    if kick is None or completed:
        return False
    return kick <= now <= kick + LOCK_WINDOW


def _team(block: Any) -> dict[str, Any]:
    b = block if isinstance(block, dict) else {}
    return {k: b.get(k) for k in ("school", "abbreviation", "mascot", "apRank", "record", "conference") if k in b}


def _rows(rows: Any) -> list[dict[str, Any]]:
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("key"), str):
            out.append({k: row.get(k) for k in ("side", "label", "key", "value", "format", "higherIsBetter", "nationalRank", "nationalOf")})
    return out


def snapshot(data: Any, now: datetime) -> dict[str, Any]:
    """What the results band needs later, and nothing that changes with the game (the box, the live score)."""
    d = data if isinstance(data, dict) else {}
    game = d.get("game") if isinstance(d.get("game"), dict) else {}
    profile = d.get("profile") if isinstance(d.get("profile"), dict) else {}
    notes = d.get("notes") if isinstance(d.get("notes"), dict) else {}
    leaders = [row for row in (d.get("leaders") if isinstance(d.get("leaders"), list) else []) if isinstance(row, dict)]
    edges = [row for row in (d.get("edges") if isinstance(d.get("edges"), list) else []) if isinstance(row, dict)][:6]
    return {
        "format": FORMAT,
        "lockedAt": _iso(now),
        "gameId": game.get("gameId"),
        "kickoff": game.get("kickoff"),
        "homeIsUs": game.get("homeIsUs"),
        "us": _team(d.get("us")),
        "them": _team(d.get("them")),
        "line": d.get("line") if isinstance(d.get("line"), dict) else None,
        "pregame": d.get("pregame") if isinstance(d.get("pregame"), dict) else None,
        "profile": {"us": _rows(profile.get("us")), "them": _rows(profile.get("them"))},
        "leaders": leaders,
        "edges": edges,
        "notes": {"present": bool(notes.get("present")), "author": notes.get("author")},
    }


class ProgramLock:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(season) / "program"

    def path(self, game_id: int | str) -> Path:
        return self.dir / f"{int(game_id)}.json"

    def has(self, game_id: Any) -> bool:
        try:
            return self.path(game_id).is_file()
        except (TypeError, ValueError):
            return False

    def load(self, game_id: Any) -> dict[str, Any] | None:
        try:
            path = self.path(game_id)
        except (TypeError, ValueError):
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            return None
        except ValueError:
            log.warning("The locked program %s could not be read; treated as not locked.", path)
            return None
        return raw if isinstance(raw, dict) and raw.get("gameId") is not None else None

    def save(self, game_id: Any, snap: dict[str, Any]) -> bool:
        if self.has(game_id):
            return False
        atomic_write(self.path(game_id), json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
        log.info("The Pre-Game Program for game %s is locked at kickoff.", game_id)
        return True
