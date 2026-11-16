"""The newspaper's weeks (Phase 17 #26): the season's headlines grouped by game week, each with a topic for its
picture and the players it names (their headshots; FEAT-14 retired the pixel art).

Each of our games has two papers (the season line's Wave 6; owner 2026-11-15: "a kind of sunday paper and including only
the articles about the loss, then monday everything is about the new week up until kickoff"; his picks: from the final
to 6 AM Monday, every week, win or lose). The week's paper runs from the end of the last game's Sunday paper to this
game's final; the Sunday paper from the final to 6 AM on the second morning after kickoff (Monday for a Saturday game)
and holds only the stories about the game (`about_game`): a story in that window about anything else goes to the next
week's paper. The final is taken as kickoff + FINAL_AFTER (the app keeps no final time for the season's games). Headlines
before the first game go to the first week; those after the last game's Sunday paper to a closing section; a bye week
has no Sunday paper of its own. Nothing here calls CFBD: the schedule and the rosters come from parts the program
already loads.

  topic_of(title)                  "injury" | "recruiting" | "coach" | "weather" | "nfl" | "other-sport" | "practice" | "trophy" | "rankings" | "stadium" | "scoreboard" | "game"
  named_players(title, roster)     [{playerId, name, team}] the roster players the headline names: a full
                                   name, or a last name only one player on these rosters carries
  final_of(kickoff) / sunday_end(kickoff, tz)   a game's taken final and the end of its Sunday paper
  about_game(row, opponent)        a headline is about the game just played
  paper_weeks(headlines, games, team, *, tz, rosters)  the sections, newest first: a game's Sunday paper over its week's
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, tzinfo
from typing import Any

from app.cfbd.models import Game, RosterPlayer

FINAL_AFTER = timedelta(hours=3, minutes=30)  # kickoff to the final, for a game the app did not watch
SUNDAY_ENDS_AT = time(6, 0)  # the Sunday paper gives way at 6 AM on the second morning after kickoff
ABOUT_TOPICS = ("game", "scoreboard", "coach", "injury")  # a Sunday story on these is about the game

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


_NAME_INDEX: dict[tuple[Any, ...], tuple[list[Any], list[tuple[str, RosterPlayer, str, str, str, list[str], bool]]]] = {}


def _name_index(rosters: list[tuple[str, list[RosterPlayer]]]) -> list[tuple[str, RosterPlayer, str, str, str, list[str], bool]]:
    """Each roster player once, with what the headline test needs worked out ahead (batch 1, 2026-11-15: the paper spent most
    of its 557 ms reworking every player's name for each of the season's 1,812 headlines, on every read). Kept per roster
    list (the parts memo keeps the parsed lists), at most a few."""
    key = tuple((team, id(players), len(players)) for team, players in rosters)
    kept = _NAME_INDEX.get(key)
    lists = [players for _team, players in rosters]
    if kept is not None and len(kept[0]) == len(lists) and all(a is b for a, b in zip(kept[0], lists, strict=True)):
        return kept[1]  # the very lists (the review, 2026-11-16: an id alone can be a freed list's, reused); kept, so never freed
    by_last: dict[str, int] = {}
    for _team, players in rosters:
        for p in players:
            if isinstance(p, RosterPlayer) and p.last_name and p.id is not None:
                by_last[p.last_name.lower()] = by_last.get(p.last_name.lower(), 0) + 1
    rows = []
    for team, players in rosters:
        for p in players:
            if not isinstance(p, RosterPlayer) or p.id is None or not p.last_name:
                continue
            full = _full_name(p)
            last = p.last_name.lower()
            alone = len(last) >= 4 and last not in WORD_NAMES and by_last.get(last, 0) == 1
            rows.append((team, p, full, f" {_words(full.lower()).strip()} ", last, _words(last).split(), alone))
    if len(_NAME_INDEX) >= 8:
        _NAME_INDEX.clear()
    _NAME_INDEX[key] = (lists, rows)
    return rows


def named_players(title: Any, rosters: list[tuple[str, list[RosterPlayer]]]) -> list[dict[str, Any]]:
    """The roster players a headline names, ours first. A full name always counts; a last name alone counts
    when only one player on these rosters carries it and it is not an ordinary word."""
    if not isinstance(title, str) or not title.strip():
        return []
    words = _words(title)
    tokens = set(words.split())
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for team, p, full, phrase, last, last_words, alone in _name_index(rosters):
        plural = bool(last_words) and all(w in tokens for w in last_words[:-1]) and f"{last_words[-1]}s" in tokens  # "Van Dykes"
        if not (all(w in tokens for w in last_words) or f"{last}s" in tokens or plural):
            continue  # neither the full name nor the last name can be in a title that lacks the last name's words
        hit = phrase in words
        if not hit and alone:
            hit = f" {last} " in words or f" {last}s " in words
        if hit and str(p.id) not in seen:
            seen.add(str(p.id))
            found.append({"playerId": str(p.id), "name": full, "team": p.team or team})
    return found[:3]


def _when(iso: Any) -> datetime | None:
    if not isinstance(iso, str) or not iso:
        return None
    try:
        value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else None


def final_of(kickoff: datetime) -> datetime:
    return kickoff + FINAL_AFTER


def game_week_start(when: datetime, tz: tzinfo) -> datetime:
    """Monday 6 AM of the week holding `when`, in the server's time zone: where a game week's paper starts (rollover R3: the
    opener's week starts Week 1's paper; the off-season paper turns over at this hour every Monday)."""
    local = when.astimezone(tz)
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday, SUNDAY_ENDS_AT, tzinfo=tz)


def sunday_end(kickoff: datetime, tz: tzinfo) -> datetime:
    """6 AM on the second morning after kickoff, in the server's time zone: Monday for a Saturday game (a late kickoff
    that ends after midnight too), Saturday for a Thursday one."""
    local = kickoff.astimezone(tz)
    return datetime.combine(local.date() + timedelta(days=2), SUNDAY_ENDS_AT, tzinfo=tz)


def about_game(row: dict[str, Any], opponent: str | None) -> bool:
    """A Sunday headline that is about the game just played: on the game, its score, the coach or the injuries, naming
    one of the rosters' players, or naming the opponent."""
    if row.get("topic") in ABOUT_TOPICS or row.get("players"):
        return True
    title = row.get("title") if isinstance(row.get("title"), str) else ""
    return bool(opponent) and f" {_words(opponent).strip()} " in _words(title)


