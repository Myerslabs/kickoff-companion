"""Settings the owner changes in the app (X6), stored on the server so every device sees the
same thing (owner direction 2026-09-23: the server stays simple, every option lives in the app).

`data/settings.json` holds them. Secrets never live here; the CFBD key stays in `.env`. A broken
file is reported and the defaults apply; a bad value in a PUT is refused with a readable message."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import RadioSource

log = logging.getLogger("kickoff.prefs")

SETTINGS_FILE = "settings.json"
MAX_EXTRA_PRIMARIES = 4  # primary teams #2 to #5
MAX_STATIONS = 12


class SavedStation(RadioSource):
    """A radio station added in Settings: a RADIO_SOURCES entry plus the team it belongs to."""

    team: str | None = Field(default=None, max_length=60)

    @field_validator("team", mode="before")
    @classmethod
    def _team(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if any(ch in value for ch in "\r\n<>"):
                raise ValueError("must be a school name")
            return value or None
        return value

    @field_validator("name")
    @classmethod
    def _plain_name(cls, value: str) -> str:
        if any(ch in value for ch in "\r\n<>"):
            raise ValueError("must be one line of plain text")
        return value


class Prefs(BaseModel):
    """Every field has a safe default, so an empty or missing file is a complete answer."""

    delaySeconds: int = Field(default=30, ge=0, le=120)
    radioSourceId: str | None = Field(default=None, max_length=80)
    theme: Literal["dark", "light"] = "dark"
    refreshMinutes: int = Field(default=15, ge=1, le=120)
    autoStart: bool = False
    trayMode: bool = False
    hints: bool = True  # stat names show a dotted underline and explain themselves when tapped (2026-09-26)
    keepScreenOn: Literal["off", "gameday", "always"] = "gameday"  # the shell's screen wake lock (Phase 12)
    openBrowser: Literal["manual", "always", "never"] = "manual"  # open the app on the host when the server starts (Phase 4b)
    # Public release Phase 5b (a Tier 2 key for all of these). Primary teams #2 to #5: their team pages load
    # as soon as a device connects and sit one tap away in the menu; the home team (TEAM in .env) stays
    # primary #1 and alone themes the app. Secondary teams: schools, whole conferences and states as CFBD
    # spells them, loaded only when a page asks; with the primaries they fill the My teams ticker and page.
    primaryTeams: list[str] = Field(default_factory=list, max_length=MAX_EXTRA_PRIMARIES)
    likedTeams: list[str] = Field(default_factory=list, max_length=40)
    likedConferences: list[str] = Field(default_factory=list, max_length=12)
    likedStates: list[str] = Field(default_factory=list, max_length=12)
    tickerMode: Literal["national", "mine"] = "national"  # every FBS game, or only my teams' games (Tier 2)
    # Radio stations added in Settings (Phase 5b), after the RADIO_SOURCES in .env. `team` says whose station it is.
    radioStations: list[SavedStation] = Field(default_factory=list, max_length=MAX_STATIONS)
    notesCommand: str = Field(default="claude", min_length=1, max_length=400)

    @field_validator("notesCommand")
    @classmethod
    def _command(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must name the Claude Code command (claude, or a full path to it)")
        if any(ch in value for ch in "\r\n"):
            raise ValueError("must be one line")
        return value

    @field_validator("primaryTeams", "likedTeams", "likedConferences", "likedStates")
    @classmethod
    def _names(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            name = value.strip() if isinstance(value, str) else ""
            if not name or len(name) > 60 or any(ch in name for ch in "\r\n<>"):
                raise ValueError(f"{value!r} is not a team, conference or state name")
            if name.lower() not in {n.lower() for n in out}:
                out.append(name)
        return out

    @field_validator("radioSourceId", mode="before")
    @classmethod
    def _blank_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class PrefsError(ValueError):
    """A PUT that cannot be applied; the message is safe to show."""


def describe(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors(include_url=False):
        loc = ".".join(str(p) for p in err.get("loc", ())) or "settings"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid settings"


class PrefsStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / SETTINGS_FILE
        self.error: str | None = None
        self.prefs = self._load()

    # --- file ------------------------------------------------------------------------------------

    def _load(self) -> Prefs:
        if not self.path.is_file():
            return Prefs()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))  # a file saved by Notepad starts with a byte-order mark
        except (OSError, ValueError) as exc:
            self.error = f"{self.path.name} could not be read ({exc}); defaults apply"
            log.warning("Settings file problem: %s", self.error)
            return Prefs()
        if not isinstance(raw, dict):
            self.error = f"{self.path.name} is not an object; defaults apply"
            log.warning("Settings file problem: %s", self.error)
            return Prefs()
        try:
            prefs = Prefs(**raw)
        except ValidationError as exc:
            self.error = f"{self.path.name} has a bad value ({describe(exc)}); defaults apply"
            log.warning("Settings file problem: %s", self.error)
            return Prefs()
        self.error = None
        return prefs

    def _save(self, prefs: Prefs) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(prefs.model_dump(), handle, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    # --- public ------------------------------------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return self.prefs.model_dump()

    def update(self, patch: Any) -> Prefs:
        """Apply a partial change. Unknown keys are refused so a typo never silently does nothing."""
        if not isinstance(patch, dict):
            raise PrefsError("settings must be an object")
        unknown = sorted(set(patch) - set(Prefs.model_fields))
        if unknown:
            raise PrefsError(f"unknown setting(s): {', '.join(unknown)}")
        try:
            merged = Prefs(**{**self.prefs.model_dump(), **patch})
        except ValidationError as exc:
            raise PrefsError(describe(exc)) from None
        try:
            self._save(merged)
        except OSError as exc:
            raise PrefsError(f"could not write {self.path.name}: {exc}") from None
        self.prefs = merged
        self.error = None
        log.info("Settings saved: %s", ", ".join(f"{k}={v!r}" for k, v in patch.items()))
        return merged
