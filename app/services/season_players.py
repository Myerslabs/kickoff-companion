"""Every player's stats for the season in review (the season line's Wave 7; owner 2026-11-15, Board 5
"Build as drawn, but make sure there are more players stats, at least every
starter"). From the team's season lines CFBD keeps (/stats/player/season for our team, the part Leaders already reads, so no
call of its own): every player with a stat line in each category, best first, and every starter of the latest depth chart the
game notes hold, the linemen too, each with his season line where he has one. Pure functions; the service and the route
gather the parts.

  TABLES                                  the categories in the page's order: (category, title, columns, sort stat)
  season_tables(lines)                    [{category, title, columns [{key, label}], rows [{playerId, name, position, stats}]}]
  starters_from(lineups_us, lines)        [{unit, slot, name, number, playerId, chips}] the first man of every slot, matched
"""

from __future__ import annotations

from typing import Any

from app.services.lineup_stats import attach_lineup_stats

# (category, title, [(stat, label)], the stat that orders the table). CFBD's own stat names; a column no row has is left out
TABLES: tuple[tuple[str, str, tuple[tuple[str, str], ...], str], ...] = (
    ("passing", "Passing", (("COMPLETIONS", "Cmp"), ("ATT", "Att"), ("PCT", "Pct"), ("YDS", "Yds"), ("YPA", "Y/A"), ("TD", "TD"), ("INT", "INT")), "YDS"),
    ("rushing", "Rushing", (("CAR", "Car"), ("YDS", "Yds"), ("YPC", "Avg"), ("TD", "TD"), ("LONG", "Long")), "YDS"),
    ("receiving", "Receiving", (("REC", "Rec"), ("YDS", "Yds"), ("YPR", "Avg"), ("TD", "TD"), ("LONG", "Long")), "YDS"),
    ("defensive", "Defense", (("TOT", "Tkl"), ("SOLO", "Solo"), ("TFL", "TFL"), ("SACKS", "Sacks"), ("QB HUR", "Hurries"), ("PD", "PD"), ("TD", "TD")), "TOT"),
    ("interceptions", "Interceptions", (("INT", "INT"), ("YDS", "Yds"), ("AVG", "Avg"), ("TD", "TD")), "INT"),
    ("fumbles", "Fumbles", (("FUM", "Fum"), ("LOST", "Lost"), ("REC", "Rec")), "FUM"),
    ("kicking", "Kicking", (("FGM", "FGM"), ("FGA", "FGA"), ("PCT", "Pct"), ("LONG", "Long"), ("XPM", "XPM"), ("XPA", "XPA"), ("PTS", "Pts")), "PTS"),
    ("punting", "Punting", (("NO", "Punts"), ("YDS", "Yds"), ("YPP", "Avg"), ("In 20", "In 20"), ("TB", "TB"), ("LONG", "Long")), "NO"),
    ("kickReturns", "Kick returns", (("NO", "Ret"), ("YDS", "Yds"), ("AVG", "Avg"), ("TD", "TD"), ("LONG", "Long")), "YDS"),
    ("puntReturns", "Punt returns", (("NO", "Ret"), ("YDS", "Yds"), ("AVG", "Avg"), ("TD", "TD"), ("LONG", "Long")), "YDS"),
)


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and value == value else None


def season_tables(lines: Any) -> list[dict[str, Any]]:
    """Every player with a stat line, a table a category, best first by its stat; a category nobody has is left out, and
    within one, a column no row fills."""
    by_category: dict[str, list[Any]] = {}
    for key, line in (lines.items() if isinstance(lines, dict) else []):
        category = getattr(line, "category", None) or (key[1] if isinstance(key, tuple) and len(key) == 2 else None)
        if isinstance(category, str):
            by_category.setdefault(category, []).append(line)
    out = []
    for category, title, columns, order in TABLES:
        rows = []
        for line in by_category.get(category, []):
            stats = {stat: _num(line.stats.get(stat)) for stat, _ in columns}
            if not any(v is not None for v in stats.values()):
                continue
            rows.append({"playerId": getattr(line, "player_id", None), "name": getattr(line, "player", None), "position": getattr(line, "position", None), "stats": stats})
        if not rows:
            continue
        rows.sort(key=lambda r: (r["stats"].get(order) is not None, r["stats"].get(order) or 0, r["name"] or ""), reverse=True)
        kept = [{"key": stat, "label": label} for stat, label in columns if any(r["stats"].get(stat) is not None for r in rows)]
        out.append({"category": category, "title": title, "columns": kept, "rows": rows})
    return out


def starters_from(lineups_us: Any, lines: Any) -> list[dict[str, Any]]:
    """Every slot's first man of our depth chart (the dumped `lineups.us` of a notes file), each matched to his season lines
    the way the program's lineups are (playerId and the impact chips, none for a lineman CFBD keeps no numbers for)."""
    if not isinstance(lineups_us, dict) or not isinstance(lineups_us.get("slots"), list):
        return []
    block = attach_lineup_stats({"us": {**lineups_us, "slots": [dict(s, players=[dict(p) for p in s.get("players") or [] if isinstance(p, dict)]) for s in lineups_us["slots"] if isinstance(s, dict)]}}, lines if isinstance(lines, dict) else {}, {})
    out = []
    seen: set[str] = set()
    for slot in block["us"]["slots"]:
        first = next((p for p in slot.get("players") or [] if isinstance(p.get("name"), str) and p["name"].strip()), None)
        if first is None:
            continue
        key = f"{slot.get('slot')}|{first['name']}"
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "unit": slot.get("unit") if isinstance(slot.get("unit"), str) else None,
            "slot": slot.get("slot") if isinstance(slot.get("slot"), str) else None,
            "name": first["name"].strip(),
            "number": first.get("number") if isinstance(first.get("number"), int) and not isinstance(first.get("number"), bool) else None,
            "playerId": first.get("playerId") if isinstance(first.get("playerId"), str) else None,
            "chips": [c for c in first.get("chips") or [] if isinstance(c, str)],
        })
    return out
