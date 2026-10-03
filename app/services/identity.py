"""Who "we" are (public release Phase 3): the configured team's school, mascot, abbreviation,
conference and colors, from CFBD's /teams/fbs, so nothing in the app names a team in its code.

The TEAM setting is the only input. At start the service resolves it once through the client (the
quota guard and the cache apply: /teams/fbs is reference data, kept for days, and the Season page
asks for the same key anyway). Until that answer is in, or if it never comes, a fallback built from
the setting alone stands in: the school as written, no mascot, a short label from its letters, and
the app's default colors, so every page still renders.

`rivals` are the other FBS schools whose names contain ours as a whole word (Michigan State and
Central Michigan for Michigan), with their alternate names. The headline filter uses
them so a story about one of those schools is not taken for ours.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdError
from app.cfbd.models import Team, parse_records
from app.cfbd.quota import QuotaBlocked

log = logging.getLogger("kickoff.identity")

APP_TITLE = "Kickoff Companion"


def short_label(school: str) -> str:
    """A short label when CFBD has none: the initials of a multi-word name, else the first four letters."""
    words = [w for w in re.split(r"[^A-Za-z]+", school) if w]
    if len(words) >= 2:
        return "".join(w[0] for w in words).upper()[:4]
    return (words[0][:4] if words else school[:4]).upper()


# Short labels for CFBD's conference names that are long (table headers and chips). A name not here
# is short already ("ACC") or gets its initials ("Biscuit Belt" -> "BB").
CONFERENCE_SHORT = {
    "American Athletic": "AAC", "Mountain West": "MWC", "Conference USA": "CUSA", "Mid-American": "MAC", "Sun Belt": "SBC",
    "Big Ten": "B1G", "Big 12": "B12", "Pac-12": "PAC", "FBS Independents": "IND",
}


def conference_short(name: str | None) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if name in CONFERENCE_SHORT:
        return CONFERENCE_SHORT[name]
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    return name if len(words) <= 1 else "".join(w[0] for w in words).upper()


def _word(name: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)


@dataclass(frozen=True)
class Identity:
    school: str
    mascot: str | None = None
    abbreviation: str | None = None
    conference: str | None = None
    color: str | None = None
    alt_color: str | None = None
    team_id: int | None = None
    rivals: tuple[str, ...] = field(default_factory=tuple)
    resolved: bool = False

    @classmethod
    def fallback(cls, school: str, conference: str | None = None) -> Identity:
        return cls(school=school, abbreviation=short_label(school), conference=conference)

    @property
    def label(self) -> str:
        """The short label for tables and the score strip: CFBD's abbreviation."""
        return self.abbreviation or short_label(self.school)

    @property
    def name(self) -> str:
        """How the app names us in words: the mascot ("Wolverines"), else the school."""
        return self.mascot or self.school

    @property
    def title(self) -> str:
        """The app's title for this install: "Wolverines Kickoff Companion"."""
        return f"{self.name} {APP_TITLE}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "school": self.school, "mascot": self.mascot, "abbreviation": self.label, "conference": self.conference,
            "conferenceShort": conference_short(self.conference),
            "color": self.color, "altColor": self.alt_color, "teamId": self.team_id, "name": self.name, "title": self.title,
            "appName": APP_TITLE, "resolved": self.resolved,
        }


def identity_from_teams(teams: list[Team], school: str, conference: str | None = None) -> Identity:
    """Our identity from a /teams/fbs list; the fallback when the school is not in it."""
    lowered = school.strip().lower()
    ours = next((t for t in teams if isinstance(t.school, str) and t.school.lower() == lowered), None)
    if ours is None:
        ours = next((t for t in teams if any(isinstance(n, str) and n.lower() == lowered for n in (t.alternate_names or []))), None)
    if ours is None:
        return Identity.fallback(school, conference)
    pattern = _word(ours.school or school)
    rivals: list[str] = []
    for t in teams:
        if t is ours or not isinstance(t.school, str):
            continue
        names = [t.school, *[n for n in (t.alternate_names or []) if isinstance(n, str)]]
        if any(pattern.search(n) for n in names):
            rivals.extend(n for n in names if len(n) >= 3)
    return Identity(
        school=ours.school or school, mascot=ours.mascot, abbreviation=ours.abbreviation or short_label(ours.school or school),
        conference=ours.conference or conference, color=ours.color, alt_color=ours.alternate_color, team_id=ours.id,
        rivals=tuple(dict.fromkeys(rivals)), resolved=True,
    )


class IdentityService:
    """Holds the current identity; `load` asks CFBD once and tells the listeners."""

    def __init__(self, client: Any, settings: Any) -> None:
        self.client = client
        self.settings = settings
        self.current = Identity.fallback(settings.team, settings.conference)
        self._listeners: list[Any] = []

    def on_change(self, listener: Any) -> None:
        self._listeners.append(listener)
        listener(self.current)

    async def load(self) -> Identity:
        try:
            fetched = await self.client.get("/teams/fbs", {"year": self.settings.season}, kind=DataKind.TEAMS)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("Team identity unavailable (%s); using %r as written", exc, self.settings.team)
            return self.current
        except Exception:  # noqa: BLE001 - the fallback keeps every page working; the failure is logged
            log.exception("Team identity failed unexpectedly; using %r as written", self.settings.team)
            return self.current
        parsed = parse_records(Team, fetched.payload, context="identity /teams/fbs")
        found = identity_from_teams(parsed.records, self.settings.team, self.settings.conference)
        if not found.resolved:
            log.warning("TEAM=%r is not an FBS school in CFBD's list for %s; check the spelling in .env", self.settings.team, self.settings.season)
        self.current = found
        for listener in self._listeners:
            try:
                listener(found)
            except Exception:  # noqa: BLE001 - one listener must not stop the others; it is logged
                log.exception("Identity listener failed")
        return found
