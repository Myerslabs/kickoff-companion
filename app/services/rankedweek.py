"""The week's AP-ranked games (queue items 10 to 12, mocks approved 2026-10-13): the Top 25 page's cards and the
newspaper's matchups come from here, so the two always agree.

Every game of the week (CFBD's calendar week; our week when the calendar has none) with an AP Top 25 team, in the
owner's order ("The higher the ranked game, the higher the article"): games of two ranked teams first, the lowest pair
of ranks first; then games of one ranked team, by its rank. Each game carries what the Pre-Game Program's cover shows
("Same initial information for every game that the cover has in the pre-game program"): both teams with their AP
rank, record, conference record, last five and head coach; the kickoff, the stadium and TV; the line and the
over/under; the pregame win probability; the weather. Then the live score, quarter and clock from the ticker's own
cached calls, our game following the spoiler delay, and a final's score by quarter. Ranked teams with no game are
listed as off this week ("no game or article" for them).

The newspaper adds a headline to each matchup before kickoff and after the final (app/services/headlines.py) and keeps
the week's edition for the season (app/services/editions.py): the masthead's arrows page back through them.

Calls, all through the quota guard and the cache: the week's /games, /lines, /metrics/wp/pregame and /games/media (the
same questions the newspaper's slate asks, so they share the cache), /coaches for the year (every head coach in one
call, a week's cache), /games/weather for the week (plans with CFBD's weather only), and the ticker's own (the slate,
and the scoreboard only while a game is on). Nothing is fetched without someone looking at a page.

  RankedWeekService(program, ticker, editions)
    top25(delay)                                 Assembled: the Top 25 page (/api/top25)
    paper(data, parts, delay, edition=None)      the newspaper's answer plus "edition", "editions" and "rankedWeek"
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.cache import DataKind
from app.cfbd.models import BettingGame, CalendarWeek, Coach, Game, GameMedia, GameWeather, PregameWinProbability
from app.services import gamekeys, headlines
from app.services.coaches import resolve as resolve_coaches
from app.services.context16 import form_for, form_table
from app.services.editions import Editions, key_for, label_for, order_of
from app.services.lines import line_block
from app.services.notes import load_notes
from app.services.parts import Assembled, Part, assemble, calendar_slot, statuses
from app.services.program import POLL_NAMES, ProgramService, compass
from app.services.ticker import TickerService

log = logging.getLogger("kickoff.rankedweek")

AP_NAME = "AP Top 25"
COLLECT_REUSE_S = 60  # the ticker's week reused this long by these pages: a minute's refresh bills the scoreboard at most once
_PERIOD = re.compile(r"^(?:Q(?P<q>[1-4])|(?P<ot>\d*)OT)(?:\s+(?P<clock>\d{1,2}:\d{2}))?$")


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _word(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _when(value: Any) -> datetime | None:
    raw = _word(value)
    if raw is None:
        return None
    try:
        out = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return out.astimezone(timezone.utc) if out.tzinfo is not None else None


def week_ranks(weeks: list[Any], week: Any, season_type: Any) -> tuple[dict[str, dict[str, int]], int | None]:
    """The polls as they stood for a week: the newest regular-season poll numbered no later than the week (review,
    2026-10-13: the next week's poll lands on Sunday evening, before the calendar's week ends on Monday, and must not
    rewrite the week that was played). Bowl season reads the last regular poll; a week before the first poll reads the
    first one. ({short name: {school: rank}}, the poll's week)."""
    pool = [w for w in weeks if isinstance(getattr(w, "week", None), int) and str(getattr(w, "season_type", None) or "regular") != gamekeys.POSTSEASON]
    if not pool:
        return {}, None
    if str(season_type or "regular") != gamekeys.POSTSEASON and isinstance(week, int):
        upto = [w for w in pool if w.week <= week]
        pick = max(upto, key=gamekeys.poll_order) if upto else min(pool, key=gamekeys.poll_order)
    else:
        pick = max(pool, key=gamekeys.poll_order)
    out: dict[str, dict[str, int]] = {}
    for poll in getattr(pick, "polls", None) or []:
        short = POLL_NAMES.get(getattr(poll, "poll", None))
        if short:
            out[short] = {r.school: r.rank for r in getattr(poll, "ranks", None) or [] if r.school and isinstance(r.rank, int)}
    return out, pick.week


def _game_ok(game: Any) -> bool:
    """A saved matchup the keepsake can work with: a dict with a whole-number id and both teams as dicts."""
    return isinstance(game, dict) and _int(game.get("gameId")) is not None and isinstance(game.get("home"), dict) and isinstance(game.get("away"), dict)


def period_of(detail: Any) -> tuple[int | None, str | None]:
    """(period, clock) from the ticker's status text: 'Q2 7:02' -> (2, '7:02'), 'OT' -> (5, None), '2OT' -> (6, None)."""
    match = _PERIOD.match(_word(detail) or "")
    if not match:
        return None, None
    if match.group("q"):
        return int(match.group("q")), match.group("clock")
    extra = int(match.group("ot")) if match.group("ot") else 1
    return 4 + extra, match.group("clock")


def ranked_order(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The owner's order: games of two ranked teams by the sum of their ranks (then the better rank), then games of one
    ranked team by its rank. A game id breaks any tie, so the order never shuffles between refreshes."""
    def rank(game: dict[str, Any], side: str) -> int | None:
        block = game.get(side) if isinstance(game.get(side), dict) else {}
        return _int(block.get("rank"))

    def key(game: dict[str, Any]) -> tuple[int, int, int, int]:
        h, a = rank(game, "home"), rank(game, "away")
        best = min(r for r in (h, a, 99) if r is not None)
        both = h is not None and a is not None
        return (0 if both else 1, (h + a) if both else best, best, _int(game.get("gameId")) or 0)

    return sorted(games, key=key)


class RankedWeekService:
    def __init__(self, program: ProgramService, ticker: TickerService, editions: Editions) -> None:
        self.program = program
        self.ticker = ticker
        self.editions = editions
        self._collected: dict[float, tuple[float, Any]] = {}  # delay -> (when, the ticker's week)

    @property
    def year(self) -> int:
        return self.program.year

    @property
    def team(self) -> str:
        return self.program.team

    # --- the week -------------------------------------------------------------------------------------------

    async def week(self, delay: float) -> tuple[dict[str, Any], dict[str, Part]]:
        """(the week's answer without headlines, the parts it used)."""
        program = self.program
        now = program.client._clock()
        core = await program._core()
        slot, _source, ticker_parts, entries = await self._collect(delay)
        parts: dict[str, Part] = dict(core)
        for name in ("calendar", "slate", "scoreboard"):
            if name in ticker_parts:
                parts[name] = ticker_parts[name]
        teams = program._teams(core["teams"])
        team_models = {t.school: t for t in core["teams"].records if t.school}
        records = {r.team: r for r in core["records"].records}
        week, season_type = slot if slot else (None, "regular")
        ranks, poll_week = week_ranks(core["rankings"].records, week, season_type)
        ap = ranks.get("AP", {})
        data: dict[str, Any] = {
            "season": self.year,
            "week": week,
            "seasonType": season_type,
            "label": label_for(key_for(week, season_type) or ""),
            "poll": {"name": AP_NAME, "week": poll_week, "teams": len(ap)} if ap else None,
            "delaySeconds": delay,
            "weather": "cfbd" if program.client.capabilities.weather else "none",
            "games": [],
            "offThisWeek": [],
            "counts": {"live": 0, "pre": 0, "final": 0},
            "ourGame": None,
            "weekEnd": None,
            "note": None,
        }
        cal = next((w for w in parts["calendar"].records if isinstance(w, CalendarWeek) and w.week == week and str(w.season_type or "regular") == season_type), None) if "calendar" in parts else None
        data["weekEnd"] = cal.end_date if cal is not None else None
        if week is None:
            data["note"] = "No week to show yet: the schedule has not loaded."
            return data, parts
        if not ap:
            data["note"] = "No AP poll yet this season." if core["rankings"].ok else "The AP poll could not be loaded; the app tries again."
            return data, parts

        params: dict[str, Any] = {"year": self.year, "week": week}
        if season_type == gamekeys.POSTSEASON:
            params["seasonType"] = gamekeys.POSTSEASON
        fetches = [
            program._f("weekGames", "/games", params, Game, DataKind.SCHEDULE),
            program._f("weekLines", "/lines", params, BettingGame, DataKind.LINES),
            program._f("weekPregame", "/metrics/wp/pregame", params, PregameWinProbability, DataKind.SEASON_STATS),
            program._f("weekMedia", "/games/media", params, GameMedia, DataKind.SCHEDULE),
            program._f("headCoaches", "/coaches", {"year": self.year}, Coach, DataKind.TEAMS),
        ]
        if program.client.capabilities.weather:
            fetches.append(program._f("weekWeather", "/games/weather", {**params, "classification": "fbs"}, GameWeather, DataKind.WEATHER))
        for part in await asyncio.gather(*fetches):
            parts[part.name] = part

        week_games = parts["weekGames"].records if parts["weekGames"].ok else (parts["slate"].records if "slate" in parts and parts["slate"].ok else [])
        fresher = {g.id: g for g in (parts["slate"].records if "slate" in parts and parts["slate"].ok else [])}  # the ticker's slate, five minutes fresh on a game day
        by_entry = {e.get("gameId"): e for e in entries if isinstance(e, dict)}
        lines = {b.id: b for b in parts["weekLines"].records}
        pregame = {p.game_id: p for p in parts["weekPregame"].records}
        media = {m.id: m.outlet for m in parts["weekMedia"].records if (m.media_type or "").lower() == "tv" and m.outlet}
        weather = {w.id: w for w in parts["weekWeather"].records} if "weekWeather" in parts else {}
        coaches = self._head_coaches(parts["headCoaches"].records)
        abbreviations = program._abbreviations(teams)

        mine = next((g for g in week_games if isinstance(g, Game) and self.team in (g.home_team, g.away_team)), None)
        if mine is not None:
            home = mine.home_team == self.team
            data["ourGame"] = {"gameId": mine.id, "opponent": mine.away_team if home else mine.home_team, "homeAway": "neutral" if mine.neutral_site else "home" if home else "away", "kickoff": mine.start_date}
        ranked = [g for g in week_games if isinstance(g, Game) and g.home_team and g.away_team and (g.home_team in ap or g.away_team in ap)]
        states: dict[int, tuple[str, str | None, int | None, int | None]] = {}
        for g in ranked:
            entry = by_entry.get(g.id)
            if entry is None:
                try:
                    entry = await self.ticker.entry_for(g, team_models, ap, delay, now)
                except Exception:  # noqa: BLE001 - one game never fails the week; logged
                    log.exception("No status for game %s", g.id)
                    entry = None
            if entry is None:
                states[g.id] = ("final" if g.completed else "pre", None, None, None)
                continue
            home = entry.get("home") if isinstance(entry.get("home"), dict) else {}
            away = entry.get("away") if isinstance(entry.get("away"), dict) else {}
            status = entry.get("status") if entry.get("status") in ("pre", "live", "final") else "pre"
            states[g.id] = (status, _word(entry.get("detail")), _int(home.get("points")), _int(away.get("points")))

        # the last five never gives away a result this page does not show yet (our game under the spoiler delay)
        hidden = {gid for gid, state in states.items() if state[0] != "final"}
        pool = [g for g in [*core["games"].records, *core["schedule"].records, *week_games] if isinstance(g, Game) and g.id not in hidden]
        table = form_table(pool)
        notes_coaches = self._our_notes_coaches(ranked)  # freeze wave F3: our game's notes name its coaches first
        notes_broadcast = self._our_notes_broadcast(ranked)  # freeze wave F4: and its TV crew

        def side(school: str, points: int | None, line_scores: Any, final: bool) -> dict[str, Any]:
            block = program._team_block(school, teams, records, ranks)
            scores = [s for s in (line_scores or []) if _int(s) is not None] if final else []
            block.update(rank=ap.get(school), points=points, lineScores=scores or None, headCoach=self._coach_for(school, coaches, notes_coaches), form=form_for(table, school))
            return block

        out = []
        for g in ranked:
            status, detail, home_points, away_points = states[g.id]
            source = fresher.get(g.id) or g
            final = status == "final"
            period, clock = period_of(detail) if status == "live" else (None, None)
            book = lines.get(g.id)
            wp = pregame.get(g.id)
            is_us = self.team in (g.home_team, g.away_team)
            out.append({
                "gameId": g.id,
                "week": g.week,
                "seasonType": g.season_type or "regular",
                "bowl": gamekeys.label(g),
                "kickoff": g.start_date,
                "startTimeTbd": bool(g.start_time_tbd),
                "neutralSite": bool(g.neutral_site),
                "conferenceGame": bool(g.conference_game),
                "conference": g.home_conference if g.conference_game else None,
                "venue": g.venue,
                "tv": media.get(g.id),
                "broadcast": notes_broadcast if is_us else None,  # freeze wave F4: the crew from our notes, beside the network
                "status": status,
                "detail": detail,
                "period": period,
                "clock": clock,
                "isUs": is_us,
                "href": "#live" if is_us else f"#box={g.id}",
                "home": side(g.home_team, home_points, source.home_line_scores, final),
                "away": side(g.away_team, away_points, source.away_line_scores, final),
                "line": line_block(book.lines[0] if book and book.lines else None, abbreviations),
                "homeWinProbability": _num(wp.home_win_probability) if wp is not None else None,
                "weather": self._weather(weather.get(g.id)),
            })
        games = ranked_order(out)
        data["games"] = games
        data["counts"] = {s: sum(1 for g in games if g["status"] == s) for s in ("live", "pre", "final")}
        if parts["weekGames"].ok or ("slate" in parts and parts["slate"].ok):
            playing = {t for g in week_games if isinstance(g, Game) for t in (g.home_team, g.away_team) if t}
            off = sorted((school for school in ap if school not in playing), key=lambda s: ap[s])
            data["offThisWeek"] = [{**program._team_block(school, teams, records, ranks), "rank": ap[school]} for school in off]
        return data, parts

    async def _collect(self, delay: float) -> Any:
        """The ticker's week (its live scores, our game under the delay), reused for a minute: the Top 25 page and the
        paper refresh every minute on every device, and a fresh scoreboard each time would bill a call a minute each."""
        key = round(float(delay), 1)
        now = self.program.client._clock().timestamp()  # the app's clock (the simulator's, a test's), not the machine's
        fresh = lambda at: 0 <= now - at < COLLECT_REUSE_S  # noqa: E731
        hit = self._collected.get(key)
        if hit is not None and fresh(hit[0]):
            return hit[1]
        answer = await self.ticker.collect(delay)
        self._collected = {k: v for k, v in self._collected.items() if fresh(v[0])}
        self._collected[key] = (now, answer)
        return answer

    def _head_coaches(self, records: list[Any]) -> dict[str, str]:
        """{school: head coach} for this season as CFBD's /coaches lists them (the resolver puts the notes and the season's
        load ahead of these, freeze wave F3)."""
        out: dict[str, str] = {}
        for coach in records:
            if not isinstance(coach, Coach):
                continue
            name = " ".join(p for p in (_word(coach.first_name), _word(coach.last_name)) if p)
            for season in coach.seasons or []:
                if name and season.year == self.year and _word(season.school) and season.school not in out:
                    out[season.school] = name
        return out

    def _coach_for(self, school: str, cfbd_heads: dict[str, str], notes_coaches: dict[str, Any] | None) -> str | None:
        """One school's head coach through the one resolver: our game's notes (when the school is in them), the season's
        coaches load, then CFBD."""
        block = None
        if isinstance(notes_coaches, dict):
            for key in ("us", "them"):
                side = notes_coaches.get(key)
                if isinstance(side, dict) and side.get("team") == school:
                    block = side
        return resolve_coaches(school, notes=block, season=self.program.season_notes.coaches_for(school), cfbd_head=cfbd_heads.get(school))["headCoach"]

    def _our_notes_file(self, games: list[Any]) -> tuple[Any, Any]:
        """(our game this week, its notes file) or (None, None)."""
        ours = next((g for g in games if self.team in (g.home_team, g.away_team)), None)
        if ours is None:
            return None, None
        notes, _error = load_notes(self.program.settings.data_dir, ours.id)
        return ours, notes

    def _our_notes_broadcast(self, games: list[Any]) -> dict[str, Any] | None:
        """The TV crew of our game's notes this week (freeze wave F4: the Top 25 card and the paper's box carry it)."""
        _ours, notes = self._our_notes_file(games)
        return notes.broadcast.model_dump() if notes is not None and notes.broadcast is not None else None

    def _our_notes_coaches(self, games: list[Any]) -> dict[str, Any] | None:
        """The coaches block of our game's notes this week, if the week has our game and the notes name anyone."""
        ours, notes = self._our_notes_file(games)
        if notes is None or notes.coaches is None:
            return None
        block = notes.coaches.model_dump()
        for key, school in (("us", self.team), ("them", ours.away_team if ours.home_team == self.team else ours.home_team)):
            side = block.get(key)
            if isinstance(side, dict) and not side.get("team"):
                side["team"] = school
        return block

    @staticmethod
    def _weather(row: Any) -> dict[str, Any] | None:
        """CFBD's weather for a game: its temperature, wind and sky (verified 2026-10-13: the temperature is always
        filled, the condition often null), or None."""
        if not isinstance(row, GameWeather):
            return None
        temp = _num(row.temperature)
        wind = _num(row.wind_speed)
        if temp is None and wind is None and not _word(row.weather_condition) and row.game_indoors is not True:
            return None
        return {"tempF": temp, "windMph": wind, "windDir": compass(row.wind_direction), "sky": _word(row.weather_condition), "indoors": row.game_indoors is True, "precipitation": _num(row.precipitation)}

    # --- the Top 25 page --------------------------------------------------------------------------------------

    async def top25(self, delay: float) -> Assembled:
        data, parts = await self.week(delay)
        data["parts"] = statuses(parts, self.program.client._clock())
        return assemble(data, parts)

    # --- the newspaper's edition --------------------------------------------------------------------------------

    async def paper(self, data: dict[str, Any], parts: dict[str, Part], delay: float, edition: str | None = None) -> dict[str, Part]:
        """Add this week's edition (or a saved one), the edition list and the week's facts to the newspaper's answer.
        Returns the parts to assemble the answer from (the newspaper's and the week's)."""
        sections = [s for s in data.get("weeks") or [] if isinstance(s, dict)]
        now = self.program.client._clock()
        if edition:
            # an earlier edition is read from its file: the week's key from the cached calendar, never the live week
            slot, slot_parts = await self._slot()
            current = key_for(*slot) if slot else None
            if edition != current:
                merged = {**parts, **slot_parts}
                if "games" in slot_parts and slot_parts["games"].ok:
                    self._settle(current, slot_parts["games"].records, now)
                data["rankedWeek"] = {"season": self.year, "week": slot[0] if slot else None, "seasonType": slot[1] if slot else None, "label": label_for(current or "")}
                data["editions"] = self._edition_list(sections, current, now)
                data["edition"] = self._earlier(edition, sections)
                return merged
        week, week_parts = await self.week(delay)
        merged = {**parts, **week_parts}
        current = key_for(week.get("week"), week.get("seasonType"))
        if current and "games" in week_parts and week_parts["games"].ok:
            self._settle(current, week_parts["games"].records, now)
        data["rankedWeek"] = {k: week.get(k) for k in ("season", "week", "seasonType", "label", "poll", "counts", "ourGame", "note", "delaySeconds")}
        data["editions"] = self._edition_list(sections, current, now)
        saved = self.editions.load(current) if current else None
        if saved is not None and saved.get("frozen") is True:
            data["edition"] = {**saved, "current": True}  # the season is over and this week's paper is kept as printed
            return merged
        data["edition"] = self._current(week, week_parts, sections, current)
        return merged

    async def _slot(self) -> tuple[tuple[int, str] | None, dict[str, Part]]:
        """This week's (week, seasonType) from the cached calendar, else our week; the parts it read."""
        program = self.program
        core = await program._core()
        calendar = await program._f("calendar", "/calendar", {"year": self.year}, CalendarWeek, DataKind.REFERENCE)
        now = program.client._clock()
        slot = calendar_slot(calendar.records, now) or self.ticker.week_of(core["schedule"].records, now)
        return slot, {**core, "calendar": calendar}

    def _section_key(self, section: dict[str, Any]) -> str | None:
        if not isinstance(section.get("gameId"), int):
            return None
        post = str(section.get("label") or "").startswith("Bowl")
        return key_for(section.get("week"), gamekeys.POSTSEASON if post else "regular")

    def _edition_list(self, sections: list[dict[str, Any]], current: str | None, now: datetime | None = None) -> list[dict[str, Any]]:
        listed: dict[str, dict[str, Any]] = {e["key"]: {**e, "saved": True} for e in self.editions.keys()}
        for s in sections:
            key = self._section_key(s)
            if key and key not in listed:
                listed[key] = {"key": key, "label": label_for(key), "opponent": s.get("opponent"), "homeAway": s.get("homeAway"), "saved": False, "frozen": False}
        if current and current not in listed:
            listed[current] = {"key": current, "label": label_for(current), "opponent": None, "homeAway": None, "saved": False, "frozen": False}
        out = sorted(listed.values(), key=lambda e: order_of(e["key"]))
        for e in out:
            e["current"] = e["key"] == current
            end = _when(e.get("weekEnd"))
            ahead = end is None or now is None or end > now
            if current and order_of(e["key"]) > order_of(current) and not e.get("frozen") and ahead:
                e["future"] = True  # a saved edition from a later week (a clock that went back): never "earlier"
        return [e for e in out if not e.get("future")]

    def _section_for(self, sections: list[dict[str, Any]], key: str | None) -> dict[str, Any] | None:
        return next((s for s in sections if self._section_key(s) == key), None)

    def _earlier(self, key: str, sections: list[dict[str, Any]]) -> dict[str, Any] | None:
        """A saved edition, or one rebuilt from the season's headlines (weeks before the paper kept editions have no
        matchups); None for a week the season has no paper for."""
        saved = self.editions.load(key)
        if saved is not None:
            return {**saved, "current": False}
        section = self._section_for(sections, key)
        if section is None:
            return None
        return {
            "key": key,
            "season": self.year,
            "label": label_for(key),
            "week": section.get("week"),
            "seasonType": gamekeys.POSTSEASON if key == "postseason" else "regular",
            "gameId": section.get("gameId"),
            "opponent": section.get("opponent"),
            "homeAway": section.get("homeAway"),
            "date": section.get("kickoff"),
            "headlines": section.get("headlines") or [],
            "matchups": [],
            "offThisWeek": [],
            "frozen": True,
            "rebuilt": True,
            "current": False,
        }

    def _current(self, week: dict[str, Any], week_parts: dict[str, Part], sections: list[dict[str, Any]], key: str | None) -> dict[str, Any]:
        tz = self.program.settings.tzinfo
        # this week's headlines; before any of them is published, the newest week's (the paper is never blank)
        section = self._section_for(sections, key) or (sections[0] if sections else None)
        ours = week.get("ourGame") if isinstance(week.get("ourGame"), dict) else None  # the masthead names this week's game
        games = [dict(g) for g in week.get("games") or []]
        frozen_lines = self.editions.frozen_headlines(key) if key else {}
        for game, line in zip(games, headlines.write_all(games, us=self.team, tz=tz), strict=True):
            kept = frozen_lines.get(game["gameId"]) if game["status"] == "final" else None
            game["headline"] = kept or line
        edition: dict[str, Any] = {
            "key": key,
            "season": self.year,
            "label": week.get("label"),
            "week": week.get("week"),
            "seasonType": week.get("seasonType"),
            "gameId": ours.get("gameId") if ours else None,
            "opponent": ours.get("opponent") if ours else None,
            "homeAway": ours.get("homeAway") if ours else None,
            "date": ours.get("kickoff") if ours else None,
            "headlines": (section.get("headlines") if section else None) or [],
            "matchups": games,
            "offThisWeek": week.get("offThisWeek") or [],
            "poll": week.get("poll"),
            "weekEnd": week.get("weekEnd"),
            "frozen": False,
        }
        if key is None:
            return {**edition, "current": True}
        # a week read in full is kept; one with its games, its teams or their records missing never overwrites a good file
        if all(name in week_parts and week_parts[name].ok for name in ("weekGames", "teams", "records")):
            self._keep(edition)
        return {**edition, "current": True}

    def _keep(self, edition: dict[str, Any]) -> None:
        """Save this week's edition. A final already saved is never written back to an earlier state (a reader with a
        longer spoiler delay sees the game later; the keepsake keeps what was printed). The current week's edition is
        never frozen: that happens once the week is over (_settle)."""
        key = edition["key"]
        saved = self.editions.load(key) or {}
        if saved.get("frozen") is True:
            return
        old = {g["gameId"]: g for g in saved.get("matchups") or [] if _game_ok(g)}
        matchups = []
        for game in edition["matchups"]:
            before = old.pop(game["gameId"], None)
            matchups.append(before if before and before.get("status") == "final" and game["status"] != "final" else game)
        # a game the saved paper printed stays in it, whatever a later answer leaves out (an empty or partial list)
        matchups = ranked_order(matchups + list(old.values()))
        to_save = {**{k: v for k, v in edition.items() if k != "current"}, "matchups": matchups, "frozen": False}
        try:
            self.editions.save(to_save)
        except Exception:  # noqa: BLE001 - the keepsake never breaks the paper; logged
            log.exception("The paper's edition %s could not be kept", key)

    def _settle(self, current: str | None, season_games: list[Any], now: datetime | None = None) -> None:
        """Freeze every saved edition whose week is over (a week before this one, or any other whose calendar week has
        ended: bowl season once the title game is played): each matchup still short of its final takes the final score
        from the season's games (already cached, no call) and its final headline, a game the season never finished
        (postponed, cancelled) reads "Not played", and the edition is frozen and never written again."""
        games = {g.id: g for g in season_games if isinstance(g, Game)}
        tz = self.program.settings.tzinfo
        for entry in self.editions.keys():
            if entry.get("frozen") or entry["key"] == current:
                continue
            saved = self.editions.load(entry["key"])
            if saved is None:
                continue
            end = _when(saved.get("weekEnd"))
            earlier = current is not None and order_of(entry["key"]) < order_of(current)
            if not (earlier or (end is not None and now is not None and now > end)):
                continue
            matchups = []
            for game in saved.get("matchups") or []:
                if not _game_ok(game):
                    continue
                done = games.get(game["gameId"])
                if game.get("status") != "final" and not (done is not None and done.completed):
                    game = {**game, "status": "unplayed", "detail": "Not played", "period": None, "clock": None, "headline": None}
                elif game.get("status") != "final" and done is not None and done.completed and _int(done.home_points) is not None and _int(done.away_points) is not None:
                    game = {
                        **game,
                        "status": "final",
                        "detail": "Final",
                        "period": None,
                        "clock": None,
                        "home": {**game["home"], "points": done.home_points, "lineScores": [s for s in done.home_line_scores or [] if _int(s) is not None] or None},
                        "away": {**game["away"], "points": done.away_points, "lineScores": [s for s in done.away_line_scores or [] if _int(s) is not None] or None},
                    }
                    game["headline"] = headlines.write(game, us=self.team, tz=tz)
                matchups.append(game)
            try:
                self.editions.save({**saved, "matchups": matchups, "frozen": True}, force=True)
            except Exception:  # noqa: BLE001 - the keepsake never breaks the paper; logged
                log.exception("The paper's edition %s could not be frozen", entry["key"])
