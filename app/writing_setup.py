"""The data each Claude writing run is given (P4): built from the app's own answers, never a CFBD call of its own beyond
what the pages already cache, and the save that puts the answer where its page reads it. Kept apart from the runner
(app/services/writing.py) so the runner and the readers stay testable without an app.

    review_findings(notes, players, us, them) -> dict      what the notes said against what happened; pure
    await build_job(app, kind, key) -> Job | None          the packet and the save for one run (None: nothing to write about)
    await paper_week(app) -> (key, rows, layout)            this week's paper as the page builds it (FEAT-14 wave 4)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from app.services.notes import NotesFile, compact_notes, load_notes
from app.services.notes_paste import PARTS
from app.services.writing import Job, Lessons, WritingStore

log = logging.getLogger("kickoff.writing")

OUT_STATUSES = ("out", "doubtful")
NO_LINE_SLOTS = re.compile(r"^(lt|lg|c|rg|rt|ol|ls|h|holder|snapper)\b", re.IGNORECASE)  # linemen and the snap: no box line to look for
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv)\.?$", re.IGNORECASE)


def _name(value: Any) -> str:
    text = re.sub(r"[^a-z ]", "", SUFFIX.sub("", str(value or "").lower().replace("-", " "))).strip()
    return " ".join(text.split())


def _played(players: dict[str, Any]) -> set[str]:
    """Every name with a line in one team's box (any category)."""
    names: set[str] = set()
    for rows in (players or {}).values():
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("name"):
                names.add(_name(row["name"]))
    return names


def review_findings(notes: NotesFile | None, players: dict[str, dict[str, Any]], us: str, them: str) -> dict[str, Any]:
    """What the notes said against what the box shows, for the review run: listed out but played, questionable and did not
    play, a starter on the chart with no line (linemen left out: they have none), and the parts that came back empty."""
    found: dict[str, Any] = {"listedOutButPlayed": [], "questionableDidNotPlay": [], "starterWithNoLine": [], "emptyParts": []}
    if notes is None:
        found["emptyParts"] = list(PARTS)
        return found
    played = {team: _played(players.get(team) or {}) for team in (us, them)}
    for row in notes.availability:
        team = row.team if row.team in played else None
        if team is None or not played[team]:
            continue
        status = str(row.status or "").lower()
        on = _name(row.name) in played[team]
        if status in OUT_STATUSES and on:
            found["listedOutButPlayed"].append({"team": team, "name": row.name, "status": row.status})
        elif status == "questionable" and not on:
            found["questionableDidNotPlay"].append({"team": team, "name": row.name})
    for side, team in (("us", us), ("them", them)):
        chart = getattr(notes.lineups, side, None) if notes.lineups else None
        if chart is None or not played.get(team):
            continue
        for slot in chart.slots:
            if NO_LINE_SLOTS.match(slot.slot or "") or not slot.players:
                continue
            starter = slot.players[0]
            if _name(starter.name) not in played[team]:
                found["starterWithNoLine"].append({"team": team, "slot": slot.slot, "name": starter.name})
    data = notes.model_dump(exclude_none=True)
    for part, spec in PARTS.items():
        if not any(data.get(key) for key in spec["keys"]):
            found["emptyParts"].append(part)
    for key in ("listedOutButPlayed", "questionableDidNotPlay", "starterWithNoLine"):
        found[key] = found[key][:25]
    return found


async def _our_game(app: FastAPI, game_id: int) -> Any:
    parts = await app.state.program._core()
    return next((g for g in parts["schedule"].records if g.id == game_id), None)


EDITOR_STORIES = 90  # the week's stories the editor sees, newest first


async def paper_week(app: FastAPI) -> tuple[str | None, list[dict[str, Any]], dict[str, Any]]:
    """(this week's edition key, its stories with what the server copied, the page's layout), as /api/newspaper builds it:
    the same cached parts, so no CFBD call of its own beyond what the page would make."""
    state = app.state
    data, parts = await state.program.newspaper_parts()
    await state.rankedweek.paper(data, parts, 0.0, None)
    edition = data.get("edition") if isinstance(data.get("edition"), dict) else {}
    rows = [r for r in edition.get("headlines") or [] if isinstance(r, dict) and isinstance(r.get("id"), str) and r.get("topic") != "other-sport"]
    built = edition.get("layout") if isinstance(edition.get("layout"), dict) else {}
    return (edition.get("key") if isinstance(edition.get("key"), str) else None), rows, built


