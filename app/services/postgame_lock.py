"""The Post-Game Program locked once, when the new AP poll is out (the F8 talk-through, feature 1, owner 2026-10-21:
"pregame, here's what everybody was saying before the game; postgame, here's what everybody said after, so when you look
back you have a history": the Sunday after our game, both teams' ranks of that poll, the records with the game counted,
the conference race and the playoff picture as they stood then, what we need now, the season's numbers with the game
counted, and the news articles about the game, written once to data/season/<year>/postgame/<game_id>.json and never
rewritten, like the kickoff lock (app/services/program_lock.py) and the paper's editions).

    PostgameLock(data_dir, season)
      path(game_id), has(game_id), load(game_id) -> dict | None, save(game_id, snapshot) -> bool (the first lock wins)
    poll_after(weeks, game) -> (week, {poll: {school: rank}})   the polls of the week after the game's; ({} until the AP poll is out)
    as_of(games, week) -> games                                  the season's games with every later game unplayed again
    records_after(games, week) -> {school: {wins, losses, confWins, confLosses}}
    news_for(items, us, them, kickoff) -> [{title, url, source, publishedAt}]   articles about the game, newest first
    snapshot_after(data, now, ...) -> dict                       what the Post-Game Program keeps

A lock made more than BACKFILL_AFTER after the final (this season's games played before the feature, or a server that
was off) is a back-fill: the ranks, the records, the race and the picture are rebuilt as they stood that week from the
cached polls and games, and the news comes from the season's headline archive; the season's numbers of that day are
gone, so the snapshot carries none and the page shows those bands once."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.cfbd.models import Game
from app.feeds import TeamMatcher
from app.services import gamekeys
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.postgame")

FORMAT = 1
BACKFILL_AFTER = timedelta(days=3)
NEWS_WINDOW = timedelta(days=4)
NEWS_LIMIT = 8
POLL_NAMES = {"AP Top 25": "AP", "Coaches Poll": "Coaches", "Playoff Committee Rankings": "CFP"}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def poll_after(weeks: list[Any], game: Game) -> tuple[int | None, dict[str, dict[str, int]]]:
    """The polls of the first week after the game's week (the AP poll released the Sunday after a regular-season game;
    the final poll after a postseason game). (None, {}) until that poll exists."""
    if not isinstance(game.week, int):
        return None, {}
    season_type = game.season_type or "regular"
    if season_type == gamekeys.POSTSEASON:
        pool = [w for w in weeks if (getattr(w, "season_type", None) or "regular") == gamekeys.POSTSEASON and isinstance(getattr(w, "week", None), int)]
        week = max(pool, key=gamekeys.poll_order) if pool else None
    else:
        week = next((w for w in weeks if getattr(w, "week", None) == game.week + 1 and (getattr(w, "season_type", None) or "regular") == "regular"), None)
    if week is None:
        return None, {}
    out: dict[str, dict[str, int]] = {}
    for poll in getattr(week, "polls", None) or []:
        short = POLL_NAMES.get(getattr(poll, "poll", None))
        if not short:
            continue
        out[short] = {r.school: r.rank for r in (getattr(poll, "ranks", None) or []) if isinstance(getattr(r, "rank", None), int) and getattr(r, "school", None)}
    return week.week, out


def as_of(games: list[Game], week: int) -> list[Game]:
    """The season's games as they stood after `week`: every later game unplayed again, so the race and the records of
    that week can be told from today's list."""
    out: list[Game] = []
    for g in games:
        if not isinstance(g, Game):
            continue
        later = (g.season_type or "regular") == gamekeys.POSTSEASON or (isinstance(g.week, int) and g.week > week)
        if later and g.completed:
            out.append(g.model_copy(update={"completed": False, "home_points": None, "away_points": None, "home_line_scores": None, "away_line_scores": None}))
        else:
            out.append(g)
    return out


def records_after(games: list[Game], week: int) -> dict[str, dict[str, int]]:
    """Every team's record through `week` from the games: overall and conference wins and losses."""
    out: dict[str, dict[str, int]] = {}
    for g in games:
        if not isinstance(g, Game) or not g.completed or not isinstance(g.week, int) or g.week > week or (g.season_type or "regular") == gamekeys.POSTSEASON:
            continue
        if not isinstance(g.home_points, int) or not isinstance(g.away_points, int) or g.home_points == g.away_points:
            continue
        for school, pts, opp in ((g.home_team, g.home_points, g.away_points), (g.away_team, g.away_points, g.home_points)):
            if not school:
                continue
            line = out.setdefault(school, {"wins": 0, "losses": 0, "confWins": 0, "confLosses": 0})
            won = pts > opp
            line["wins" if won else "losses"] += 1
            if g.conference_game:
                line["confWins" if won else "confLosses"] += 1
    return out


