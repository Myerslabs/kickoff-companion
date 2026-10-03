"""Who "my teams" are (public release Phase 5b). Pure functions over the saved settings and CFBD's FBS list;
nothing here fetches.

- Primary #1, the home team: TEAM in .env. The Season page, the Game program and the Live sheet follow it,
  and only its colors and mascot theme the app.
- Primaries #2 to #5 (a Tier 2 key): `primaryTeams` in the settings. Their team pages load as soon as a
  device connects (POST /api/myteams/warm) and sit one tap away in the menu.
- Secondary teams (a Tier 2 key): `likedTeams`, plus every FBS school in `likedConferences` and in
  `likedStates`. Nothing is loaded for them until a page asks.

Primaries and secondaries together fill the My teams ticker, the My teams page and the "My teams" scope of a
ranked list. With a free key the set is the home team alone; saved picks stay in the settings (`locked`)
and come back with a Tier 2 key."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.cfbd.models import Game, Team
from app.services import gamekeys, plan

HOME = "home"
PRIMARY = "primary"
SECONDARY = "secondary"


def state_of(team: Team) -> str | None:
    """The state a school plays in, as CFBD's /teams/fbs location gives it (a postal code)."""
    location = team.location if isinstance(team.location, dict) else None
    value = location.get("state") if location else None
    return value.strip() if isinstance(value, str) and value.strip() else None


@dataclass(frozen=True)
class TeamSet:
    home: str
    primaries: tuple[str, ...]  # the home team first, then #2 to #5
    secondary: tuple[str, ...]  # every secondary school, primaries left out
    why: dict[str, tuple[str, ...]] = field(default_factory=dict)  # school -> what put it in the set
    allowed: bool = False  # the key allows more than the home team (Tier 2)
    locked: dict[str, int] = field(default_factory=dict)  # saved picks the key leaves out, counted by kind

    @property
    def extra(self) -> tuple[str, ...]:
        """Primaries #2 to #5."""
        return self.primaries[1:]

    def mine(self) -> frozenset[str]:
        return frozenset(self.primaries) | frozenset(self.secondary)

    def role(self, school: str | None) -> str | None:
        if not school:
            return None
        if school == self.home:
            return HOME
        if school in self.primaries:
            return PRIMARY
        if school in self.secondary:
            return SECONDARY
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "home": self.home,
            "primaries": list(self.primaries),
            "extraPrimaries": list(self.extra),
            "secondary": list(self.secondary),
            "allowed": self.allowed,
            "locked": dict(self.locked),
        }


def _clean(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in out:
            out.append(value.strip())
    return out


def resolve(home: str, prefs: Any, allowed: bool, teams: list[Team] | None = None) -> TeamSet:
    """The team set for the saved settings. `teams` (CFBD's FBS list) spells the names as CFBD does and
    expands liked conferences and states; without it the saved names are used as they are and no
    conference or state can be expanded."""
    extra = _clean(getattr(prefs, "primaryTeams", []) or [])
    liked = _clean(getattr(prefs, "likedTeams", []) or [])
    conferences = _clean(getattr(prefs, "likedConferences", []) or [])
    states = _clean(getattr(prefs, "likedStates", []) or [])
    if not allowed:
        locked = {k: v for k, v in (("primaries", len(extra)), ("teams", len(liked)), ("conferences", len(conferences)), ("states", len(states))) if v}
        return TeamSet(home, (home,) if home else (), (), {home: ("Home team",)} if home else {}, False, locked)

    fbs = [t for t in (teams or []) if isinstance(t.school, str) and t.school.strip()]
    by_lower = {t.school.lower(): t.school for t in fbs}

    def spell(name: str) -> str:
        return by_lower.get(name.lower(), name)

    why: dict[str, list[str]] = {}
    primaries: list[str] = [home] if home else []
    if home:
        why[home] = ["Home team"]
    for name in extra:
        school = spell(name)
        if school.lower() not in {p.lower() for p in primaries}:
            primaries.append(school)
            why.setdefault(school, []).append("Primary team")
    primaries = primaries[:5]

    secondary: list[str] = []

    taken = {p.lower() for p in primaries}  # without CFBD's list, saved names still match case-blind

    def add(school: str, reason: str) -> None:
        if school.lower() in taken:
            return
        if school.lower() not in {s.lower() for s in secondary}:
            secondary.append(school)
        reasons = why.setdefault(school, [])
        if reason not in reasons:
            reasons.append(reason)

    for name in liked:
        add(spell(name), "Liked school")
    conf_set = {c.lower(): c for c in conferences}
    state_set = {s.lower(): s for s in states}
    for team in sorted(fbs, key=lambda t: t.school.lower()):
        conference = team.conference if isinstance(team.conference, str) else None
        if conference and conference.lower() in conf_set:
            add(team.school, conference)
        state = state_of(team)
        if state and state.lower() in state_set:
            add(team.school, state)
    return TeamSet(home, tuple(primaries), tuple(secondary), {k: tuple(v) for k, v in why.items()}, True, {})


def current(settings: Any, prefs_store: Any, client: Any, teams: list[Team] | None = None) -> TeamSet:
    """The team set right now: the home team from the settings, the picks from data/settings.json, and
    the key's plan. With no settings store (a bare service in a test) the home team stands alone."""
    prefs = getattr(prefs_store, "prefs", None)
    return resolve(settings.team, prefs, plan.allows_liked(client.capabilities), teams)


def opponents(games: Iterable[Game], team: str) -> list[str]:
    """Every opponent on a team's schedule, in schedule order (the ranked list's opponents scope)."""
    out: list[str] = []
    for game in sorted((g for g in games if isinstance(g, Game) and g.week is not None), key=gamekeys.order):
        other = gamekeys.opponent_of(game, team)
        if other and other not in out:
            out.append(other)
    return out