def _team_line(block: Any) -> dict[str, Any]:
    d = block if isinstance(block, dict) else {}
    return {k: d.get(k) for k in ("school", "record", "conferenceRecord", "apRank", "cfpRank") if d.get(k) is not None}


async def _article_job(app: FastAPI, kind: str, key: str, store: WritingStore) -> Job | None:
    """Wave 6, second half (owner 2026-11-15): the paper's own article, By the numbers (key "week-N"), on the coming game
    from the program's own figures, both teams side by side with their national ranks. None when there is nothing to write
    from. The answer is checked against the packet (paper_articles.check) and kept in the paper's store as a copied story."""
    from app.services import paper_articles
    from app.services.notes_layout import figures

    state = app.state
    team = state.settings.team
    articles = getattr(state, "articles", None)
    if articles is None or kind != "numbers":
        return None
    result = await state.program.program(None)
    data = result.data if result is not None and isinstance(result.data, dict) else {}
    game = data.get("game") if isinstance(data.get("game"), dict) else None
    from app.services.editions import key_for

    if game is None or game.get("completed") or key != key_for(game.get("week"), game.get("seasonType")):
        return None  # the week moved on, or our game of it is played ("postseason" for a bowl, rollover R1)
    us, them = data.get("us") or {}, data.get("them") or {}
    rows = figures(data.get("profile"), data.get("advanced"), {"us": us.get("school"), "them": them.get("school")})
    if len(rows) < 3:
        return None
    packet: dict[str, Any] = {
        "team": team, "opponent": them.get("school"), "week": game.get("week"), "kickoff": game.get("kickoff"), "venue": game.get("venue"),
        "us": _team_line(us), "them": _team_line(them), "line": data.get("line"),
        "usWinProbability": (data.get("pregame") or {}).get("usWinProbability") if isinstance(data.get("pregame"), dict) else None,
        "figures": [{"metric": r["metric"], "what": r["label"], "side": r.get("side"), **{side: ({"value": r[side]["text"], "nationalRank": r[side]["rank"], "of": r[side]["of"]} if r.get(side) else None) for side in ("us", "them")}} for r in rows],
    }
    title = "By the numbers"

    def keep_article(answer: dict[str, Any]) -> bool:
        changed = paper_articles.keep(articles.store, kind, key, answer)
        store.save(kind, key, answer)  # the answer kept like any writing too (data status, the Prompts page)
        return changed

    return Job(kind, key, team, packet, keep_article, title, check=lambda answer: paper_articles.check(answer, packet))


