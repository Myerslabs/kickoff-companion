"""The notes laid out (Wave 5; owner 2026-11-15, the board "Build as
drawn"): on top of the Program notes band, three keys to the game, a strip of three or four of the program's own numbers and
the one matchup to watch. The sections under them stay as 1.38.0 draws them.

Claude writes the keys and the matchup in words and only names the figures: the program's metric keys with the team,
`{"team": "them", "metric": "profile:third"}`. The value, the national rank and the conference rank come from the program
here, so a figure can never be invented (the board's mark 2). Each piece is checked on its own, and a piece that fails is
left out alone, never the whole band (mark 3); the reasons go into `dropped` and, once per distinct set, to the log.

    resolve(layout, profile, advanced, schools)   the band's layout {keys, numbers, watch, dropped}, or None
    figures(profile, advanced, schools)           the figures a notes prompt offers, both teams side by side
    figures_text(rows, team, opponent)            those as the prompt's lines
    program_figures(service, game_id)             the figures for one game from the program service, or None
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("kickoff.notes")

KEYS = 3  # exactly three keys to the game
NUMBERS = (3, 4)  # at least three figures in the strip, at most four
LINE_WORDS = 8  # a key's bold line
KEY_WORDS = 35  # a key's sentence
WATCH_LINE_WORDS = 12
WATCH_WORDS = 40
TEAMS = ("us", "them")
MAX_TEXT = 400  # characters: a longer string is not a sentence
METRIC = re.compile(r"^[a-z]+:[a-z0-9_]{1,60}$")

_logged: set[str] = set()


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text if text and len(text) <= MAX_TEXT else None


def _words(text: str | None) -> int:
    return len(text.split()) if text else 0


def _is_num(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value == value  # NaN is not a number here


def _rows(block: Any, team: str) -> list[dict[str, Any]]:
    """One team's figures from the program's profile or advanced block: dict rows with a metric key and a number."""
    rows = block.get(team) if isinstance(block, dict) else None
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("metric"), str) and METRIC.match(row["metric"]) and _is_num(row.get("value")):
            out.append(row)
    return out


def _index(profile: Any, advanced: Any) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for team in TEAMS:
        index[team] = {}
        for row in [*_rows(profile, team), *_rows(advanced, team)]:
            index[team].setdefault(row["metric"], row)
    return index


def _rank(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _note(dropped: list[str]) -> None:
    key = "|".join(dropped)
    if dropped and key not in _logged:
        _logged.add(key)
        log.warning("The notes layout left out: %s", "; ".join(dropped))


def resolve(layout: Any, profile: Any, advanced: Any, schools: dict[str, Any] | None = None, conference: Any = None) -> dict[str, Any] | None:
    """The band's layout from what Claude wrote and the program's numbers. Each piece stands alone: fewer than three
    usable keys leaves the keys out, fewer than three known figures leaves the strip out, a matchup that breaks its
    lengths leaves it out. None when nothing is left (the band is then as 1.38.0 drew it). `conference` names the
    conference the profile's conference ranks are within (the program's own)."""
    raw = layout.model_dump() if hasattr(layout, "model_dump") else layout
    if not isinstance(raw, dict):
        return None
    schools = schools if isinstance(schools, dict) else {}
    dropped: list[str] = []

    keys: list[dict[str, Any]] = []
    raw_keys = raw.get("keys") if isinstance(raw.get("keys"), list) else []
    for n, key in enumerate(raw_keys, start=1):
        line = _clean(key.get("line")) if isinstance(key, dict) else None
        text = _clean(key.get("text")) if isinstance(key, dict) else None
        if not line:
            dropped.append(f"key {n} has no line")
        elif _words(line) > LINE_WORDS:
            dropped.append(f"key {n}'s line is longer than {LINE_WORDS} words")
        elif _words(text) > KEY_WORDS:
            dropped.append(f"key {n}'s sentence is longer than {KEY_WORDS} words")
        else:
            keys.append({"line": line, "text": text})
    if len(keys) < KEYS:
        if raw_keys:
            dropped.append(f"the keys: {len(keys)} usable of the {KEYS} needed")
        keys = []
    keys = keys[:KEYS]

    index = _index(profile, advanced)
    numbers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    raw_numbers = raw.get("numbers") if isinstance(raw.get("numbers"), list) else []
    for entry in raw_numbers:
        team = entry.get("team") if isinstance(entry, dict) else None
        metric = entry.get("metric") if isinstance(entry, dict) else None
        if team not in TEAMS or not isinstance(metric, str):
            dropped.append(f"a figure without a team (us or them) and a metric name: {str(entry)[:80]}")
            continue
        row = index[team].get(metric.strip())
        if row is None:
            dropped.append(f"{metric[:60]} is not in the program's numbers for {team}")
            continue
        if (team, row["metric"]) in seen:
            continue
        seen.add((team, row["metric"]))
        numbers.append({
            "team": team,
            "school": schools.get(team) if isinstance(schools.get(team), str) else None,
            "metric": row["metric"],
            "label": row.get("label") if isinstance(row.get("label"), str) else row["metric"],
            "side": row.get("side") if isinstance(row.get("side"), str) else None,
            "value": row["value"],
            "format": row.get("format") if isinstance(row.get("format"), str) else None,
            "higherIsBetter": row.get("higherIsBetter") if isinstance(row.get("higherIsBetter"), bool) else None,
            "rank": _rank(row, "nationalRank"),
            "of": _rank(row, "nationalOf"),
            "conferenceRank": _rank(row, "conferenceRank"),
            "conferenceOf": _rank(row, "conferenceOf"),
        })
    if len(numbers) < NUMBERS[0]:
        if raw_numbers:
            dropped.append(f"the numbers: {len(numbers)} known of the {NUMBERS[0]} needed")
        numbers = []
    numbers = numbers[: NUMBERS[1]]

    watch = None
    raw_watch = raw.get("watch")
    if isinstance(raw_watch, dict):
        line, text = _clean(raw_watch.get("line")), _clean(raw_watch.get("text"))
        if not line:
            dropped.append("the matchup to watch has no line")
        elif _words(line) > WATCH_LINE_WORDS or _words(text) > WATCH_WORDS:
            dropped.append(f"the matchup to watch is longer than {WATCH_LINE_WORDS} and {WATCH_WORDS} words")
        else:
            watch = {"line": line, "text": text}

    _note(dropped)
    if not keys and not numbers and watch is None:
        return None
    return {"keys": keys, "numbers": numbers, "watch": watch, "conference": conference if isinstance(conference, str) and conference else None, "dropped": dropped}


def _fmt(value: Any, fmt: Any) -> str:
    """A figure as the prompt shows it; the band formats its own."""
    if not _is_num(value):
        return "–"
    if fmt == "pct":
        return f"{value * 100:.1f}%"
    match = re.fullmatch(r"(\+?)(\d)f", fmt) if isinstance(fmt, str) else None
    if match:
        return f"{value:{'+' if match.group(1) else ''}.{match.group(2)}f}"
    return f"{value:g}"


def figures(profile: Any, advanced: Any, schools: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every figure the program has for this game, both teams side by side: [{metric, label, side, us, them}], each team's
    {value, text, rank, of} or None. The order is the program's: the profile, then the advanced numbers."""
    index = _index(profile, advanced)
    order: list[str] = []
    for team in TEAMS:
        for metric in index[team]:
            if metric not in order:
                order.append(metric)
    out = []
    for metric in order:
        first = index["us"].get(metric) or index["them"].get(metric) or {}
        sides: dict[str, Any] = {}
        for team in TEAMS:
            row = index[team].get(metric)
            sides[team] = {"value": row["value"], "text": _fmt(row["value"], row.get("format")), "rank": _rank(row, "nationalRank"), "of": _rank(row, "nationalOf")} if row else None
        out.append({"metric": metric, "label": first.get("label") if isinstance(first.get("label"), str) else metric, "side": first.get("side") if isinstance(first.get("side"), str) else None, **sides})
    return out


