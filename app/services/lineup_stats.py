"""Season stat chips for the starting lineups (owner request 2026-10-02: "the players' stats, like the
impact cards, in the depth chart"). The notes file names the starters as the published chart printed
them; CFBD's season lines carry the ids and the numbers. Names are matched after normalising (case,
punctuation, Jr. and III), then by first initial and last name when that is unique on the team. A
matched player gets `playerId` (so the row opens his card) and `chips` in the impact cards' shape:
the lead stat in words ("917 passing yards"), then up to three more in CFBD's keys ("7 TD"), which
the front end relabels. Nothing matched means no chips, never an error."""

from __future__ import annotations

import re
from typing import Any

from app.services.players import Line

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# (category, lead stat, lead label, format, detail keys in order). Offense picks by what the player
# did most; defense leads with tackles and adds sacks, TFL, interceptions and passes defended.
PASSING = ("passing", "YDS", "passing yards", "0f", ["TD", "INT", "PCT", "YPA"])
RUSHING = ("rushing", "YDS", "rushing yards", "0f", ["CAR", "TD", "YPC", "LONG"])
RECEIVING = ("receiving", "YDS", "receiving yards", "0f", ["REC", "TD", "YPR", "LONG"])
DEFENSE = ("defensive", "TOT", "tackles", "0f", ["SACKS", "TFL", "PD", "QB HUR"])
KICKING = ("kicking", "FGM", "field goals", "0f", ["FGA", "PCT", "LONG", "XPM"])
PUNTING = ("punting", "YPP", "yards a punt", "1f", ["NO", "LONG", "IN 20", "TB"])


def name_key(name: Any) -> str:
    """'TJ Shanahan Jr.' -> 'tj shanahan'; "Ke'Shaun Tillery" -> 'xaishaun edwards'."""
    if not isinstance(name, str):
        return ""
    words = re.sub(r"[^a-z0-9 ]", "", name.lower().replace("-", " ")).split()
    while words and words[-1] in SUFFIXES:
        words.pop()
    return " ".join(words)


def short_key(name: Any) -> str:
    """'t shanahan': the first initial and the last word, for a chart that prints a nickname or an initial."""
    key = name_key(name)
    if not key:
        return ""
    words = key.split()
    return f"{words[0][0]} {words[-1]}" if len(words) > 1 else key


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _fmt(value: float, fmt: str) -> str:
    if fmt == "1f":
        return f"{value:.1f}"
    return f"{value:.0f}" if value.is_integer() else f"{value:.1f}"


def _detail(key: str, value: float) -> str:
    if key == "PCT":
        pct = value * 100 if value <= 1 else value
        return f"{pct:.0f}% completions"
    return f"{_fmt(value, '1f' if not value.is_integer() else '0f')} {key}"


def chips_for(by_category: dict[str, Line]) -> list[str]:
    """The impact-card chips for one player's season lines, or [] when he has no numbers."""
    passing = _num((by_category.get("passing") or Line("", None, None, None, None, "passing", {})).stats.get("ATT"))
    rushing = _num((by_category.get("rushing") or Line("", None, None, None, None, "rushing", {})).stats.get("YDS"))
    receiving = _num((by_category.get("receiving") or Line("", None, None, None, None, "receiving", {})).stats.get("YDS"))
    tackles = _num((by_category.get("defensive") or Line("", None, None, None, None, "defensive", {})).stats.get("TOT"))
    if passing is not None and passing >= 10:
        spec = PASSING
    elif rushing is not None or receiving is not None:
        spec = RUSHING if (rushing or 0) >= (receiving or 0) else RECEIVING
    elif tackles is not None:
        spec = DEFENSE
    elif "kicking" in by_category and _num(by_category["kicking"].stats.get("FGA")):
        spec = KICKING
    elif "punting" in by_category and _num(by_category["punting"].stats.get("NO")):
        spec = PUNTING
    else:
        return []
    category, lead, label, fmt, details = spec
    line = by_category.get(category)
    value = _num(line.stats.get(lead)) if line else None
    if line is None or value is None:
        return []
    chips = [f"{_fmt(value, fmt)} {label}"]
    for key in details:
        v = _num(line.stats.get(key))
        if v is None or v == 0:
            continue
        chips.append(_detail(key, v))
        if len(chips) >= 4:
            break
    if spec is DEFENSE and len(chips) < 4:
        ints = by_category.get("interceptions")
        v = _num(ints.stats.get("INT")) if ints else None
        if v:
            chips.append(f"{_fmt(v, '0f')} INT")
    return chips


def index_lines(lines: dict[tuple[str, str], Line]) -> tuple[dict[str, dict[str, Line]], dict[str, str], dict[str, str | None]]:
    """(player id -> category -> line, name key -> player id (full and, when unique, short), player id -> name)."""
    by_player: dict[str, dict[str, Line]] = {}
    names: dict[str, str | None] = {}
    for (player_id, category), line in lines.items():
        by_player.setdefault(player_id, {})[category] = line
        names.setdefault(player_id, line.player)
    full: dict[str, str] = {}
    short: dict[str, set[str]] = {}
    for player_id, name in names.items():
        key = name_key(name)
        if key and key not in full:
            full[key] = player_id
        sk = short_key(name)
        if sk:
            short.setdefault(sk, set()).add(player_id)
    keys = dict(full)
    for sk, ids in short.items():
        if len(ids) == 1 and sk not in keys:
            keys[sk] = next(iter(ids))
    return by_player, keys, names


def attach_lineup_stats(lineups: dict[str, Any] | None, us_lines: dict[tuple[str, str], Line], opp_lines: dict[tuple[str, str], Line]) -> dict[str, Any] | None:
    """Add playerId and chips to every matched name in a dumped lineups block; returns the same object."""
    if not isinstance(lineups, dict):
        return lineups
    for side, lines in (("us", us_lines), ("them", opp_lines)):
        team = lineups.get(side)
        if not isinstance(team, dict) or not isinstance(team.get("slots"), list):
            continue
        by_player, keys, _names = index_lines(lines or {})
        for slot in team["slots"]:
            if not isinstance(slot, dict) or not isinstance(slot.get("players"), list):
                continue
            for player in slot["players"]:
                if not isinstance(player, dict):
                    continue
                player_id = keys.get(name_key(player.get("name"))) or keys.get(short_key(player.get("name")))
                player["playerId"] = player_id
                player["chips"] = chips_for(by_player.get(player_id, {})) if player_id else []
    return lineups
