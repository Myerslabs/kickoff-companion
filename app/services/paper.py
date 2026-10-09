"""The newspaper's weeks (Phase 17 #26): the season's headlines grouped by game week, each with a topic for its
pixel-art picture and the players it names (for their own pixelated headshot).

A game week runs from 12 hours after the game before (the morning after) to 12 hours after this game, so its
section holds the fallout of the last game and the build-up to this one. Headlines before the first game go
to the first week; those after the last game to a closing section. Nothing here calls CFBD: the schedule and
the rosters come from parts the program already loads.

  topic_of(title)                  "injury" | "recruiting" | "coach" | "weather" | "nfl" | "other-sport" | "practice" | "trophy" | "rankings" | "stadium" | "scoreboard" | "game"
  named_players(title, roster)     [{playerId, name, team}] the roster players the headline names: a full
                                   name, or a last name only one player on these rosters carries
  paper_weeks(headlines, games, team, *, tz, rosters, opponent)  the sections, newest week first
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, tzinfo
from typing import Any

from app.cfbd.models import Game, RosterPlayer

WEEK_EDGE = timedelta(hours=12)

# Topic words, checked in this order (the first that matches wins); whole words, any case.
TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("injury", ("injury", "injuries", "injured", "availability", "questionable", "doubtful", "out for", "surgery", "concussion", "status update", "ruled out")),
    ("recruiting", ("recruit", "recruits", "recruiting", "commit", "commits", "commitment", "decommit", "prospect", "prospects", "visit", "official visit", "flip", "signee", "signing", "4-star", "5-star", "3-star", "transfer portal", "portal", "class of")),
    ("weather", ("weather", "storm", "storms", "rain", "lightning", "heat", "hurricane", "forecast", "cold")),
    ("nfl", ("nfl", "draft", "pro day", "in the nfl")),
    ("other-sport", ("basketball", "baseball", "softball", "volleyball", "soccer", "gymnastics", "track", "swimming", "golf", "tennis", "lacrosse")),
    ("practice", ("practice", "practices", "camp", "scrimmage", "spring game", "depth chart", "lineup", "starters", "starting", "quarterback battle", "bye week")),  # Phase 19
    ("trophy", ("rivalry", "trophy", "championship", "title", "bowl", "playoff", "cfp", "ring")),
    ("rankings", ("poll", "polls", "ranked", "ranking", "rankings", "top 25", "power rankings", "sp+", "elo")),
    ("stadium", ("stadium", "tailgate", "tailgating", "crowd", "attendance", "sellout", "renovation", "gameday atmosphere", "homecoming")),
    ("scoreboard", ("beat", "beats", "defeat", "defeats", "wins", "win over", "loses", "loss", "upset", "rout", "blowout", "final score", "comeback", "survive", "survives")),
    ("coach", ("coach", "coaches", "coaching", "coordinator", "oc", "dc", "head coach", "staff", "press conference", "presser")),
)

# Last names too common as ordinary words to stand for a player on their own.
WORD_NAMES = {"will", "young", "king", "brown", "white", "green", "black", "best", "love", "rich", "early", "strong", "smart", "sharp", "price", "page", "hall", "wells", "rice", "banks", "lane", "long", "short", "west", "north", "south", "east", "hill", "ford", "may", "june", "case", "fields", "cook", "wade", "hunter", "mason", "carter", "walker", "turner", "baker", "porter", "parker"}


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9-]+", " ", text.lower()) + " "


def topic_of(title: Any) -> str:
    if not isinstance(title, str) or not title.strip():
        return "game"
    words = _words(title)
    for topic, terms in TOPICS:
        if any(f" {term} " in words for term in terms):
            return topic
    return "game"


def _full_name(p: RosterPlayer) -> str:
    return " ".join(x for x in (p.first_name, p.last_name) if x)


def named_players(title: Any, rosters: list[tuple[str, list[RosterPlayer]]]) -> list[dict[str, Any]]:
    """The roster players a headline names, ours first. A full name always counts; a last name alone counts
    when only one player on these rosters carries it and it is not an ordinary word."""
    if not isinstance(title, str) or not title.strip():
        return []
    words = _words(title)
    by_last: dict[str, list[tuple[str, RosterPlayer]]] = {}
    for team, players in rosters:
        for p in players:
            if isinstance(p, RosterPlayer) and p.last_name and p.id is not None:
                by_last.setdefault(p.last_name.lower(), []).append((team, p))
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for team, players in rosters:
        for p in players:
            if not isinstance(p, RosterPlayer) or p.id is None or not p.last_name:
                continue
            full = _full_name(p).lower()
            last = p.last_name.lower()
            hit = f" {_words(full).strip()} " in words
            if not hit and len(last) >= 4 and last not in WORD_NAMES and len(by_last.get(last, [])) == 1:
                hit = f" {last} " in words or f" {last}s " in words
            if hit and str(p.id) not in seen:
                seen.add(str(p.id))
                found.append({"playerId": str(p.id), "name": _full_name(p), "team": p.team or team})
    return found[:3]


def _when(iso: Any) -> datetime | None:
    if not isinstance(iso, str) or not iso:
        return None
    try:
        value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else None


def paper_weeks(headlines: list[dict[str, Any]], games: list[Game], team: str, *, tz: tzinfo, rosters: list[tuple[str, list[RosterPlayer]]] | None = None) -> list[dict[str, Any]]:
    """The season's headlines in game-week sections, newest week first; each section names its game."""
    ours = sorted(
        (g for g in games if isinstance(g, Game) and _when(g.start_date) is not None and team in (g.home_team, g.away_team)),
        key=lambda g: _when(g.start_date),
    )
    sections: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    rosters = rosters or []

    def section_for(when: datetime | None) -> dict[str, Any]:
        game = None
        if when is not None:
            game = next((g for g in ours if when <= _when(g.start_date) + WEEK_EDGE), None)
        elif ours:
            game = ours[-1]
        key = str(game.id) if game is not None else "after"
        if key not in sections:
            if game is not None:
                home = game.home_team == team
                opponent = game.away_team if home else game.home_team
                where = "vs" if home or game.neutral_site else "at"
                week = game.week if isinstance(game.week, int) else None
                label = f"{'Bowl season' if (game.season_type or '') == 'postseason' else f'Week {week}' if week is not None else 'This week'} · {where} {opponent or 'TBD'}"
                sections[key] = {"key": key, "gameId": game.id, "week": week, "label": label, "opponent": opponent, "homeAway": "neutral" if game.neutral_site else "home" if home else "away", "kickoff": game.start_date, "headlines": []}
            else:
                sections[key] = {"key": key, "gameId": None, "week": None, "label": "After the season", "opponent": None, "homeAway": None, "kickoff": None, "headlines": []}
            order.append(key)
        return sections[key]

    for h in headlines:
        if not isinstance(h, dict) or not isinstance(h.get("title"), str):
            continue
        row = {**h, "topic": topic_of(h["title"]), "players": named_players(h["title"], rosters)}
        section_for(_when(h.get("publishedAt")))["headlines"].append(row)
    out = [sections[k] for k in order]
    for s in out:
        s["headlines"].sort(key=lambda r: r.get("publishedAt") or "", reverse=True)
    out.sort(key=lambda s: _when(s["kickoff"]) or datetime.max.replace(tzinfo=tz), reverse=True)
    return out
