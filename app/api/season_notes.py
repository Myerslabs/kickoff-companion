"""The season prompts (Phase 17 Part 3a): the preseason load for the primary teams and the coaches for every FBS team.

GET  /api/season-notes                     what's loaded: preseason by primary team, coaches by conference, the run
GET  /api/season-notes/prompt?kind=&key=   one batch's prompt to copy (kind preseason: key a primary team; coaches:
                                           key a conference)
POST /api/season-notes/save                {kind, key, text}: read a pasted answer and save it
GET, POST /api/season-notes/run            Claude Code works through the batches ({kind, keys, missingOnly})
GET, PUT, DELETE /api/season-notes/template?kind=   the prompt templates, editable in Settings
GET  /api/preseason                        the Preseason page: every primary team's load with its coaches
Part 3b: kind "costs", one batch per conference: rumored roster costs (every team's total, the primary teams' detail).

No CFBD call beyond the cached team list. Any device on the home network may paste, as with the game notes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.envelope import envelope, error_response
from app.services import readiness as readiness_service
from app.services import season_all, season_prompts, teamset
from app.services.notes import load_notes
from app.services.season_notes import SeasonNotes
from app.services.season_task import Batch, SeasonRunner

router = APIRouter(tags=["season-notes"])


async def _context(request: Request) -> tuple[list[str], dict[str, list[str]], dict[str, dict[str, Any]]]:
    """(primary teams, {conference: schools}, {school: team meta}) from the cached FBS list."""
    state = request.app.state
    program = state.program
    teams = await program.fbs_teams()
    meta = program._teams_from(teams)
    primaries = list(teamset.current(state.settings, getattr(state, "prefs", None), state.cfbd, teams).primaries)
    conferences: dict[str, list[str]] = {}
    for school, row in meta.items():
        conference = row.get("conference")
        if isinstance(conference, str) and conference.strip():
            conferences.setdefault(conference.strip(), []).append(school)
    for schools in conferences.values():
        schools.sort()
    return primaries, conferences, meta


def _notes(request: Request) -> SeasonNotes:
    return request.app.state.season_notes


def _today(request: Request) -> Any:
    clock = request.app.state.cfbd._clock
    return clock().astimezone(request.app.state.settings.tzinfo).date() if callable(clock) else datetime.now().date()


def _prompt(request: Request, kind: str, key: str, primaries: list[str], conferences: dict[str, list[str]], meta: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    """(prompt, error)."""
    data_dir = request.app.state.settings.data_dir
    season = request.app.state.settings.season
    if kind == "season":
        return season_prompts.season_prompt(data_dir, primaries=primaries, conferences=conferences, season=season), None
    if kind == "preseason":
        school = next((p for p in primaries if p.lower() == key.strip().lower()), None)
        if school is None:
            return None, f"{key} is not one of your primary teams."
        row = meta.get(school) or {}
        name = " ".join(x for x in (school, row.get("mascot")) if isinstance(x, str) and x)
        return season_prompts.preseason_prompt(data_dir, school=school, team_name=name, conference=row.get("conference"), season=season), None
    if kind == "coaches" and key.strip().lower() == "all":
        return season_all.coaches_all_prompt(data_dir, conferences=conferences, season=season), None
    if kind == "costs" and key.strip().lower() == "all":
        detailed = [s for names in conferences.values() for s in names if s in primaries]
        return season_all.costs_all_prompt(data_dir, conferences=conferences, detailed=detailed, season=season), None
    if kind == "coaches":
        conference = next((c for c in conferences if c.lower() == key.strip().lower()), None)
        if conference is None:
            return None, f"{key} is not an FBS conference this season."
        return season_prompts.coaches_prompt(data_dir, conference=conference, schools=conferences[conference], season=season), None
    if kind == "costs":
        conference = next((c for c in conferences if c.lower() == key.strip().lower()), None)
        if conference is None:
            return None, f"{key} is not an FBS conference this season."
        schools = conferences[conference]
        detailed = [s for s in schools if s in primaries]
        return season_prompts.costs_prompt(data_dir, conference=conference, schools=schools, detailed=detailed, season=season), None
    return None, "kind must be season, preseason, coaches or costs"


def _saver(request: Request, kind: str, key: str, primaries: list[str], conferences: dict[str, list[str]]):
    """save(text) -> (saved, error, warnings) for one batch, shared by a paste and a Claude Code run."""
    notes = _notes(request)

    def save(text: str) -> tuple[bool, str | None, list[str]]:
        if kind == "season":
            reading = season_prompts.read_season(text, primaries, conferences)
            if reading.value is None:
                return False, reading.error, reading.warnings
            for school, team in reading.value["teams"].items():
                notes.save_preseason(team, school, (reading.summary or {}).get("author"))
            for conference, batch in reading.value["coaches"].items():
                notes.save_coaches(batch, conference, conferences.get(conference, []))
            return True, None, reading.warnings
        if kind == "preseason":
            school = next((p for p in primaries if p.lower() == key.strip().lower()), key)
            reading = season_prompts.read_preseason(text, school)
            if reading.value is None:
                return False, reading.error, reading.warnings
            notes.save_preseason(reading.value, school, (reading.summary or {}).get("author"))
            return True, None, reading.warnings
        if kind in ("coaches", "costs") and key.strip().lower() == "all":
            reading = season_all.read_coaches_all(text, conferences) if kind == "coaches" else season_all.read_costs_all(text, conferences)
            if reading.value is None:
                return False, reading.error, reading.warnings
            for conference, batch in reading.value.items():
                names = conferences.get(conference, [])
                if kind == "coaches":
                    notes.save_coaches(batch, conference, names)
                else:
                    notes.save_costs(batch, conference, names, [s for s in names if s in primaries])
            return True, None, reading.warnings
        conference = next((c for c in conferences if c.lower() == key.strip().lower()), key)
        schools = conferences.get(conference, [])
        if kind == "costs":
            reading = season_prompts.read_costs(text, conference, schools)
            if reading.value is None:
                return False, reading.error, reading.warnings
            notes.save_costs(reading.value, conference, schools, [s for s in schools if s in primaries])
            return True, None, reading.warnings
        reading = season_prompts.read_coaches(text, conference, schools)
        if reading.value is None:
            return False, reading.error, reading.warnings
        notes.save_coaches(reading.value, conference, schools)
        return True, None, reading.warnings

    return save


@router.get("/api/claude-schedule")
async def claude_schedule(request: Request) -> Any:
    """What Claude Code will run by itself next, and what it ran lately (Settings > Claude on a schedule)."""
    return envelope(await request.app.state.claude_schedule.status(), source="live")


@router.get("/api/readiness")
async def readiness(request: Request) -> Any:
    """What is not loaded yet, for the first screen and the Settings card. No CFBD call beyond the cached schedule."""
    from app.api.notes import _game  # the next game on our schedule

    primaries, conferences, _meta = await _context(request)
    state = request.app.state
    status = _notes(request).status(primaries, conferences, _today(request))
    game_info = None
    notes = None
    errors: list[dict[str, str]] = []
    try:
        game, _schedule_ok = await _game(request, None)  # final pass: _game also says whether the schedule could be read
    except Exception:  # noqa: BLE001 - the card still answers about the season loads; the error is shown
        game = None
        errors.append({"code": "schedule_unavailable", "message": "This week's game could not be read, so its notes are not checked."})
    if game is not None and not game.completed:
        team = state.settings.team
        opponent = game.away_team if game.home_team == team else game.home_team
        game_info = {"gameId": game.id, "opponent": opponent}
        notes, _problem = load_notes(state.settings.data_dir, game.id)
    result = readiness_service.readiness(status, notes, game_info, _today(request))
    started = state.started_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    return envelope({**result, "serverStartedAt": started}, source="live", errors=errors)


@router.get("/api/season-notes")
async def season_status(request: Request) -> Any:
    primaries, conferences, _meta = await _context(request)
    runner: SeasonRunner = request.app.state.season_runner
    command = request.app.state.settings.claude_command
    return envelope({**_notes(request).status(primaries, conferences, _today(request)), "run": runner.status(command)}, source="live")


@router.get("/api/season-notes/prompt")
async def season_prompt(request: Request, kind: str, key: str) -> Any:
    primaries, conferences, meta = await _context(request)
    prompt, error = _prompt(request, kind, key, primaries, conferences, meta)
    if prompt is None:
        return error_response(404, "not_found", error or "No such batch.")
    _template, custom = season_prompts.template(kind, request.app.state.settings.data_dir).read()
    return envelope({"kind": kind, "key": key, "prompt": prompt, "custom": custom, "chars": len(prompt)}, source="live")


class SaveRequest(BaseModel):
    kind: str = Field(pattern="^(season|preseason|coaches|costs)$")
    key: str = Field(min_length=1, max_length=120)
    text: str = Field(max_length=season_prompts.MAX_ANSWER)


@router.post("/api/season-notes/save")
async def season_save(body: SaveRequest, request: Request) -> Any:
    primaries, conferences, meta = await _context(request)
    _prompt_text, error = _prompt(request, body.kind, body.key, primaries, conferences, meta)
    if error:
        return error_response(404, "not_found", error)
    try:
        saved, problem, warnings = _saver(request, body.kind, body.key, primaries, conferences)(body.text)
    except OSError as exc:
        return error_response(500, "not_saved", f"The answer could not be saved: {exc}.")
    if not saved:
        return error_response(422, "unreadable", problem or "The answer has nothing usable in it.")
    return envelope({"ok": True, "saved": True, "warnings": warnings}, source="live")


class RunRequest(BaseModel):
    kind: str = Field(pattern="^(season|preseason|coaches|costs)$")
    keys: list[str] | None = Field(default=None, max_length=40)
    missingOnly: bool = True


@router.get("/api/season-notes/run")
async def season_run_status(request: Request) -> Any:
    runner: SeasonRunner = request.app.state.season_runner
    return envelope(runner.status(request.app.state.settings.claude_command), source="live")


async def start_season_run(request: Any, kind: str, keys: list[str] | None = None, missing_only: bool = True) -> dict[str, Any]:
    """Queue a season run for Claude Code. `request` is anything with `.app.state` (the schedule passes a stand-in)."""
    primaries, conferences, meta = await _context(request)
    runner: SeasonRunner = request.app.state.season_runner
    notes = _notes(request)
    if kind == "season":
        keys = ["all"]
    elif kind == "preseason":
        loaded = notes.preseason_meta()
        keys = keys or [p for p in primaries if not (missing_only and p in loaded)]
    elif kind == "costs":
        saved = notes.costs()["batches"]
        keys = keys or [c for c in sorted(conferences) if not (missing_only and c in saved)]
    else:
        saved = notes.coaches()["batches"]
        # Final pass: a full refresh of the staffs (the winter schedule slots, "Run all again") is the one prompt for every
        # conference (Phase 19.3), not a run per conference; "the missing" still goes conference by conference
        keys = keys or (["all"] if not missing_only else [c for c in sorted(conferences) if c not in saved])
    batches = []
    for key in keys:
        prompt, error = _prompt(request, kind, key, primaries, conferences, meta)
        if prompt is not None:
            batches.append(Batch(key, prompt, _saver(request, kind, key, primaries, conferences)))
    return await runner.start(kind, batches, request.app.state.settings.claude_command)


@router.post("/api/season-notes/run")
async def season_run(body: RunRequest, request: Request) -> Any:
    status = await start_season_run(request, body.kind, body.keys, body.missingOnly)
    if status.get("error") and not status.get("running"):
        return envelope(status, source="live", errors=[{"code": "season_not_started", "message": status["error"]}])
    return envelope(status, source="live")


class TemplateRequest(BaseModel):
    template: str = Field(max_length=20_000)


def _template(request: Request, kind: str):
    if kind not in season_prompts.KINDS:
        return None
    return season_prompts.template(kind, request.app.state.settings.data_dir)


@router.get("/api/season-notes/template")
async def season_template_get(request: Request, kind: str) -> Any:
    t = _template(request, kind)
    if t is None:
        return error_response(404, "not_found", "kind must be preseason, coaches or costs")
    return envelope(t.payload(), source="live")


@router.put("/api/season-notes/template")
async def season_template_put(body: TemplateRequest, request: Request, kind: str) -> Any:
    t = _template(request, kind)
    if t is None:
        return error_response(404, "not_found", "kind must be preseason, coaches or costs")
    text = body.template.replace("\r\n", "\n")
    problem = t.check(text)
    if problem:
        return error_response(422, "bad_template", problem)
    try:
        t.write(text)
    except OSError as exc:
        return error_response(500, "template_not_saved", f"The prompt could not be saved: {exc}.")
    return envelope(t.payload(), source="live")


@router.delete("/api/season-notes/template")
async def season_template_reset(request: Request, kind: str) -> Any:
    t = _template(request, kind)
    if t is None:
        return error_response(404, "not_found", "kind must be preseason, coaches or costs")
    try:
        t.write(None)
    except OSError as exc:
        return error_response(500, "template_not_saved", f"The prompt could not be reset: {exc}.")
    return envelope(t.payload(), source="live")


@router.get("/api/preseason")
async def preseason_page(request: Request) -> Any:
    primaries, conferences, meta = await _context(request)
    notes = _notes(request)
    loaded = notes.preseason()
    saved = notes.preseason_meta()
    teams = []
    for school in primaries:
        team = loaded.get(school)
        row = meta.get(school) or {}
        teams.append({
            "school": school,
            "mascot": row.get("mascot"),
            "conference": row.get("conference"),
            "logo": row.get("logo"),
            "logoDark": row.get("logoDark"),
            "savedAt": (saved.get(school) or {}).get("savedAt"),
            "author": (saved.get(school) or {}).get("author"),
            "coaches": notes.coaches_for(school),
            "costs": notes.costs_for(school),
            "preseason": team.model_dump(mode="json") if team else None,
        })
    status = notes.status(primaries, conferences, _today(request))
    return envelope({"season": notes.season, "teams": teams, "status": status}, source="live")
