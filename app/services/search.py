"""Find any team or player fast (Phase 15).

Two steps so typing never costs a call:
1. Local, on every keystroke: FBS teams (school, abbreviation, mascot) from the cached /teams/fbs, and
   our players and the next opponent's from their cached rosters.
2. Wide, only when asked ("Search every player"): CFBD's /player/search, one call per new term (kept a
   week like a roster). CFBD answers with up to 100 names from every season on record (recorded
   2026-09-27: one surname found players from 2009 on), so this season's FBS players come first and can
   open a player card; former players are listed as such.
3. Phase 17 (#8): when nothing local matches, up to three close spellings from the same local names
   (difflib, no call), so "sanches" offers "Sanchez" instead of a dead end.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import unicodedata
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import Game, PlayerSearchResult, RosterPlayer, Team
from app.config import Settings
from app.services import gamekeys
from app.services.logos import logo_fields
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses

MIN_LOCAL = 2
MIN_WIDE = 3
MAX_TERM = 40
TEAM_LIMIT = 8
PLAYER_LIMIT = 12
WIDE_LIMIT = 40
SUGGEST_LIMIT = 3
SUGGEST_CUTOFF = 0.75


def fold(value: Any) -> str:
    """Lower case with accents and punctuation off, so an accented name matches plain typing."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", "", text.lower())).strip()


def clean_term(value: Any) -> str:
    return re.sub(r"\s+", " ", value.strip())[:MAX_TERM] if isinstance(value, str) else ""


def score(term: str, *names: Any) -> int | None:
    """0 for an exact match, 1 for a prefix of the name or of a word in it, 2 for a substring, None for no match."""
    best: int | None = None
    for name in names:
        f = fold(name)
        if not f or not term:
            continue
        if f == term:
            s = 0
        elif f.startswith(term) or any(word.startswith(term) for word in f.split()):
            s = 1
        elif term in f:
            s = 2
        else:
            continue
        best = s if best is None else min(best, s)
    return best


def suggestions(term: str, names: list[Any]) -> list[str]:
    """Close spellings of `term` among `names` (schools, mascots, players' full and last names): the names
    themselves, most alike first, no duplicates. Compared folded, so case and accents never matter."""
    if len(term) < MIN_WIDE:
        return []
    by_fold: dict[str, str] = {}
    for name in names:
        if isinstance(name, str) and name.strip():
            by_fold.setdefault(fold(name), name.strip())
    by_fold.pop("", None)
    close = difflib.get_close_matches(term, list(by_fold), n=SUGGEST_LIMIT, cutoff=SUGGEST_CUTOFF)
    return [by_fold[f] for f in close if f != term]


