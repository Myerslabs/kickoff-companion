"""Player lines worked out from the live play-by-play (Phase 11). CFBD's box-score endpoints stay
empty while a game is on (seen on the Texas at Tennessee recording, 2026-09-26), so the Live
sheet's leaders and box score read these until the box score posts for that team.

Only what the play text states reliably is counted: passing (completions, attempts, yards,
touchdowns, interceptions), rushing (carries, yards, touchdowns, long) and receiving (catches,
yards, touchdowns, long). Tackles are left out because the text names tacklers loosely. Sacks
count as rushes for the quarterback, the NCAA rule the box score follows. A play the officials
wiped out ("NO PLAY"), a two-point try, and a play with no named player are skipped. Names are the
feed's short form ("A.Manley"). With the teams' rosters, a jersey number whose roster entry has
the same last name and first initial gives the row CFBD's player id and full name, so it shows a
headshot and opens the player card; two players can share a number, so anything less than one
clean match leaves the short name and no id.

The text shapes were read off the recording (the regexes below match its wording; the names here are made up):
  "#16 A.Manley pass complete short right to #1 R.Wingate caught at SILO33, for 8 yards ..."
  "#11 F.Brandt pass incomplete short right to #4 M.Matheson thrown to SILO01"
  "#16 A.Manley pass intercepted by #14 K.Leeds at MAG04"
  "#0 R.Brownlee rush middle for 9 yards gain to the MAG00 TOUCHDOWN"
  "#16 A.Manley sacked for loss of 8 yards to the SILO18"
"""

from __future__ import annotations

import re
from typing import Any

NAME = r"#(\d+)\s+([^#();,]+?)"
PASSER = re.compile(NAME + r"\s+pass\s+(complete|incomplete|intercepted)\b", re.IGNORECASE)
RECEIVER = re.compile(r"pass\s+complete[^#]*?\bto\s+" + NAME + r"\s+(?:caught\b|for\b)", re.IGNORECASE)
RUSHER = re.compile(NAME + r"\s+rush\b", re.IGNORECASE)
SACKED = re.compile(NAME + r"\s+sacked\b", re.IGNORECASE)
MAX_NAME = 40
SKIP_TYPES = ("two point", "2pt", "extra point", "kickoff", "punt", "field goal", "timeout", "end ")
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# {team: {jersey: [{"id": "5132812", "first": "Mason", "last": "Hamilton"}]}}
Rosters = dict[str, dict[int, list[dict[str, str]]]]


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _name(match: re.Match[str] | None) -> tuple[str, int] | None:
    """(short name, jersey) from a match, or None."""
    if match is None:
        return None
    name = match.group(2).strip()
    return (name, int(match.group(1))) if 0 < len(name) <= MAX_NAME else None


def _words(value: str) -> list[str]:
    return [w for w in re.split(r"[\s.'\-]+", value.lower()) if w and w not in SUFFIXES]


def resolve(rosters: Rosters | None, team: str, short: str, jersey: int) -> tuple[str | None, str]:
    """(player id, display name) for a short name: the one roster entry with this jersey whose last
    name and first initial agree, else (None, the short name)."""
    entries = ((rosters or {}).get(team) or {}).get(jersey) or []
    if "." in short:
        initial, last = short.split(".", 1)
    else:
        initial, last = "", short
    last_words = _words(last)
    matches = [
        e for e in entries
        if last_words and _words(e.get("last") or "")[:1] == last_words[:1] and (not initial or (e.get("first") or "").lower().startswith(initial.strip().lower()))
    ]
    if len(matches) != 1:
        return None, short
    entry = matches[0]
    full = " ".join(part for part in (entry.get("first"), entry.get("last")) if part)
    return entry.get("id") or None, full or short


def _touchdown(play_type: str) -> bool:
    kind = play_type.lower()
    return "touchdown" in kind and "return" not in kind  # a return touchdown belongs to the other side


class _Lines:
    def __init__(self, rosters: Rosters | None) -> None:
        self.rosters = rosters
        self.teams: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    def row(self, team: str, category: str, who: tuple[str, int]) -> dict[str, Any]:
        player_id, name = resolve(self.rosters, team, *who)
        rows = self.teams.setdefault(team, {}).setdefault(category, {})
        return rows.setdefault(player_id or name, {"id": player_id, "name": name, "n": 0, "made": 0, "yds": 0, "td": 0, "int": 0, "long": None})

    def out(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        result: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for team, categories in self.teams.items():
            result[team] = {}
            for category, rows in categories.items():
                lines = [_stats(category, r) for r in rows.values()]
                lines.sort(key=lambda r: -(r["stats"].get("YDS") or 0))
                result[team][category] = lines
        return result


def _stats(category: str, r: dict[str, Any]) -> dict[str, Any]:
    if category == "passing":
        stats: dict[str, Any] = {"C/ATT": f"{r['made']}/{r['n']}", "YDS": r["yds"], "TD": r["td"], "INT": r["int"]}
    elif category == "rushing":
        stats = {"CAR": r["n"], "YDS": r["yds"], "AVG": round(r["yds"] / r["n"], 1) if r["n"] else None, "TD": r["td"], "LONG": r["long"]}
    else:
        stats = {"REC": r["n"], "YDS": r["yds"], "AVG": round(r["yds"] / r["n"], 1) if r["n"] else None, "TD": r["td"], "LONG": r["long"]}
    return {"playerId": r["id"], "name": r["name"], "stats": stats}


def _long(row: dict[str, Any], gained: int) -> None:
    row["long"] = gained if row["long"] is None else max(row["long"], gained)


def play_player_lines(plays: list[dict[str, Any]], rosters: Rosters | None = None) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """{team: {"passing" | "rushing" | "receiving": [{playerId, name, stats}]}}, rows by yards.
    `plays` are the live play dicts (offense, playType, text, yardsGained); anything malformed is
    skipped. `rosters` (see resolve) turns short names into roster players when they match."""
    lines = _Lines(rosters)
    for play in plays:
        if not isinstance(play, dict):
            continue
        team = play.get("offense")
        text = play.get("text")
        if not isinstance(team, str) or not team or not isinstance(text, str) or not text:
            continue
        play_type = play.get("playType") if isinstance(play.get("playType"), str) else ""
        if "NO PLAY" in text.upper() or any(word in play_type.lower() for word in SKIP_TYPES):
            continue
        gained = _int(play.get("yardsGained"))
        touchdown = _touchdown(play_type)
        passer = PASSER.search(text)
        if passer is not None:
            name = _name(passer)
            outcome = passer.group(3).lower()
            if name:
                row = lines.row(team, "passing", name)
                row["n"] += 1
                if outcome == "complete":
                    row["made"] += 1
                    row["yds"] += gained or 0
                    row["td"] += 1 if touchdown else 0
                elif outcome == "intercepted":
                    row["int"] += 1
            receiver = _name(RECEIVER.search(text)) if outcome == "complete" else None
            if receiver:
                row = lines.row(team, "receiving", receiver)
                row["n"] += 1
                row["yds"] += gained or 0
                row["td"] += 1 if touchdown else 0
                if gained is not None:
                    _long(row, gained)
            continue
        rusher = _name(RUSHER.search(text)) or _name(SACKED.search(text))
        if rusher:
            row = lines.row(team, "rushing", rusher)
            row["n"] += 1
            row["yds"] += gained or 0
            row["td"] += 1 if touchdown else 0
            if gained is not None:
                _long(row, gained)
    return lines.out()
