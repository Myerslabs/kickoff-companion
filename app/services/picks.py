"""Picks of the week (FEAT-2, owner 2026-10-25: "Named with the paper's weekly name. Power: SEC, Big Ten, Big 12, ACC, Pac-12
and independents; the rest Group of 5. Four timeslots, chosen once game and broadcast information exists"; 2026-10-30
"Claude picks": Claude Code with web search picks every game, one line of reason, the market's line beside it).

Every game of the week with an FBS team, from the answers the Top 25 page already caches (the week's games, lines and TV:
no call of its own), in four kickoff windows by the local clock, each game Power when a Power school plays in it; Claude's
picks from the writing run `picks` (keyed by the week, like the paper) and, until that run, the paper's own picks for the
games it covered. A finished game marks its pick right or wrong, and the week's record counts them.

    POWER, SLOTS
    slot_of(kickoff_local) -> str | None   the window a kickoff falls in
    is_power(home_conf, away_conf, home, away, fbs_conf) -> bool
    pick_right(pick, game_row) -> bool | None
    await picks_week(state) -> dict        the page's answer
    packet_games(answer) -> list[dict]     the games as the picks run sees them
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.cache import DataKind
from app.cfbd.models import BettingGame, Game, GameMedia
from app.services import gamekeys
from app.services.editions import key_for, label_for
from app.services.lines import line_block
from app.services.rankedweek import week_ranks
from app.services.writing import WritingStore

log = logging.getLogger("kickoff.picks")

POWER = frozenset({"SEC", "Big Ten", "Big 12", "ACC", "Pac-12", "FBS Independents"})
SLOTS: tuple[tuple[str, str, str, int, int], ...] = (  # (id, name, the hours in words, from hour, to hour), local time
    ("early", "Early", "kickoff before 2 PM", 0, 14),
    ("afternoon", "Afternoon", "2 to 6 PM", 14, 18),
    ("prime", "Prime time", "6 to 9 PM", 18, 21),
    ("late", "Late", "9 PM and after", 21, 24),
)


def slot_of(kickoff_local: datetime | None) -> str | None:
    if kickoff_local is None:
        return None
    hour = kickoff_local.hour
    return next((sid for sid, _name, _words, start, end in SLOTS if start <= hour < end), None)


def is_power(home_conf: Any, away_conf: Any, home: Any = None, away: Any = None, fbs_conf: dict[str, str] | None = None) -> bool:
    """A game is Power when either school plays in a Power conference or as an FBS independent (the game's own conference
    names first, CFBD's team list for a school the game left blank)."""
    fbs_conf = fbs_conf or {}
    names = [home_conf or fbs_conf.get(str(home or "")), away_conf or fbs_conf.get(str(away or ""))]
    return any(isinstance(n, str) and n in POWER for n in names)


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def pick_right(pick: Any, row: dict[str, Any]) -> bool | None:
    """Right or wrong once the game is final with both scores; None before, for a tie, or a pick of neither school."""
    if not row.get("final") or not isinstance(pick, str):
        return None
    home, away = row.get("home") or {}, row.get("away") or {}
    hp, ap = home.get("points"), away.get("points")
    if not isinstance(hp, int) or not isinstance(ap, int) or hp == ap:
        return None
    winner = home.get("school") if hp > ap else away.get("school")
    if pick not in (home.get("school"), away.get("school")):
        return None
    return pick == winner


def _picks_from(record: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in (record or {}).get("picks") or []:
        if isinstance(p, dict) and isinstance(p.get("gameId"), int) and isinstance(p.get("pick"), str) and p["pick"].strip():
            out[p["gameId"]] = {"pick": p["pick"].strip(), "reason": p.get("reason") if isinstance(p.get("reason"), str) else None}
    return out


async def picks_week(state: Any) -> dict[str, Any]:
    """This week's games in their windows with Claude's picks. Reads only what the Top 25 page caches."""
    program, ranked, settings = state.program, state.rankedweek, state.settings
    slot, parts = await ranked._slot()
    week, season_type = slot if slot else (None, "regular")
    key = key_for(week, season_type)
    answer: dict[str, Any] = {"season": settings.season, "week": week, "seasonType": season_type, "key": key, "label": label_for(key or ""), "slots": [], "unscheduled": [], "counts": {"power": 0, "g5": 0}, "record": {"power": {"right": 0, "wrong": 0}, "g5": {"right": 0, "wrong": 0}}, "picksBy": None, "writtenAt": None, "ready": False, "note": None}
    if week is None or key is None:
        answer["note"] = "No week to show yet: the schedule has not loaded."
        return answer
    params: dict[str, Any] = {"year": settings.season, "week": week}
    if season_type == gamekeys.POSTSEASON:
        params["seasonType"] = gamekeys.POSTSEASON
    games_part, lines_part, media_part = await asyncio.gather(  # the Top 25 page's own keys: no call of their own once it loaded
        program._f("weekGames", "/games", params, Game, DataKind.SCHEDULE),
        program._f("weekLines", "/lines", params, BettingGame, DataKind.LINES),
        program._f("weekMedia", "/games/media", params, GameMedia, DataKind.SCHEDULE),
    )
    teams = program._teams(parts["teams"])
    fbs_conf = {school: str(meta.get("conference") or "") for school, meta in teams.items() if isinstance(meta, dict)}
    abbreviations = program._abbreviations(teams)
    ranks, _poll_week = week_ranks(parts["rankings"].records, week, season_type)
    ap = ranks.get("AP", {})
    lines = {b.id: b for b in lines_part.records if isinstance(b, BettingGame)}
    media = {m.id: m.outlet for m in media_part.records if isinstance(m, GameMedia) and (m.media_type or "").lower() == "tv" and m.outlet}
    store = WritingStore(settings.data_dir, settings.season)
    own = store.load("picks", key)
    picks = _picks_from(own)
    if picks:
        answer["picksBy"], answer["writtenAt"] = "claude", own.get("writtenAt") if own else None
    else:
        paper = store.load("paper", key)
        picks = _picks_from(paper)
        if picks:
            answer["picksBy"], answer["writtenAt"] = "paper", paper.get("writtenAt") if paper else None
    tz = settings.tzinfo
    windows: dict[str, list[dict[str, Any]]] = {sid: [] for sid, *_rest in SLOTS}
    timed = with_tv = 0
    for g in sorted((g for g in games_part.records if isinstance(g, Game) and g.home_team and g.away_team and (g.home_team in teams or g.away_team in teams)), key=lambda g: (g.start_date or "", g.id)):
        kickoff = _parse(g.start_date)
        local = kickoff.astimezone(tz) if kickoff else None
        tbd = bool(g.start_time_tbd) or local is None
        power = is_power(g.home_conference, g.away_conference, g.home_team, g.away_team, fbs_conf)
        book = lines.get(g.id)

        def side(school: str, points: Any) -> dict[str, Any]:
            meta = teams.get(school) or {}
            return {"school": school, "abbreviation": abbreviations.get(school), "rank": ap.get(school), "color": meta.get("color"), "altColor": meta.get("altColor"), "points": points if isinstance(points, int) and not isinstance(points, bool) else None, "fbs": school in teams}

        row: dict[str, Any] = {
            "gameId": g.id, "kickoff": g.start_date, "startTimeTbd": tbd, "tv": media.get(g.id), "power": power, "neutralSite": bool(g.neutral_site),
            "isUs": settings.team in (g.home_team, g.away_team), "final": bool(g.completed),
            "home": side(g.home_team, g.home_points), "away": side(g.away_team, g.away_points),
            "line": line_block(book.lines[0] if book and book.lines else None, abbreviations),
        }
        mine = picks.get(g.id)
        row["pick"], row["reason"] = (mine["pick"], mine["reason"]) if mine else (None, None)
        row["right"] = pick_right(row["pick"], row)
        group = "power" if power else "g5"
        answer["counts"][group] += 1
        if row["right"] is not None:
            answer["record"][group]["right" if row["right"] else "wrong"] += 1
        if not tbd:
            timed += 1
        if row["tv"]:
            with_tv += 1
        sid = None if tbd else slot_of(local)
        (windows[sid] if sid else answer["unscheduled"]).append(row)
    answer["slots"] = [{"id": sid, "name": name, "hours": words, "games": windows[sid]} for sid, name, words, _start, _end in SLOTS if windows[sid]]
    total = answer["counts"]["power"] + answer["counts"]["g5"]
    answer["ready"] = total > 0 and timed >= total * 0.6 and with_tv > 0  # the windows hold once most kickoffs are set and TV is out
    if not total:
        answer["note"] = "No games this week yet." if games_part.ok else "The week's games could not be loaded; the app tries again."
    return answer


def packet_games(answer: dict[str, Any]) -> list[dict[str, Any]]:
    """The week's games as the picks run sees them: the schools, their conferences' side, ranks, kickoff, TV and the line."""
    rows = [g for s in answer.get("slots") or [] for g in s.get("games") or []] + list(answer.get("unscheduled") or [])
    return [
        {"gameId": g["gameId"], "home": g["home"]["school"], "away": g["away"]["school"], "homeRank": g["home"].get("rank"), "awayRank": g["away"].get("rank"),
         "power": g["power"], "neutralSite": g["neutralSite"], "kickoff": g["kickoff"], "tv": g["tv"], "line": (g.get("line") or {}).get("formatted")}
        for g in rows if not g.get("final")
    ]