class SearchService:
    def __init__(self, client: CfbdClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.fetcher = PartFetcher(client, 4)

    @property
    def year(self) -> int:
        return self.settings.season

    async def search(self, q: Any, *, wide: bool = False) -> Assembled:
        term_raw = clean_term(q)
        term = fold(term_raw)
        teams_part, schedule_part = await asyncio.gather(
            self.fetcher.fetch("teams", "/teams/fbs", {"year": self.year}, Team, DataKind.TEAMS),
            self.fetcher.fetch("schedule", "/games", {"year": self.year, "team": self.settings.team}, Game, DataKind.SCHEDULE),
        )
        parts: dict[str, Part] = {"teams": teams_part, "schedule": schedule_part}
        opponent = self._next_opponent(schedule_part.records)
        rosters = [self.fetcher.fetch("roster", "/roster", {"team": self.settings.team, "year": self.year}, RosterPlayer, DataKind.ROSTER)]
        if opponent:
            rosters.append(self.fetcher.fetch("opponentRoster", "/roster", {"team": opponent, "year": self.year}, RosterPlayer, DataKind.ROSTER))
        for part in await asyncio.gather(*rosters):
            parts[part.name] = part
        fbs = {t.school: t for t in teams_part.records if t.school}

        teams: list[dict[str, Any]] = []
        players: list[dict[str, Any]] = []
        if len(term) >= MIN_LOCAL:
            for t in fbs.values():
                s = score(term, t.school, t.abbreviation, t.mascot, f"{t.school} {t.mascot or ''}")
                if s is not None:
                    teams.append({"school": t.school, "abbreviation": t.abbreviation, "conference": t.conference, "mascot": t.mascot, **logo_fields(t.id, t.logos), "isUs": t.school == self.settings.team, "_s": s})  # Phase 16: local logo URLs
            for name, owner in (("roster", self.settings.team), ("opponentRoster", opponent)):
                part = parts.get(name)
                for p in part.records if part else []:
                    full = " ".join(x for x in (p.first_name, p.last_name) if x)
                    s = score(term, full, p.last_name)
                    if s is None and term.isdigit() and p.jersey is not None and str(p.jersey) == term:
                        s = 1
                    if s is not None:
                        players.append(self._player(p.id, full, p.team or owner, p.position, p.jersey, True, fbs, s))
        suggest: list[str] = []
        if len(term) >= MIN_LOCAL and not teams and not players:
            names: list[Any] = [x for t in fbs.values() for x in (t.school, t.mascot)]
            for name in ("roster", "opponentRoster"):
                part = parts.get(name)
                for p in part.records if part else []:
                    names += [" ".join(x for x in (p.first_name, p.last_name) if x), p.last_name]
            suggest = suggestions(term, names)
        teams.sort(key=lambda t: (t["_s"], not t["isUs"], t["school"] or ""))
        players.sort(key=lambda p: (p["_s"], not p["isUs"], p["name"] or ""))

        wide_rows: list[dict[str, Any]] = []
        wide_note = None
        if wide:
            if len(term) < MIN_WIDE:
                wide_note = f"Type at least {MIN_WIDE} letters to search every player."
            else:
                part = await self.fetcher.fetch("playerSearch", "/player/search", {"searchTerm": term_raw}, PlayerSearchResult, DataKind.ROSTER)
                parts["playerSearch"] = part
                local_ids = {p["playerId"] for p in players}
                for r in part.records:
                    if str(r.id) in local_ids:
                        continue
                    current = isinstance(r.active_end_year, int) and r.active_end_year >= self.year
                    s = score(term, r.name, r.last_name)
                    row = self._player(r.id, r.name, r.team, r.position, r.jersey, current and r.team in fbs, fbs, 3 if s is None else s)
                    wide_rows.append({**row, "current": current, "fromYear": r.active_start_year, "toYear": r.active_end_year, "hometown": r.hometown})
                wide_rows.sort(key=lambda p: (not p["canOpen"], p["_s"], p["name"] or ""))
                wide_rows = wide_rows[:WIDE_LIMIT]
                if not part.ok:
                    wide_note = "CFBD's player search did not answer; the teams and rosters above are from the app's own copy."
        for row in (*teams, *players, *wide_rows):
            row.pop("_s", None)
        data = {
            "q": term_raw,
            "teams": teams[:TEAM_LIMIT],
            "players": players[:PLAYER_LIMIT],
            "wide": wide_rows if wide else None,
            "wideNote": wide_note,
            "suggest": suggest,
            "opponent": opponent,
            "minLocal": MIN_LOCAL,
            "minWide": MIN_WIDE,
            "parts": statuses(parts, self.client._clock()),
        }
        return assemble(data, parts)

    def _player(self, pid: Any, name: str | None, team: str | None, position: str | None, jersey: int | None, can_open: bool, fbs: dict[str, Team], s: int) -> dict[str, Any]:
        t = fbs.get(team or "")
        return {
            "playerId": str(pid) if pid is not None else None,
            "name": name,
            "team": team,
            "abbreviation": t.abbreviation if t else None,
            "position": position,
            "number": jersey,
            "isUs": team == self.settings.team,
            "canOpen": bool(can_open and pid is not None and str(pid).isdigit()),
            "_s": s,
        }

    def _next_opponent(self, games: list[Game]) -> str | None:
        upcoming = sorted((g for g in games if not g.completed and g.week is not None), key=gamekeys.order)
        if not upcoming:
            return None
        return gamekeys.opponent_of(upcoming[0], self.settings.team)
