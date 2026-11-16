"""Connects the season rollover's switch (app/services/rollover.py) to this app: the rail's line for "closed out", CFBD's
postseason and next season's schedule through the quota guard, what counts as busy, the season in review kept in
data/season/<year>/book/ by asking the app's own routes in process, .env, and the in-place restart. Kept apart so the rules
stay pure and testable.

    build_rollover(app) -> Rollover            the app's tick skips it in the test league (it never switches a season)
    BOOK_PARTS                                  the season in review's answers kept at the switch: part -> path
    keep_book(app, season) -> list[str]         writes the parts, returns the ones kept; overview and players must answer
    read_book(data_dir, season, part) -> dict | None
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app import restart
from app.cache import DataKind
from app.cfbd.models import Game
from app.services.answers import atomic_write
from app.services.envfile import set_values
from app.services.rollover import Rollover, title_game_final

log = logging.getLogger("kickoff.rollover")

CHECK_MAX_AGE = timedelta(hours=12)  # the daily check reads CFBD's answers at most half a day old
REQUIRED_PARTS = ("overview", "players")  # without these the book is not the season in review: the switch waits


BOOK_PARTS = {
    "overview": "/api/season/overview",
    "players": "/api/season/players",
    "stops": "/api/stops",  # the line: each game's stops, for the schedule's marks
    "blame": "/api/blame/now",  # the Circle of Blame's last report and the season's strip (its weeks read by season already)
}  # the Imperialism Map's land reads by season already (/api/imperialism/<year>/...)


def book_dir(data_dir: Path, season: int) -> Path:
    return Path(data_dir) / "season" / str(int(season)) / "book"


def read_book(data_dir: Path, season: int, part: str) -> dict[str, Any] | None:
    """A kept part: {"keptAt", "path", "status", "envelope"}, or None (never kept, or unreadable; logged)."""
    path = book_dir(data_dir, season) / f"{part}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("The %s season's kept %s could not be read: %s", season, part, exc)
        return None
    return raw if isinstance(raw, dict) and isinstance(raw.get("envelope"), dict) else None


async def keep_book(app: Any, season: int) -> list[str]:
    """Asks the app's own routes for the season in review, as a page would, and keeps each answer. A required part that
    does not answer 200 raises (the switch waits); another is left out and the page says it was not kept."""
    settings = app.state.settings
    parts = BOOK_PARTS
    folder = book_dir(settings.data_dir, season)
    kept: list[str] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", timeout=httpx.Timeout(300.0)) as client:
        for part, path in parts.items():
            try:
                response = await client.get(path)
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if part in REQUIRED_PARTS:
                    raise RuntimeError(f"the season in review's {part} could not be read ({exc.__class__.__name__})") from exc
                log.warning("The %s book's %s was not kept: %s", season, part, exc)
                continue
            if response.status_code != 200 or not isinstance(body, dict):
                if part in REQUIRED_PARTS:
                    raise RuntimeError(f"the season in review's {part} answered {response.status_code}")
                log.info("The %s book's %s was not kept: it answered %s", season, part, response.status_code)
                continue
            atomic_write(folder / f"{part}.json", json.dumps({"keptAt": now, "path": path, "status": response.status_code, "envelope": body}))
            kept.append(part)
    log.info("The %s season in review kept: %s", season, ", ".join(kept))
    return kept


async def freeze_papers(app: Any) -> list[str]:
    """Rollover R3: every kept edition of the season frozen before the switch, its games' finals from the cached schedule.
    A failure is logged and never holds the switch: the editions stay kept, only not marked final."""
    try:
        core = await app.state.program._core()
        games = core["games"].records if core.get("games") is not None and core["games"].ok else []
        frozen = app.state.rankedweek.freeze_season(games)
    except Exception:  # noqa: BLE001 - the papers are kept either way; logged
        log.exception("The season's papers could not be frozen before the switch")
        return []
    log.info("The season's papers frozen before the switch: %s", ", ".join(frozen) or "none left to freeze")
    return frozen


def _busy(app: Any) -> str | None:
    state = app.state
    checks = (
        ("a game window is open", lambda: state.live.window_open()),
        ("a Claude run is writing", lambda: state.writing.running),
        ("Claude's notes are being written", lambda: state.notes.running),
        ("the weekly jobs are running", lambda: state.jobs.running),
        ("a prompts run is going", lambda: state.prompt_runs.running),
    )
    for words, check in checks:
        try:
            if check():
                return words
        except AttributeError:
            continue  # a part this app does not have never holds the switch
    return None


def build_rollover(app: Any) -> Rollover:
    state = app.state
    settings = state.settings
    program = state.program

    async def closed_out() -> bool:
        from app.stops_setup import line_for

        line = await line_for(state, datetime.now(timezone.utc))
        book = next((item for item in line.get("items") or [] if isinstance(item, dict) and item.get("kind") == "book"), None)
        return bool(book) and book.get("state") == "open"

    async def title_final() -> bool | None:
        part = await program.fetcher.fetch("titleGame", "/games", {"year": settings.season, "seasonType": "postseason", "classification": "fbs"}, Game, DataKind.SCHEDULE, max_age=CHECK_MAX_AGE)
        if not part.ok:
            log.warning("The postseason could not be read for the switch: %s", part.error)
            return None
        return title_game_final(part.records, datetime.now(timezone.utc))

    async def next_listed(year: int) -> bool | None:
        part = await program.fetcher.fetch("nextSchedule", "/games", {"year": year, "team": program.team}, Game, DataKind.SCHEDULE, max_age=CHECK_MAX_AGE)
        if not part.ok:
            log.warning("The %s schedule could not be read for the switch: %s", year, part.error)
            return None
        return any(isinstance(g, Game) for g in part.records)

    def set_season(year: int) -> None:
        path = settings.env_path
        if path is None:
            raise RuntimeError("this install has no .env file to write the season into")
        try:
            set_values(path, {"SEASON": str(int(year))})
        except OSError as exc:
            raise RuntimeError(f"the .env file could not be written ({exc.strerror or exc})") from exc

    async def keep(season: int) -> None:
        await keep_book(app, season)
        await freeze_papers(app)  # rollover R3: the season's last papers kept as printed

    return Rollover(
        data_dir=settings.data_dir,
        season=settings.season,
        tz=settings.tzinfo,
        closed_out=closed_out,
        title_final=title_final,
        next_listed=next_listed,
        busy=lambda: _busy(app),
        keep_book=keep,
        set_season=set_season,
        restart=restart.request,
    )