def figures_text(rows: Any, team: str, opponent: str) -> str:
    """The figures as the prompt's lines: the name to write, what it is, then each team's value and national rank."""
    lines = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("metric"), str):
            continue

        def side(name: str, cell: Any) -> str:
            if not isinstance(cell, dict):
                return f"{name} –"
            rank = f", #{cell['rank']} of {cell['of']}" if cell.get("rank") and cell.get("of") else ""
            return f"{name} {cell.get('text', '–')}{rank}"

        unit = row.get("side") if row.get("side") in ("offense", "defense") else None
        what = f"{row.get('label')} ({unit})" if unit else str(row.get("label"))
        lines.append(f"{row['metric']} | {what} | {side(team, row.get('us'))} | {side(opponent, row.get('them'))}")
    return "\n".join(lines)


async def program_figures(service: Any, game_id: Any) -> list[dict[str, Any]] | None:
    """The figures for one of our games from the program service (its cached answer; the quota guard as ever), or None
    when the program cannot be had: the notes prompt then asks for no numbers."""
    if service is None or not isinstance(game_id, int):
        return None
    try:
        result = await service.program(game_id)
    except Exception:  # noqa: BLE001 - the notes run goes on without the numbers; logged
        log.exception("The program's figures for the notes prompt could not be read (game %s)", game_id)
        return None
    data = getattr(result, "data", None)
    if not isinstance(data, dict) or not isinstance(data.get("game"), dict):
        return None
    schools = {team: (data.get(team) or {}).get("school") if isinstance(data.get(team), dict) else None for team in TEAMS}
    rows = figures(data.get("profile"), data.get("advanced"), schools)
    return rows or None
