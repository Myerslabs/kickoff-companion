"""Phase 16 stream BX: context the page streams draw, built only from payloads the services already
hold. No calls here: the functions shape parsed records, and the `*_extras` helpers attach the new
fields to an assembled answer in place (one call-site line per service). The one reader, `peek`,
looks a key up in the local cache and never reaches CFBD or the quota guard.

Every input is untrusted: a missing or wrongly typed value is skipped (and counted where a table
reports its coverage) or shown as None, never raised, and no float leaves here unless it is finite.

- GX-17 form guide: each team's last five results from the all-FBS /games answer.
- GX-06 rank paths: previous rank, movement and the AP path by week for every poll row (/rankings
  holds every week), and an Elo path per team from the pregame and postgame Elo on /games.
- GX-08 season strip: the opponent's SP+ rank and a win chance per schedule row (CFBD's postgame
  win expectancy once played; before that the standard Elo expectation, flagged as an estimate).
- GX-15 throw and run tables: pass zones (short or deep by left, middle, right) and run lanes from
  the opponent's /passing/plays and /rushing/plays.
- GX-19 venue facts: elevation, year built, and the record at the venue in the series.
- UX-14 radar: the National Weather Service page for the venue's coordinates.
- GX-20 where they're from: a recruiting class by state with the in-state share.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from typing import Any

from app.cache import cache_key
from app.cfbd.models import Game, Matchup, PassingPlay, PollWeek, Recruit, RushingPlay, Team, TeamElo, TeamSP, Venue, parse_records
from app.services import gamekeys

log = logging.getLogger("kickoff.context16")

FORM_LENGTH = 5
POLL_NAMES = {"AP Top 25": "AP", "Coaches Poll": "Coaches", "Playoff Committee Rankings": "CFP"}
METERS_TO_FEET = 3.28084
LANES = (("left", "Left"), ("middle", "Middle"), ("right", "Right"))
DEPTHS = (("deep", "Deep"), ("short", "Short"))  # the deep row sits over the short row, like the field


# --- guards -----------------------------------------------------------------------------------------


def num(value: Any) -> float | None:
    """A finite number, or None (bools, strings, NaN and infinity are not numbers here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _r(value: Any, digits: int = 3) -> float | None:
    number = num(value)
    return round(number, digits) if number is not None else None


def _records(part: Any) -> list[Any]:
    """The records of a Part, or [] when the part is missing."""
    records = getattr(part, "records", None)
    return list(records) if isinstance(records, list) else []


async def peek(client: Any, endpoint: str, params: dict[str, Any]) -> Any:
    """The payload another page already cached for (endpoint, params), or None. Reads the local cache
    only: never a CFBD call, so it needs no quota check and costs nothing on a cold cache."""
    cache = getattr(client, "cache", None)
    if cache is None:
        return None
    try:
        entry = await asyncio.to_thread(cache.get, cache_key(endpoint, params))
    except Exception as exc:  # noqa: BLE001 - a broken cache read only drops the extra field; it is logged
        log.warning("Cache peek of %s failed: %s", endpoint, exc)
        return None
    return entry.payload if entry is not None else None


# --- GX-17 form guide ---------------------------------------------------------------------------------


def form_table(games: list[Game], limit: int = FORM_LENGTH) -> dict[str, list[dict[str, Any]]]:
    """{team: last `limit` results, newest last} from every finished game with both scores. A game
    listed twice (the all-FBS list plus a team's own schedule) counts once."""
    seen: set[int] = set()
    finished: list[Game] = []
    for g in games:
        if not isinstance(g, Game) or not g.completed or g.id in seen:
            continue
        if whole(g.home_points) is None or whole(g.away_points) is None or not text(g.home_team) or not text(g.away_team):
            continue
        seen.add(g.id)
        finished.append(g)
    table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in sorted(finished, key=gamekeys.order):
        for team, opponent, points, allowed, side in ((g.home_team, g.away_team, g.home_points, g.away_points, "home"), (g.away_team, g.home_team, g.away_points, g.home_points, "away")):
            table[team].append({
                "gameId": g.id,
                "week": whole(g.week),
                "postseason": gamekeys.label(g),
                "result": "W" if points > allowed else "L" if points < allowed else "T",
                "points": points,
                "opponentPoints": allowed,
                "opponent": opponent,
                "homeAway": "neutral" if g.neutral_site else side,
            })
    return {team: rows[-limit:] for team, rows in table.items()}


def form_for(table: dict[str, list[dict[str, Any]]], team: Any) -> list[dict[str, Any]]:
    return list(table.get(team, [])) if isinstance(team, str) else []


# --- GX-06 rank paths -----------------------------------------------------------------------------------


def poll_history(weeks: list[PollWeek]) -> dict[str, list[tuple[dict[str, Any], dict[str, int]]]]:
    """{poll short name: [({week, seasonType}, {school: rank}), ...]} in time order (the postseason's
    final poll last). A week appears for a poll only when that poll was published that week."""
    ordered = sorted((w for w in weeks if isinstance(w, PollWeek) and whole(w.week) is not None), key=gamekeys.poll_order)
    out: dict[str, list[tuple[dict[str, Any], dict[str, int]]]] = defaultdict(list)
    for week in ordered:
        key = {"week": week.week, "seasonType": week.season_type or "regular"}
        for poll in week.polls:
            short = POLL_NAMES.get(poll.poll)
            if short is None:
                continue
            ranks = {r.school: r.rank for r in poll.ranks if text(r.school) and whole(r.rank) is not None and r.rank > 0}
            series = out[short]
            if series and series[-1][0] == key:
                series[-1][1].update(ranks)  # the same poll twice in one week: merge
            else:
                series.append((key, ranks))
    return dict(out)


def movement(previous: int | None, current: int | None, had_previous_week: bool) -> tuple[int | None, str | None]:
    """(change, text): change > 0 moved up. 'new' when unranked the week before, None when there was no week before."""
    if not had_previous_week or current is None:
        return None, None
    if previous is None:
        return None, "new"
    change = previous - current
    return change, (f"{change:+d}" if change else "0")


def attach_poll_paths(blocks: Any, weeks: list[PollWeek]) -> None:
    """Season polls blocks gain pathWeeks and previousWeek; each row gains previousRank, change,
    movement ('+3', '-2', '0', 'new') and apPath (the AP rank per pathWeeks entry, None when unranked)."""
    if not isinstance(blocks, list):
        return
    history = poll_history(weeks)
    ap = history.get("AP", [])
    path_weeks = [dict(key) for key, _ in ap]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        series = history.get(block.get("poll") or "", [])
        at = max((i for i, (key, _) in enumerate(series) if key["week"] == block.get("week")), default=len(series) - 1)
        previous = series[at - 1] if at >= 1 else None
        block["pathWeeks"] = path_weeks
        block["previousWeek"] = dict(previous[0]) if previous else None
        for row in block.get("ranks") or []:
            if not isinstance(row, dict):
                continue
            school = row.get("school")
            prev = previous[1].get(school) if previous and isinstance(school, str) else None
            change, label = movement(prev, whole(row.get("rank")), previous is not None)
            row["previousRank"] = prev
            row["change"] = change
            row["movement"] = label
            row["apPath"] = [ranks.get(school) if isinstance(school, str) else None for _, ranks in ap]


def elo_path(games: list[Game], team: Any) -> dict[str, Any] | None:
    """A team's Elo through the season from /games: one point per finished game (pregame and postgame
    Elo), and `current`, the latest postgame Elo (or the next game's pregame Elo before any game)."""
    if not isinstance(team, str) or not team:
        return None
    seen: set[int] = set()
    points: list[dict[str, Any]] = []
    upcoming: int | None = None
    for g in sorted((g for g in games if isinstance(g, Game) and team in (g.home_team, g.away_team)), key=gamekeys.order):
        if g.id in seen:
            continue
        seen.add(g.id)
        home = g.home_team == team
        pre = whole(g.home_pregame_elo if home else g.away_pregame_elo)
        post = whole(g.home_postgame_elo if home else g.away_postgame_elo)
        if g.completed and post is not None:
            points.append({"gameId": g.id, "week": whole(g.week), "postseason": gamekeys.label(g), "opponent": g.away_team if home else g.home_team, "pre": pre, "post": post})
        elif not g.completed and upcoming is None and pre is not None:
            upcoming = pre
    if not points and upcoming is None:
        return None
    return {"current": points[-1]["post"] if points else upcoming, "points": points}


# --- GX-08 season strip --------------------------------------------------------------------------------------


def elo_expectation(us: float | None, them: float | None) -> float | None:
    """The standard Elo expectation 1 / (1 + 10^((them - us) / 400)), without a home-field term."""
    if us is None or them is None:
        return None
    return round(1.0 / (1.0 + 10 ** ((them - us) / 400.0)), 3)


def strip_fields(game: Game, team: str, sp_ranks: dict[str, dict[str, Any]], elo_now: dict[str, float]) -> dict[str, Any]:
    """opponentSp {rank, rating} and winPct {value, estimate, source} for one of our games."""
    home = game.home_team == team
    opponent = game.away_team if home else game.home_team
    win: dict[str, Any] | None = None
    if game.completed:
        value = num(game.home_postgame_win_probability if home else game.away_postgame_win_probability)
        if value is not None and 0 <= value <= 1:
            win = {"value": round(value, 3), "estimate": False, "source": "postgame"}
    else:
        us = num(game.home_pregame_elo if home else game.away_pregame_elo)
        them = num(game.away_pregame_elo if home else game.home_pregame_elo)
        source = "pregame Elo"
        if us is None or them is None:
            us, them, source = elo_now.get(team), elo_now.get(opponent or ""), "current Elo"
        value = elo_expectation(us, them)
        if value is not None:
            win = {"value": value, "estimate": True, "source": source}
    return {"opponentSp": sp_ranks.get(opponent or ""), "winPct": win}


def sp_rank_lookup(sp: list[TeamSP]) -> dict[str, dict[str, Any]]:
    return {r.team: {"rank": whole(r.ranking), "rating": _r(r.rating, 1)} for r in sp if isinstance(r, TeamSP) and r.team and (whole(r.ranking) is not None or num(r.rating) is not None)}


def attach_strip(rows: Any, schedule: list[Game], team: str, sp: list[TeamSP], elo: list[TeamElo]) -> None:
    if not isinstance(rows, list):
        return
    by_id = {g.id: g for g in schedule if isinstance(g, Game)}
    sp_ranks = sp_rank_lookup(sp)
    elo_now = {r.team: v for r in elo if isinstance(r, TeamElo) and r.team and (v := num(r.elo)) is not None}
    for row in rows:
        if not isinstance(row, dict):
            continue
        game = by_id.get(row.get("gameId"))
        row.update(strip_fields(game, team, sp_ranks, elo_now) if game is not None else {"opponentSp": None, "winPct": None})


# --- GX-15 throw and run tables ------------------------------------------------------------------------------


def throw_run_tables(rushes: list[RushingPlay], passes: list[PassingPlay], team: Any) -> dict[str, Any]:
    """Pass zones (deep and short by left, middle, right: attempts, completions, completion rate and
    success) and run lanes (left, middle, right: carries, yards per carry, success) for `team` on
    offense. CFBD's passDepth and passDirection make the zone (its passLocation is the same pair as
    text); spikes, kneels and sacks are left out; plays without a zone or lane are counted as unplaced."""
    zones = {(d, lane): {"attempts": 0, "completions": 0, "made": 0, "judged": 0} for d, _ in DEPTHS for lane, _ in LANES}
    lanes = {lane: {"carries": 0, "yards": 0, "yardsCounted": 0, "made": 0, "judged": 0} for lane, _ in LANES}
    unplaced_passes = unplaced_runs = 0
    for p in passes:
        if not isinstance(p, PassingPlay) or p.offense != team or p.is_spike:
            continue
        depth, lane = str(p.pass_depth or "").strip().lower(), str(p.pass_direction or "").strip().lower()
        cell = zones.get((depth, lane))
        if cell is None:
            unplaced_passes += 1
            continue
        cell["attempts"] += 1
        cell["completions"] += 1 if str(p.outcome or "").strip().lower() == "completion" else 0
        if isinstance(p.success, bool):
            cell["judged"] += 1
            cell["made"] += p.success
    for r in rushes:
        if not isinstance(r, RushingPlay) or r.offense != team or r.is_kneel or r.is_sack:
            continue
        cell = lanes.get(str(r.rush_direction or "").strip().lower())
        if cell is None:
            unplaced_runs += 1
            continue
        cell["carries"] += 1
        yards = whole(r.rushing_yards)
        if yards is not None:
            cell["yards"] += yards
            cell["yardsCounted"] += 1
        if isinstance(r.success, bool):
            cell["judged"] += 1
            cell["made"] += r.success

    def rate(a: int, b: int, digits: int = 3) -> float | None:
        return round(a / b, digits) if b else None

    pass_zones = []
    for depth, depth_label in DEPTHS:
        for lane, lane_label in LANES:
            c = zones[(depth, lane)]
            pass_zones.append({"key": f"{depth}_{lane}", "depth": depth, "direction": lane, "label": f"{depth_label} {lane_label.lower()}", "attempts": c["attempts"], "completions": c["completions"], "completionPct": rate(c["completions"], c["attempts"]), "success": {"made": c["made"], "of": c["judged"]}, "successRate": rate(c["made"], c["judged"])})
    run_lanes = []
    for lane, label in LANES:
        c = lanes[lane]
        run_lanes.append({"key": lane, "label": label, "carries": c["carries"], "yardsPerCarry": rate(c["yards"], c["yardsCounted"], 1), "success": {"made": c["made"], "of": c["judged"]}, "successRate": rate(c["made"], c["judged"])})
    return {"passZones": pass_zones, "runLanes": run_lanes, "unplacedPasses": unplaced_passes, "unplacedRuns": unplaced_runs}


# --- GX-19 venue facts and UX-14 radar ------------------------------------------------------------------------


def radar_url(venue: Any) -> str | None:
    """The National Weather Service forecast page for the venue's point (it carries the local radar),
    or None without usable coordinates or for a venue outside the United States."""
    if not isinstance(venue, Venue):
        return None
    lat, lon = num(venue.latitude), num(venue.longitude)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    country = text(venue.country_code)
    if country is not None and country.upper() != "US":
        return None
    return f"https://forecast.weather.gov/MapClick.php?lat={lat:.4f}&lon={lon:.4f}"


def elevation_m(value: Any) -> float | None:
    """CFBD sends elevation as a string of meters (recorded venues: Folsom Field 1634, Ben Hill
    Griffin 45, War Memorial in Laramie 2200)."""
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    number = num(value)
    return round(number, 1) if number is not None and -500 < number < 6000 else None


def record_at_venue(series: list[Matchup], team: str, venue_name: Any) -> dict[str, Any] | None:
    """The team's record in the series games played at this venue (by name). CFBD leaves the venue
    empty on many older series games; those are counted in `gamesWithoutVenue`."""
    name = text(venue_name)
    matchup = next((m for m in series if isinstance(m, Matchup)), None)
    if name is None or matchup is None:
        return None
    wins = losses = ties = unknown = 0
    for g in matchup.games:
        where = text(g.venue)
        if where is None:
            unknown += 1
            continue
        if where.casefold() != name.casefold():
            continue
        if g.winner == team:
            wins += 1
        elif text(g.winner):
            losses += 1
        elif whole(g.home_score) is not None and g.home_score == g.away_score:
            ties += 1
    opponent = matchup.team2 if matchup.team1 == team else matchup.team1
    return {"venue": name, "opponent": opponent, "wins": wins, "losses": losses, "ties": ties, "games": wins + losses + ties, "gamesWithoutVenue": unknown}


def venue_facts(venue: Any, series: list[Matchup], team: str, venue_name: Any) -> dict[str, Any]:
    meters = elevation_m(venue.elevation) if isinstance(venue, Venue) else None
    built = whole(venue.construction_year) if isinstance(venue, Venue) else None
    return {
        "elevationM": meters,
        "elevationFt": round(meters * METERS_TO_FEET) if meters is not None else None,
        "yearBuilt": built if built is not None and 1800 < built < 2100 else None,
        "recordAtVenue": record_at_venue(series, team, venue_name),
    }


# --- GX-20 where they're from ------------------------------------------------------------------------------------


def where_from(recruits: list[Recruit], team: str, home_state: str | None) -> dict[str, Any]:
    """A class by state: commits, average rating, 5/4/3-star counts, most commits first; plus the
    in-state share (commits from `home_state` over all commits). Signees of other schools are left out,
    as on the class list; a commit without a state is counted in `unknownState`."""
    states: dict[str, dict[str, Any]] = {}
    total = unknown = 0
    for r in recruits:
        if not isinstance(r, Recruit) or (r.committed_to and r.committed_to != team):
            continue
        total += 1
        state = text(r.state_province)
        if state is None:
            unknown += 1
            continue
        row = states.setdefault(state.upper(), {"state": state.upper(), "commits": 0, "ratings": [], "stars": {"5": 0, "4": 0, "3": 0}})
        row["commits"] += 1
        rating = num(r.rating)
        if rating is not None and 0 <= rating <= 1.5:
            row["ratings"].append(rating)
        stars = whole(r.stars)
        if stars is not None and str(stars) in row["stars"]:
            row["stars"][str(stars)] += 1
    table = []
    for row in states.values():
        ratings = row.pop("ratings")
        table.append({**row, "averageRating": round(sum(ratings) / len(ratings), 4) if ratings else None})
    table.sort(key=lambda r: (-r["commits"], r["state"]))
    home = text(home_state)
    in_state = None
    if home is not None and total:
        count = next((r["commits"] for r in table if r["state"] == home.upper()), 0)
        in_state = {"state": home.upper(), "commits": count, "of": total, "share": round(count / total, 3)}
    return {"byState": table, "inState": in_state, "unknownState": unknown}


def home_state(teams: list[Team], school: str) -> str | None:
    team = next((t for t in teams if isinstance(t, Team) and t.school == school), None)
    location = team.location if team is not None and isinstance(team.location, dict) else {}
    return text(location.get("state"))


# --- call sites: one line each in the services ---------------------------------------------------------------------


def _failed(data: dict[str, Any], what: str, exc: Exception) -> None:
    """Fail loud: the traceback goes to the log and the answer's parts carry an error the status
    indicator shows. The page itself still goes out."""
    log.exception("%s failed; the answer goes out without them", what)
    parts = data.get("parts")
    if isinstance(parts, dict):
        parts["extras"] = {"status": "error", "fetchedAt": None, "ageSeconds": None, "error": f"{what}: {exc.__class__.__name__}", "skipped": 0}


def season_extras(data: dict[str, Any], parts: dict[str, Any], team: str) -> None:
    """Season overview: form on standings rows, rank paths on poll rows, the strip on schedule rows."""
    try:
        table = form_table(_records(parts.get("games")) + _records(parts.get("schedule")))
        for row in data.get("standings") or []:
            if isinstance(row, dict):
                row["form"] = form_for(table, row.get("team"))
        attach_poll_paths(data.get("polls"), _records(parts.get("rankings")))
        attach_strip(data.get("schedule"), _records(parts.get("schedule")), team, _records(parts.get("sp")), _records(parts.get("elo")))
    except Exception as exc:  # noqa: BLE001 - the extras must never take the page down; logged and shown in parts
        _failed(data, "Season extras", exc)


def program_extras(data: dict[str, Any], parts: dict[str, Any], *, team: str, opponent: str | None, venue: Any) -> None:
    """Game program: form and Elo paths on the team blocks, venue facts, the radar link, and the
    opponent's throw and run tables inside tendencies."""
    try:
        games = _records(parts.get("games")) + _records(parts.get("schedule"))
        table = form_table(games)
        for side, school in (("us", team), ("them", opponent)):
            block = data.get(side)
            if isinstance(block, dict):
                block["form"] = form_for(table, school)
                block["eloPath"] = elo_path(games, school)
        game = data.get("game")
        if isinstance(game, dict) and isinstance(game.get("venueDetail"), dict):
            game["venueDetail"].update(venue_facts(venue, _records(parts.get("series")), team, game.get("venue")))
        if isinstance(data.get("weather"), dict):
            data["weather"]["radarUrl"] = radar_url(venue)
        if isinstance(data.get("tendencies"), dict) and opponent:
            data["tendencies"].update(throw_run_tables(_records(parts.get("oppRushes")), _records(parts.get("oppPasses")), opponent))
    except Exception as exc:  # noqa: BLE001
        _failed(data, "Program extras", exc)


def team_extras(data: dict[str, Any], parts: dict[str, Any], school: str) -> None:
    """Team page header: form and the Elo path."""
    try:
        games = _records(parts.get("games")) + _records(parts.get("teamGames"))
        block = data.get("team")
        if isinstance(block, dict):
            block["form"] = form_for(form_table(games), school)
            block["eloPath"] = elo_path(games, school)
    except Exception as exc:  # noqa: BLE001
        _failed(data, "Team page extras", exc)


def newspaper_extras(data: dict[str, Any], parts: dict[str, Any]) -> None:
    """Newspaper game cards: each side's form."""
    try:
        table = form_table(_records(parts.get("games")) + _records(parts.get("schedule")) + _records(parts.get("weekGames")))
        for card in data.get("slate") or []:
            for side in ("home", "away"):
                block = card.get(side) if isinstance(card, dict) else None
                if isinstance(block, dict):
                    block["form"] = form_for(table, block.get("school"))
    except Exception as exc:  # noqa: BLE001
        _failed(data, "Newspaper extras", exc)


async def recruiting_extras(client: Any, data: dict[str, Any], parts: dict[str, Any], *, team: str, year: int) -> None:
    """Recruiting classes: where they're from. The home state comes from the /teams/fbs answer the
    other pages cached (a peek, never a call); without it the in-state share is None."""
    try:
        payload = await peek(client, "/teams/fbs", {"year": year})
        state = home_state(parse_records(Team, payload, context="recruiting/teams peek").records, team) if payload is not None else None
        for block in data.get("classes") or []:
            if isinstance(block, dict):
                block.update(where_from(_records(parts.get(block.get("partName") or "")), team, state))
    except Exception as exc:  # noqa: BLE001
        _failed(data, "Recruiting extras", exc)
