"""Circle of Blame (FEAT-18, Feature Set v2 Phase C, the owner's answers of 2026-10-30): third in
the weekly run, after Talent Edge and the Imperialism Map. For our latest final it builds one evidence pack from what the
app already keeps, has Claude Code (Opus, no tools) divide the blame 4 to 6 ways, checks the answer in code and keeps it.

    python -m app.jobs.circle_of_blame [--season 2026] [--url ...]

The run, in order:
  1. Claude Code's command must be on this computer, else the run is skipped with the reason (owner 2026-10-30, "Skip with a
     note"), and Settings' Claude on a schedule must not be off (a forced run, Regenerate, goes anyway).
  2. Our latest final: its report is written once (spec: one per game week; a bye Sunday keeps the last one); a forced run
     writes it again.
  3. The evidence pack (spec C.3), each block from the app's own services and caches; a block that cannot be read is
     {"unavailable": why}. Headlines are titles only from the season's saved headlines, the last 8 days, 40 at most.
  4. One call (app/llm/claude_cli.py), the answer checked (app/services/blame.py check_report). A timeout or an answer
     that fails the checks is tried once more, with the errors attached; a second failure, or an answer from a model that
     is not Opus, fails the run, keeps the raw output in blame/failed/<key>.json and publishes nothing.
  5. Saved in data/season/<year>/blame/<key>.json with the model, the prompt versions, the pack's SHA-256, the headlines
     shown (with their links) and the raw output; the pack beside it as <key>.pack.json.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, paced_calls
from app.cfbd.models import Coach, Game, GamePlayerStats, GameTeamStats, PlayerStat, PlayerUsage
from app.config import Settings
from app.feeds import SeasonArchive, headline_key
from app.jobs import JobFailed, JobSkipped
from app.llm.claude_cli import ClaudeCli, ClaudeFailed, ClaudeMissing, find_command
from app.services import gamekeys
from app.services.blame import BlameStore, check_report, key_order, week_key
from app.services.coaches import resolve as resolve_coaches
from app.services.depth2 import advanced_box
from app.services.imperialism import ImperialismStore
from app.services.notes import load_notes
from app.services.notes_task import scratch_dir
from app.services.numbers import NumbersStore, season_table, team_line
from app.services.parts import PartFetcher
from app.services.players import lines_from
from app.services.prefs import PrefsStore
from app.services.profiles import advanced_rows, profiles_for
from app.services.program import box_sides
from app.services.season import SeasonService
from app.services.season_notes import SeasonNotes
from app.services.talent_edge import TalentEdgeStore, summary_line

log = logging.getLogger("kickoff.jobs.blame")

NAME = "circle_of_blame"
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_FILE = PROMPTS / "circle_of_blame.system.md"
USER_FILE = PROMPTS / "circle_of_blame.user.md"
HEADLINE_DAYS = 8
HEADLINE_CAP = 40
TOP_PLAYERS = 20
TREND_GAMES = 3
VERSION = re.compile(r"prompt-version:\s*(\S+)")
GROUP_KEYS = ("count", "ratedCount", "avgRating", "avgStars", "bcrPct", "transferCount", "rank", "of", "pct")


def prompt_version(text: str) -> str:
    found = VERSION.search(text)
    return found.group(1) if found else "unversioned"


def _strip_comment(text: str) -> str:
    return re.sub(r"^\s*<!--.*?-->\s*", "", text, count=1, flags=re.DOTALL)


def render_system(team: str) -> tuple[str, str]:
    raw = SYSTEM_FILE.read_text(encoding="utf-8")
    return _strip_comment(raw).replace("{team}", team), prompt_version(raw)


def render_user(team: str, season: int, label: str, result_words: str, evidence: str) -> tuple[str, str]:
    raw = USER_FILE.read_text(encoding="utf-8")
    body = _strip_comment(raw)
    for name, value in (("{team}", team), ("{season}", str(season)), ("{week_label}", label), ("{result_words}", result_words), ("{evidence}", evidence)):
        body = body.replace(name, value)
    return body, prompt_version(raw)


def week_label(game: Any) -> str:
    return "the postseason" if gamekeys.is_post(game) else f"week {game.week}"


def ours(game: Game, team: str) -> tuple[bool, str | None, int | None, int | None]:
    home = game.home_team == team
    return home, (game.away_team if home else game.home_team), (game.home_points if home else game.away_points), (game.away_points if home else game.home_points)


def result_of(us: int | None, them: int | None) -> str | None:
    if not isinstance(us, int) or not isinstance(them, int):
        return None
    return "win" if us > them else "loss" if us < them else "tie"


def guard(name: str, build: Callable[[], Any]) -> Any:
    """One block of the pack: what `build` returns, or {"unavailable": why} (logged) when it cannot be read."""
    try:
        value = build()
    except Exception as exc:  # noqa: BLE001 - one block's failure is written into the pack, never the whole run's
        log.warning("Circle of Blame: the %s block could not be read", name, exc_info=True)
        return {"unavailable": f"{exc.__class__.__name__}: {exc}"[:300]}
    return value if value not in (None, [], {}) else {"unavailable": f"no {name} data yet"}


async def aguard(name: str, build: Callable[[], Awaitable[Any]]) -> Any:
    try:
        value = await build()
    except Exception as exc:  # noqa: BLE001 - as guard()
        log.warning("Circle of Blame: the %s block could not be read", name, exc_info=True)
        return {"unavailable": f"{exc.__class__.__name__}: {exc}"[:300]}
    return value if value not in (None, [], {}) else {"unavailable": f"no {name} data yet"}


ROLE_WORDS = {"headCoach": "head coach", "offensiveCoordinator": "offensive coordinator", "defensiveCoordinator": "defensive coordinator"}


def people(pack: dict[str, Any]) -> dict[str, str]:
    """{name: role or position} for the coaches and players the pack names, so the page can say who a named slice is."""
    out: dict[str, str] = {}
    coaching = pack.get("coaching") if isinstance(pack.get("coaching"), dict) else {}
    for key, words in ROLE_WORDS.items():
        name = coaching.get(key)
        if isinstance(name, str) and name and not name.startswith("not in "):
            out[name] = words
    players = pack.get("players") if isinstance(pack.get("players"), dict) else {}
    for row in players.get("topByUsage") or []:
        if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"] not in out:
            out[row["name"]] = str(row.get("position") or "player")
    return out


def compact_groups(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    groups = row.get("groups") if isinstance(row.get("groups"), dict) else {}
    return {
        "summaryLine": summary_line(row),
        "talent": row.get("talent"),
        "roster": row.get("summary"),
        "groups": {g: {k: v.get(k) for k in GROUP_KEYS if k in v} for g, v in groups.items() if isinstance(v, dict)},
    }


class BlameJob:
    def __init__(self, client: CfbdClient, settings: Settings, fetcher: PartFetcher | None = None, cli: ClaudeCli | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.client = client
        self.settings = settings
        self.season = settings.season
        self.team = settings.team
        self.data_dir = Path(settings.data_dir)
        self.fetcher = fetcher or PartFetcher(client)
        self.cli = cli
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.store = BlameStore(self.data_dir, self.season)

    # --- the run ---------------------------------------------------------------------------------------------------

    async def run(self, force: bool = False, refresh: bool = False) -> dict[str, Any]:
        """`refresh` (batch 4, Run with Claude): written again like `force`, with the report as it stands after the evidence
        pack, never in it: the name check reads the evidence, and an old report must not vouch for its own names."""
        force = force or refresh
        command = self.settings.claude_command or "claude"
        if self.cli is None:
            found, searched = find_command(command)
            if found is None:
                log.info("Circle of Blame skipped: %r is not on this computer (PATH: %s)", command, searched)
                raise JobSkipped(f"Claude Code isn't on this computer (looked for '{command}' on the PATH); the report is written on the computer that has it")
            self.cli = ClaudeCli(command, scratch_dir(self.data_dir))
        if not force and self._schedule_off():
            raise JobSkipped("Claude on a schedule is off in Settings; Regenerate on the page writes the report now")
        overview = await SeasonService(self.client, self.settings).overview()
        schedule = overview.parts.get("schedule")
        if schedule is None or not schedule.ok:
            raise JobFailed(f"Our schedule could not be read: {schedule.error if schedule is not None else 'no answer'}")
        finals = [g for g in schedule.records if g.completed and isinstance(g.week, int) and result_of(*ours(g, self.team)[2:]) is not None]
        if not finals:
            raise JobSkipped(f"No game of {self.team}'s is final yet in {self.season}")
        game = max(finals, key=gamekeys.order)
        key = week_key(game.season_type, game.week)
        label = week_label(game)
        if not force and self.store.load(key) is not None:
            return {"week": game.week, "key": key, "message": f"The report for {label} is already written; Regenerate writes a new one"}
        pack, headlines = await self.pack(overview, game, finals)
        held = self.store.load(key) if refresh else None
        page_now = ""
        if isinstance(held, dict) and isinstance(held.get("report"), dict):
            from app.services.writing import refresh_text

            page_now = refresh_text(held["report"])  # the report as the page shows it, not its stamps
        evidence = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
        self.store.save_pack(key, pack)
        return await self.write(game, key, label, pack, evidence, digest, headlines, page_now=page_now)

    def _schedule_off(self) -> bool:
        try:
            return PrefsStore(self.data_dir).prefs.scheduledRuns is not True  # off until Settings turns it on
        except Exception:  # noqa: BLE001 - unreadable settings: the defaults apply (logged by the store)
            log.warning("Circle of Blame: the settings could not be read; the schedule counts as off", exc_info=True)
            return True

    async def write(self, game: Game, key: str, label: str, pack: dict[str, Any], evidence: str, digest: str, headlines: list[dict[str, Any]], page_now: str = "") -> dict[str, Any]:
        _home, opponent, us, them = ours(game, self.team)
        outcome = result_of(us, them) or "result"
        words = f"a {us}-{them} {outcome} {'to' if outcome == 'loss' else 'against'} {opponent}" if outcome != "tie" else f"a {us}-{them} tie with {opponent}"
        system_text, system_version = render_system(self.team)
        system_path = scratch_dir(self.data_dir) / "circle_of_blame.system.md"
        system_path.write_text(system_text, encoding="utf-8")
        attempts: list[dict[str, Any]] = []
        report: dict[str, Any] | None = None
        retry_note = ""
        result = None
        user_version = "unversioned"
        assert self.cli is not None
        for attempt in (1, 2):
            prompt, user_version = render_user(self.team, self.season, label, words, evidence)
            started = self.clock()
            try:
                result = await self.cli.ask(system_text, system_path, prompt + page_now + retry_note)
            except ClaudeMissing as exc:
                raise JobSkipped("Claude Code isn't on this computer any more") from exc
            except TimeoutError:
                attempts.append({"attempt": attempt, "startedAt": started.isoformat(timespec="seconds"), "error": f"no answer in {int(self.cli.timeout)} s"})
                retry_note = ""
                continue
            except ClaudeFailed as exc:
                attempts.append({"attempt": attempt, "startedAt": started.isoformat(timespec="seconds"), "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr})
                self._failed(key, digest, attempts)
                raise JobFailed(str(exc)) from exc
            report, errors = check_report(result.text, evidence, self.season, int(game.week))
            attempts.append({"attempt": attempt, "startedAt": started.isoformat(timespec="seconds"), "model": result.model, "errors": errors, "stdout": result.stdout, "stderr": result.stderr})
            if report is not None:
                break
            retry_note = "\n\nYour last reply failed these checks; fix every one and reply with only the JSON object:\n" + "\n".join(f"- {e}" for e in errors[:20])
        if report is None or result is None:
            self._failed(key, digest, attempts)
            last = attempts[-1]
            why = last.get("error") or "; ".join((last.get("errors") or [])[:3])
            raise JobFailed(f"No report for {label} after {len(attempts)} tries: {why}")
        record = {
            "format": 1,
            "people": people(pack),
            "season": self.season,
            "key": key,
            "week": game.week,
            "gameId": game.id,
            "label": label[:1].upper() + label[1:],
            "opponent": opponent,
            "home": game.home_team == self.team,
            "neutral": bool(game.neutral_site),
            "score": {"us": us, "them": them},
            "generatedAt": self.clock().isoformat(timespec="seconds"),
            "modelUsed": result.model,
            "models": sorted(result.models),
            "promptVersion": {"system": system_version, "user": user_version},
            "inputHash": digest,
            "attempts": len(attempts),
            "costUsd": result.cost_usd,
            "durationMs": result.duration_ms,
            "status": "published",
            "report": report,
            "headlines": headlines,
            "raw": {"stdout": result.stdout, "stderr": result.stderr},
        }
        self.store.save(key, record)
        seconds = f" in {round(result.duration_ms / 1000)} s" if isinstance(result.duration_ms, int) else ""
        return {"week": game.week, "key": key, "model": result.model, "message": f"The report for {label} was written by {result.model}{seconds}{' on the second try' if len(attempts) > 1 else ''}"}

    def _failed(self, key: str, digest: str, attempts: list[dict[str, Any]]) -> None:
        self.store.save_failure(key, {"at": self.clock().isoformat(timespec="seconds"), "inputHash": digest, "attempts": attempts})

    # --- the evidence pack (spec C.3) --------------------------------------------------------------------------------

    async def pack(self, overview: Any, game: Game, finals: list[Game]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        data = overview.data if isinstance(overview.data, dict) else {}
        parts = overview.parts
        schedule = list(parts["schedule"].records)
        upcoming = sorted((g for g in schedule if not g.completed), key=gamekeys.order)
        next_game = upcoming[0] if upcoming else None
        _home, opponent, _us, _them = ours(game, self.team)
        next_opponent = ours(next_game, self.team)[1] if next_game is not None else None
        talent = guard("Talent Edge", lambda: TalentEdgeStore(self.data_dir, self.season).load())
        headlines = self.headlines()
        with paced_calls():
            latest = await aguard("latest game", lambda: self.latest_block(game, data, talent, opponent))
            players = await aguard("players", lambda: self.players_block(finals, talent))
            coaching = await aguard("coaching", lambda: self.coaching_block(game))
        pack = {
            "about": {
                "team": self.team,
                "season": self.season,
                "through": week_label(game),
                "builtAt": self.clock().isoformat(timespec="minutes"),
                "readMe": "Each block holds data from the app's own sources; a block reading {\"unavailable\": ...} could not be read this week. Ranks are among the 138 FBS teams unless a block says otherwise.",
            },
            "season": guard("season", lambda: self.season_block(data, overview)),
            "latestGame": latest,
            "teamStats": guard("team stats", lambda: self.stats_block(parts)),
            "players": players,
            "coaching": coaching,
            "talentEdge": guard("Talent Edge", lambda: self.talent_block(talent, opponent, next_opponent)),
            "imperialism": guard("Imperialism", lambda: self.imperialism_block()),
            "headlines": [{"title": h["title"], "source": h["source"], "publishedAt": h["publishedAt"]} for h in headlines] or {"unavailable": f"no headlines about {self.team} saved in the last {HEADLINE_DAYS} days"},
            "lastWeek": guard("last week's report", lambda: self.last_week_block(week_key(game.season_type, game.week))),
        }
        return pack, headlines

    def season_block(self, data: dict[str, Any], overview: Any) -> dict[str, Any]:
        record = data.get("record") if isinstance(data.get("record"), dict) else None
        rows = data.get("schedule") if isinstance(data.get("schedule"), list) else []
        games = [
            {k: r.get(k) for k in ("week", "date", "homeAway", "conferenceGame", "completed", "result", "usPoints", "themPoints")} | {"opponent": (r.get("opponent") or {}).get("school") if isinstance(r.get("opponent"), dict) else r.get("opponent"), "opponentApRank": (r.get("opponent") or {}).get("apRank") if isinstance(r.get("opponent"), dict) else None}
            for r in rows if isinstance(r, dict)
        ]
        polls = {p.get("poll"): {"rank": p.get("usRank"), "week": p.get("week")} for p in data.get("polls") or [] if isinstance(p, dict) and p.get("poll")}
        sp = (data.get("ratings") or {}).get("sp") if isinstance(data.get("ratings"), dict) else None
        out = {"record": record or {"unavailable": "the record could not be read"}, "schedule": games or {"unavailable": "the schedule could not be read"}, "polls": polls or {"unavailable": "no poll ranks this week"}, "spPlus": sp or {"unavailable": "SP+ could not be read"}}
        if overview.errors:
            out["sourcesMissing"] = [str(e)[:160] for e in overview.errors][:8]
        return out

    async def latest_block(self, game: Game, data: dict[str, Any], talent: Any, opponent: str | None) -> dict[str, Any]:
        params = gamekeys.box_params(game, self.season, self.team)
        teams = await self.fetcher.fetch("boxTeams", "/games/teams", params, GameTeamStats, DataKind.FINISHED_GAME)
        players = await self.fetcher.fetch("boxPlayers", "/games/players", params, GamePlayerStats, DataKind.FINISHED_GAME)
        advanced = await self.fetcher.fetch("advancedBox", "/game/box/advanced", {"id": game.id}, None, DataKind.FINISHED_GAME)
        sides, lines = box_sides(teams if teams.ok else None, players if players.ok else None, game)
        home, opp, us, them = ours(game, self.team)
        row = next((r for r in data.get("schedule") or [] if isinstance(r, dict) and r.get("gameId") == game.id), {})
        box = {school: {k: v for k, v in side.items() if k != "team"} for school, side in sides.items()}
        adv = advanced_box(advanced.fetched.payload if advanced.ok and advanced.fetched is not None else None)
        them_row = talent.get("teams", {}).get(opp) if isinstance(talent, dict) and isinstance(talent.get("teams"), dict) else None
        return {
            "opponent": opp,
            "result": result_of(us, them),
            "score": {"us": us, "them": them},
            "location": "neutral site" if game.neutral_site else ("home" if home else "away"),
            "venue": row.get("venue") if isinstance(row, dict) else None,
            "date": game.start_date,
            "teamBox": box or {"unavailable": teams.error or "no team box for this game"},
            "advancedBox": adv or {"unavailable": advanced.error or "no advanced box for this game"},
            "ourPlayerLines": lines.get(self.team) or {"unavailable": players.error or "no player lines for this game"},
            "opponentTalentEdge": summary_line(them_row) if them_row else {"unavailable": f"{opp} is not in the Talent Edge table"},
        }

    def stats_block(self, parts: dict[str, Any]) -> dict[str, Any]:
        stats, games, schedule, advanced = parts.get("stats"), parts.get("games"), parts.get("schedule"), parts.get("advanced")
        out: dict[str, Any] = {}
        if stats is not None and stats.ok and games is not None and games.ok:
            rows = profiles_for(stats.records, games.records, schedule.records if schedule is not None else [], self.settings.conference, self.team).rows(self.team)
            out["perGame"] = [{k: r.get(k) for k in ("side", "label", "value", "nationalRank", "nationalOf", "conferenceRank", "conferenceOf") if k in r} for r in rows if isinstance(r, dict)]
        else:
            out["perGame"] = {"unavailable": (stats.error if stats is not None else None) or "the season's team stats could not be read"}
        if advanced is not None and advanced.ok:
            out["advanced"] = [{k: r.get(k) for k in ("side", "label", "value", "nationalRank", "nationalOf", "higherIsBetter") if k in r} for r in advanced_rows(advanced.records, self.team)]
        else:
            out["advanced"] = {"unavailable": (advanced.error if advanced is not None else None) or "the season's advanced stats could not be read"}
        teams = parts.get("teams")
        fbs = {t.school for t in teams.records} if teams is not None and teams.ok else None
        line = team_line(season_table(NumbersStore(self.data_dir, self.season).games(), fbs), self.team)
        out["appNumbers"] = line or {"unavailable": "the app's own numbers have no games of ours yet (the nightly sweep)"}
        return out

    async def players_block(self, finals: list[Game], talent: Any) -> dict[str, Any]:
        usage = await self.fetcher.fetch("usage", "/player/usage", {"year": self.season, "team": self.team}, PlayerUsage, DataKind.SEASON_STATS)
        season = await self.fetcher.fetch("playerStats", "/stats/player/season", {"year": self.season, "team": self.team}, PlayerStat, DataKind.SEASON_STATS)
        if not usage.ok:
            return {"unavailable": usage.error or "player usage could not be read"}
        mine = [u for u in usage.records if u.team in (None, self.team)]
        overall = lambda u: (u.usage or {}).get("overall") if isinstance((u.usage or {}).get("overall"), int | float) else 0.0  # noqa: E731
        top = sorted(mine, key=lambda u: (-overall(u), u.name or ""))[:TOP_PLAYERS]
        lines = lines_from(season.records) if season.ok else {}
        recruits = {}
        for row in TalentEdgeStore(self.data_dir, self.season).players(self.team):
            if isinstance(row, dict) and row.get("id") is not None:
                recruits[str(row["id"])] = {k: row.get(k) for k in ("rating", "stars", "recruitYear", "source", "transfer")}
        recent = sorted(finals, key=gamekeys.order)[-TREND_GAMES:]
        per_game: list[tuple[Game, dict[str, list[dict[str, Any]]]]] = []
        for g in recent:
            params = gamekeys.box_params(g, self.season, self.team)
            part = await self.fetcher.fetch(f"boxPlayers_{gamekeys.tag(g)}", "/games/players", params, GamePlayerStats, DataKind.FINISHED_GAME)
            per_game.append((g, box_sides(None, part if part.ok else None, g)[1].get(self.team) or {}))
        out = []
        for u in top:
            pid = str(u.id)
            season_lines = {cat: line.stats for (player, cat), line in lines.items() if player == pid}
            trend = []
            for g, cats in per_game:
                stats = {cat: row.get("stats") for cat, rows in cats.items() for row in rows if str(row.get("playerId")) == pid}
                trend.append({"opponent": ours(g, self.team)[1], "week": g.week, "lines": stats or "did not record a stat"})
            out.append({"name": u.name, "position": u.position, "usage": {k: round(v, 3) for k, v in (u.usage or {}).items() if isinstance(v, int | float)}, "season": season_lines or "no season line", "recruiting": recruits.get(pid) or "not matched to a recruit or transfer rating", "lastGames": trend})
        return {"topByUsage": out, "note": f"The {len(out)} players with the most usage (share of the team's plays); lastGames are the last {len(per_game)} finals, oldest first."}

    async def coaching_block(self, game: Game) -> dict[str, Any]:
        part = await self.fetcher.fetch("coaches", "/coaches", {"team": self.team, "year": self.season}, Coach, DataKind.TEAMS)
        head_cfbd = None
        tenure = None
        if part.ok and part.records:
            coach = part.records[0]
            head_cfbd = " ".join(n for n in (coach.first_name, coach.last_name) if n) or None
            seasons = sorted((s for s in coach.seasons if s.school == self.team), key=lambda s: s.year or 0)
            tenure = {"hired": coach.hire_date, "seasonsHere": [{"year": s.year, "wins": s.wins, "losses": s.losses, "preseasonRank": s.preseason_rank} for s in seasons]}
        notes, _error = load_notes(self.data_dir, game.id)
        have = notes.coaches.us.model_dump() if notes is not None and notes.coaches is not None and notes.coaches.us is not None else None
        resolved = resolve_coaches(self.team, notes=have, season=SeasonNotes(self.data_dir, self.season).coaches_for(self.team), cfbd_head=head_cfbd)
        unavailable = "not in the app's staff data for this season; do not name anyone in this role"
        return {
            "headCoach": resolved.get("headCoach") or unavailable,
            "offensiveCoordinator": resolved.get("offensiveCoordinator") or unavailable,
            "defensiveCoordinator": resolved.get("defensiveCoordinator") or unavailable,
            "sources": resolved.get("sources"),
            "headCoachRecord": tenure or {"unavailable": part.error or "CFBD lists no head coach for this season yet"},
            "readMe": "Names come from the game's notes, the season's staff data or CFBD (sources). CFBD lists a season still being played at 0-0; this season's real record is in the season block.",
        }

    def talent_block(self, table: Any, opponent: str | None, next_opponent: str | None) -> dict[str, Any]:
        if not isinstance(table, dict) or not isinstance(table.get("teams"), dict):
            return {"unavailable": "Talent Edge has not been worked out this season"}
        teams = table["teams"]
        out: dict[str, Any] = {"computedWeek": table.get("computedWeek"), "readMe": "Each group's average 247 composite of rated players, blue-chip share, FBS rank and percentile (100 is 1st)."}
        for role, school in (("us", self.team), ("latestOpponent", opponent), ("nextOpponent", next_opponent)):
            if school:
                out[role] = {"team": school, **(compact_groups(teams.get(school)) or {"unavailable": f"{school} is not in the table (not FBS)"})}
        return out

    def imperialism_block(self) -> dict[str, Any]:
        table = ImperialismStore(self.data_dir, self.season).load()
        if not isinstance(table, dict) or not table.get("snapshots"):
            return {"unavailable": "the Imperialism Map has not been worked out this season"}
        names = [t.get("team") for t in table.get("teams") or []]
        if self.team not in names:
            return {"unavailable": f"{self.team} is not on the map"}
        index = names.index(self.team)
        snap = table["snapshots"][-1]
        counts: dict[int, int] = {}
        for owner in snap.get("owners") or []:
            counts[owner] = counts.get(owner, 0) + 1
        cells = counts.get(index, 0)
        rank = 1 + sum(1 for n in counts.values() if n > cells) if cells else None
        events = [{"winner": e.get("winner"), "loser": e.get("loser"), "cells": e.get("cellsMoved")} for e in table.get("events") or [] if e.get("phase") == snap.get("phase") and e.get("week") == snap.get("week") and self.team in (e.get("winner"), e.get("loser")) and e.get("cellsMoved")]
        return {"readMe": "Flavor only: a map game of land taken by wins. Not evidence of play quality.", "after": snap.get("label"), "cells": cells, "of": len(snap.get("owners") or []), "rankByLand": rank, "schoolsHoldingLand": len(counts), "thisWeek": events or "no land changed hands for us"}

    def headlines(self) -> list[dict[str, Any]]:
        """Titles from the season's saved headlines, newest first, the last 8 days, one a story, 40 at most (spec C.3.8)."""
        cutoff = self.clock() - timedelta(days=HEADLINE_DAYS)
        seen: set[str] = set()
        out = []
        rows = SeasonArchive(self.data_dir).load(self.season)
        dated = []
        for row in rows:
            try:
                when = datetime.fromisoformat(str(row.get("publishedAt")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if when.tzinfo is None or when < cutoff:
                continue
            dated.append((when, row))
        for when, row in sorted(dated, key=lambda x: x[0], reverse=True):
            k = headline_key(row["title"])
            if k in seen:
                continue
            seen.add(k)
            out.append({"title": row["title"], "source": row.get("source") or "", "publishedAt": when.isoformat(timespec="minutes"), "url": row.get("url")})
            if len(out) >= HEADLINE_CAP:
                break
        return out

    def last_week_block(self, key: str) -> dict[str, Any]:
        earlier = [(k, r) for k, r in self.store.records() if key_order(k) < key_order(key)]
        if not earlier:
            return {"none": "This is the first report of the season."}
        k, record = earlier[-1]
        report = record.get("report") or {}
        return {"label": record.get("label"), "verdict": report.get("verdict"), "slices": [{"name": s.get("name"), "kind": s.get("kind"), "share_pct": s.get("share_pct")} for s in report.get("slices") or [] if isinstance(s, dict)]}


if __name__ == "__main__":
    from app.jobs.cli import main

    raise SystemExit(main(NAME, sys.argv[1:]))