def news_for(items: list[dict[str, Any]], us: TeamMatcher, them: TeamMatcher | None, kickoff: datetime | None, limit: int = NEWS_LIMIT) -> list[dict[str, Any]]:
    """The articles about the game: a headline naming either team, published from kickoff to NEWS_WINDOW after it, newest
    first, duplicates by title dropped. Without a kickoff, nothing (a date is what makes it about this game)."""
    if kickoff is None:
        return []
    end = kickoff + NEWS_WINDOW
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        published = _parse(item.get("publishedAt"))
        if not isinstance(title, str) or not title.strip() or published is None or not (kickoff <= published <= end):
            continue
        if not (us.matches(title) or (them is not None and them.matches(title))):
            continue
        key = " ".join(title.lower().split())[:80]
        if key in seen:
            continue
        seen.add(key)
        kept.append({"title": title.strip(), "url": item.get("url") if isinstance(item.get("url"), str) else None, "source": item.get("source") if isinstance(item.get("source"), str) else None, "publishedAt": _iso(published)})
    kept.sort(key=lambda h: h["publishedAt"], reverse=True)
    return kept[:limit]


def _team(block: Any, ranks: dict[str, dict[str, int]], records: dict[str, dict[str, int]]) -> dict[str, Any]:
    d = block if isinstance(block, dict) else {}
    school = d.get("school") if isinstance(d.get("school"), str) else None
    rec = records.get(school or "")
    return {
        "school": school,
        "abbreviation": d.get("abbreviation"),
        "mascot": d.get("mascot"),
        "apRank": ranks.get("AP", {}).get(school or ""),
        "cfpRank": ranks.get("CFP", {}).get(school or ""),
        "record": {"wins": rec["wins"], "losses": rec["losses"]} if rec else None,
        "conferenceRecord": {"wins": rec["confWins"], "losses": rec["confLosses"]} if rec else None,
    }


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in (value if isinstance(value, list) else []) if isinstance(row, dict)]


def snapshot_after(
    data: Any,
    now: datetime,
    *,
    poll_week: int | None,
    ranks: dict[str, dict[str, int]],
    records: dict[str, dict[str, int]],
    race: dict[str, Any] | None,
    picture: dict[str, Any] | None,
    news: list[dict[str, Any]],
    backfilled: bool,
) -> dict[str, Any]:
    """What the Post-Game Program keeps: both teams as the poll after the game had them, the final, the race and the
    picture as they stood, the news, the season's numbers with the game counted (not for a back-fill), and the program's
    whole answer as it stood, so every band can be drawn beside its kickoff twin."""
    d = data if isinstance(data, dict) else {}
    game = d.get("game") if isinstance(d.get("game"), dict) else {}
    profile = d.get("profile") if isinstance(d.get("profile"), dict) else {}
    program = {k: v for k, v in d.items() if k not in ("parts", "picker")}
    program["race"] = race
    program["picture"] = picture
    for side in ("us", "them"):
        block = program.get(side)
        if isinstance(block, dict):
            after = _team(block, ranks, records)
            program[side] = {**block, "apRank": after["apRank"], "cfpRank": after["cfpRank"], "record": after["record"] or block.get("record"), "conferenceRecord": after["conferenceRecord"] or block.get("conferenceRecord")}
    return {
        "format": FORMAT,
        "lockedAt": _iso(now),
        "backfilled": backfilled,
        "gameId": game.get("gameId"),
        "week": game.get("week"),
        "pollWeek": poll_week,
        "kickoff": game.get("kickoff"),
        "homeIsUs": game.get("homeIsUs"),
        "final": {"usPoints": game.get("usPoints"), "themPoints": game.get("themPoints")},
        "us": _team(d.get("us"), ranks, records),
        "them": _team(d.get("them"), ranks, records),
        "race": race,
        "picture": picture,
        "news": news,
        "profile": None if backfilled else {"us": _rows(profile.get("us")), "them": _rows(profile.get("them"))},
        "program": program,
    }


class PostgameLock:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(season) / "postgame"

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
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("The Post-Game lock for game %s could not be read: %s", game_id, exc)
            return None
        if not isinstance(raw, dict) or raw.get("gameId") != int(game_id):
            log.warning("The Post-Game lock for game %s is not a lock; ignored", game_id)
            return None
        return raw

    def save(self, game_id: int, snapshot: dict[str, Any]) -> bool:
        """Write once. False when a lock is there already: the first lock wins."""
        path = self.path(game_id)
        if path.exists():
            return False
        try:
            atomic_write(path, json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.error("The Post-Game lock for game %s could not be written: %s", game_id, exc)
            return False
        log.info("Post-Game Program locked for game %s (poll week %s%s)", game_id, snapshot.get("pollWeek"), ", back-filled" if snapshot.get("backfilled") else "")
        return True