def sunday_stories(headlines: Any, kickoff: datetime | None, opponent: str | None, tz: tzinfo) -> list[dict[str, Any]]:
    """One game's Sunday paper by the same rule as paper_weeks (no rosters at hand, so a player named alone does not
    count): the headlines published from its taken final to its 6 AM end that are about the game. The Post-Game's
    "The game in the news" reads these (Wave 6)."""
    if kickoff is None:
        return []
    start, end = final_of(kickoff), sunday_end(kickoff, tz)
    out = []
    for h in headlines if isinstance(headlines, list) else []:
        if not isinstance(h, dict) or not isinstance(h.get("title"), str):
            continue
        when = _when(h.get("publishedAt"))
        if when is not None and start < when <= end and about_game({**h, "topic": topic_of(h["title"])}, opponent):
            out.append(h)
    return out


def paper_weeks(headlines: list[dict[str, Any]], games: list[Game], team: str, *, tz: tzinfo, rosters: list[tuple[str, list[RosterPlayer]]] | None = None) -> list[dict[str, Any]]:
    """The season's headlines in sections, newest first: each game's week paper, and its Sunday paper once a headline
    falls in it (`sunday` True, `from` the taken final, `until` its 6 AM end). Each section names its game."""
    ours = sorted(
        (g for g in games if isinstance(g, Game) and _when(g.start_date) is not None and team in (g.home_team, g.away_team)),
        key=lambda g: _when(g.start_date),
    )
    sections: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    rosters = rosters or []

    def opponent_of(game: Game) -> str | None:
        return game.away_team if game.home_team == team else game.home_team

    def section(game: Game | None, sunday: bool = False, before: bool = False) -> dict[str, Any]:
        key = ("before" if before else "after") if game is None else f"{game.id}-sunday" if sunday else str(game.id)
        if key not in sections:
            if game is not None:
                home = game.home_team == team
                opponent = opponent_of(game)
                where = "vs" if home or game.neutral_site else "at"
                week = game.week if isinstance(game.week, int) else None
                name = "Bowl season" if (game.season_type or "") == "postseason" else f"Week {week}" if week is not None else "This week"
                label = f"{name}{' · Sunday paper' if sunday else ''} · {where} {opponent or 'TBD'}"
                kickoff = _when(game.start_date)
                sections[key] = {"key": key, "gameId": game.id, "week": week, "label": label, "opponent": opponent, "homeAway": "neutral" if game.neutral_site else "home" if home else "away", "kickoff": game.start_date, "sunday": sunday, "headlines": []}
                if sunday and kickoff is not None:
                    sections[key]["from"] = final_of(kickoff).isoformat()
                    sections[key]["until"] = sunday_end(kickoff, tz).isoformat()
            else:
                sections[key] = {"key": key, "gameId": None, "week": None, "label": "Before the season" if before else "After the season", "opponent": None, "homeAway": None, "kickoff": None, "sunday": False, "headlines": []}
            order.append(key)
        return sections[key]

    def section_for(row: dict[str, Any], when: datetime | None) -> dict[str, Any]:
        if when is None:
            return section(ours[-1] if ours else None)
        for i, game in enumerate(ours):
            kickoff = _when(game.start_date)
            if i == 0 and when < game_week_start(kickoff, tz):
                return section(None, before=True)  # rollover R3: before the opener's week, the off-season paper's, not Week 1's
            if when <= final_of(kickoff):
                return section(game)
            if when <= sunday_end(kickoff, tz):
                if about_game(row, opponent_of(game)):
                    return section(game, sunday=True)
                return section(ours[i + 1] if i + 1 < len(ours) else None)  # the new week's, or after the season
        return section(None)

    for h in headlines:
        if not isinstance(h, dict) or not isinstance(h.get("title"), str):
            continue
        row = {**h, "topic": topic_of(h["title"]), "players": named_players(h["title"], rosters)}
        section_for(row, _when(h.get("publishedAt")))["headlines"].append(row)
    out = [sections[k] for k in order]
    for s in out:
        s["headlines"].sort(key=lambda r: r.get("publishedAt") or "", reverse=True)
    # newest first; a game's Sunday paper over its week's paper
    out.sort(key=lambda s: (_when(s["kickoff"]) or datetime.max.replace(tzinfo=tz), s.get("sunday") is True), reverse=True)
    return out