async def build_job(app: FastAPI, kind: str, key: str) -> Job | None:
    """The run for one kind and key: a game id for review, recap, scout and trivia, a week label for paper, a day for the
    data check, a venue id for trip, the week's key for picks. None when there is nothing to write about (no such game of ours, the game not played yet)."""
    state = app.state
    settings = state.settings
    team = settings.team
    store = WritingStore(settings.data_dir, settings.season)

    def keep(answer: dict[str, Any]) -> bool:
        return store.save(kind, key, answer)

    if kind == "numbers":
        return await _article_job(app, kind, key, store)
    if kind in ("review", "recap", "scout", "trivia"):
        if not str(key).isdigit():
            return None
        game_id = int(key)
        game = await _our_game(app, game_id)
        if game is None:
            return None
        opponent = game.away_team if game.home_team == team else game.home_team
        base = {"gameId": game_id, "home": game.home_team, "away": game.away_team, "opponent": opponent, "kickoff": game.start_date, "week": game.week}
        if kind in ("review", "recap"):
            if not game.completed:
                return None
            box = await state.program.box(game_id)
            final = (box.data.get("final") if box and isinstance(box.data, dict) else None) or {}
            players = {team_name: final.get("players", {}).get(side) or {} for side, team_name in (("home", game.home_team), ("away", game.away_team))}
            notes, _error = load_notes(settings.data_dir, game_id)
            if kind == "review":
                lessons = Lessons(settings.data_dir, settings.season)  # rollover R1: lessons carry their season
                packet = {**base, "score": {game.home_team: game.home_points, game.away_team: game.away_points}, "notes": compact_notes(notes),
                          "whatHappened": review_findings(notes, players, team, opponent or ""), "earlierLessons": lessons.for_prompt()[0]}
                return Job("review", key, team, packet, lambda answer: lessons.add_review(game_id, answer), "The weekly review")
            analytics = await state.analytics.game(game_id)
            wp = (analytics.data.get("winProbability") if analytics and isinstance(analytics.data, dict) else None) or {}
            sides = {name: {k: v for k, v in (final.get(side) or {}).items() if k != "raw"} for side, name in (("home", game.home_team), ("away", game.away_team))}
            packet = {**base, "score": {game.home_team: game.home_points, game.away_team: game.away_points},
                      "byQuarter": {game.home_team: game.home_line_scores, game.away_team: game.away_line_scores}, "box": sides,
                      "biggestSwings": [{k: s.get(k) for k in ("text", "period", "clock", "usWpBefore", "usWpAfter", "change")} for s in (wp.get("swings") or [])[:6] if isinstance(s, dict)],
                      "notesHeadings": [s.heading for s in notes.sections] if notes else []}
            return Job("recap", key, team, packet, keep, "What decided it")
        if kind == "scout":
            line = None
            try:
                from app.services.numbers import season_table, team_line

                fbs = {t.school for t in await state.program.fbs_teams() if isinstance(t.school, str)}
                line = team_line(season_table(state.warm.numbers.games(), fbs or None), opponent or "")
            except Exception:  # noqa: BLE001 - a scouting report without the numbers is still worth writing; logged
                log.exception("The scouting packet could not read the app's numbers")
            season = await state.season.overview(opponent) if opponent else None
            schedule = [{k: g.get(k) for k in ("week", "opponent", "homeAway", "result", "usPoints", "themPoints")} for g in ((season.data.get("schedule") if season else None) or []) if isinstance(g, dict)]
            for row in schedule:
                if isinstance(row.get("opponent"), dict):
                    row["opponent"] = row["opponent"].get("school")
            packet = {**base, "opponentNumbers": line, "opponentSeason": schedule, "opponentRatings": (season.data.get("ratings") if season else None)}
            return Job("scout", key, team, packet, keep, "The scouting report")
        facts = state.season_notes.facts().get("teams", {}) if hasattr(state.season_notes, "facts") else {}
        packet = {**base, "facts": {name: facts.get(name) for name in (game.home_team, game.away_team) if name}}
        return Job("trivia", key, team, packet, keep, "Game-day trivia")
    if kind == "paper":
        data, _parts = await state.rankedweek.week(0)
        games = [{"gameId": g.get("gameId"), "home": (g.get("home") or {}).get("school"), "away": (g.get("away") or {}).get("school"), "homeRank": (g.get("home") or {}).get("rank"), "awayRank": (g.get("away") or {}).get("rank"), "status": g.get("status"), "kickoff": g.get("kickoff")}
                 for g in data.get("games") or [] if isinstance(g, dict)]
        ours = data.get("ourGame") if isinstance(data.get("ourGame"), dict) else None
        packet = {"week": data.get("week"), "label": data.get("label"), "games": games[:30], "ourGame": ours}
        return Job("paper", key, team, packet, keep, "The week's stories and picks")
    if kind == "editor":
        week, rows, _built = await paper_week(app)
        if not week or not rows:
            return None
        coach = (state.season_notes.coaches_for(team) or {}).get("headCoach") if hasattr(state.season_notes, "coaches_for") else None
        stories = [
            {"id": r["id"], "headline": r.get("title"), "source": r.get("source"), "publishedAt": r.get("publishedAt"), "subject": r.get("topic"), "copied": r.get("copied") is True,
             "photo": bool(r.get("photo")), "words": r.get("words") or 0, "firstParagraph": (r.get("opening") or [""])[0][:500] if r.get("opening") else None}
            for r in sorted(rows, key=lambda r: r.get("publishedAt") or "", reverse=True)[:EDITOR_STORIES]
        ]
        ids = [st["id"] for st in stories]
        from app.services.editions import is_sunday

        packet = {"week": week, "team": team, "headCoach": coach, "sunday": is_sunday(week), "stories": stories}  # Wave 6: the Sunday paper's editor knows it

        def keep_layout(answer: dict[str, Any]) -> bool:
            return store.save("editor", week, {**answer, "storyIds": ids, "slot": key})

        return Job("editor", key, team, packet, keep_layout, "The paper laid out")
    if kind == "art":
        from app.services.paper_layout import needs_drawing

        _week, _rows, built = await paper_week(app)
        wanted = needs_drawing(built)
        if not wanted:
            return None
        who = state.identity.current
        packet = {"team": team, "colors": {"primary": getattr(who, "color", None), "secondary": getattr(who, "alt_color", None)},
                  "stories": [{"id": st["id"], "headline": st.get("title"), "subject": st.get("topic"), "firstParagraph": (st.get("opening") or [""])[0][:400] if st.get("opening") else None} for st in wanted]}
        allowed = {st["id"] for st in wanted}

        def keep_drawings(answer: dict[str, Any]) -> bool:
            art = state.rankedweek.art
            drew = [d["storyId"] for d in answer.get("drawings") or [] if isinstance(d, dict) and d.get("storyId") in allowed and art.save(d["storyId"], d.get("svg"), d.get("caption"))]
            store.save("art", key, {"drew": drew, "asked": sorted(allowed)})
            return bool(drew)

        return Job("art", key, team, packet, keep_drawings, "Drawings for the paper")
    if kind == "picks":
        # FEAT-2: every game of the week with an FBS team, from the picks page's own answer (no call of its own)
        from app.services.picks import packet_games, picks_week

        week = await picks_week(state)
        games = packet_games(week)
        if week.get("key") != key or not games:
            return None
        return Job("picks", key, team, {"week": week.get("week"), "label": week.get("label"), "games": games}, keep, "Picks of the week")
    if kind == "trip":
        # ENH-15: one stadium's Getting there sheet, keyed by CFBD's venue id; our next game there, when there is one, for
        # what is different on its day
        if not str(key).isdigit():
            return None
        venue_id = int(key)
        venue = await state.program.venue(venue_id)
        if venue is None:
            return None
        packet: dict[str, Any] = {"venueId": venue_id, "venue": venue.name, "city": venue.city, "state": venue.state, "zip": venue.zip, "latitude": venue.latitude, "longitude": venue.longitude, "capacity": venue.capacity, "dome": venue.dome}
        homes = [t.school for t in await state.program.fbs_teams() if isinstance(t.location, dict) and t.location.get("id") == venue_id and t.school]
        if homes:
            packet["homeOf"] = homes
        upcoming = sorted((g for g in (await state.program._core())["schedule"].records if g.venue_id == venue_id and not g.completed and g.start_date), key=lambda g: g.start_date)
        if upcoming:
            g = upcoming[0]
            packet["game"] = {"home": g.home_team, "away": g.away_team, "kickoff": g.start_date, "neutralSite": bool(g.neutral_site)}
        return Job("trip", key, team, json.loads(json.dumps(packet, default=str)), keep, "Getting there")
    if kind == "datacheck":
        notes = state.season_notes
        coaches = notes.coaches_for(team) if hasattr(notes, "coaches_for") else None
        facts = notes.facts().get("teams", {}).get(team) if hasattr(notes, "facts") else None
        nxt = await state.program.program(None)
        them = nxt.data.get("them", {}).get("school") if nxt and isinstance(nxt.data, dict) and isinstance(nxt.data.get("them"), dict) else None
        packet = {"day": key, "team": team, "ourCoaches": coaches, "ourFacts": facts, "nextOpponent": them,
                  "nextOpponentCoaches": notes.coaches_for(them) if them and hasattr(notes, "coaches_for") else None, "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return Job("datacheck", key, team, json.loads(json.dumps(packet, default=str)), keep, "The weekly data check")
    return None
