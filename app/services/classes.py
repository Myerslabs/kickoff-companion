"""Class years (Phase 18.4, owner 2026-10-08: "only four classes", a redshirt marked by name). There are four classes,
FR, SO, JR and SR. CFBD's roster `year` runs 1 to 5 and carries no redshirt flag, so a redshirt is inferred:

    year 5 or more              a fifth-year player: SR, redshirt
    recruiting class says more  the player has been on campus more seasons than the class he is listed in: redshirt
    seasons than the class

    class_label(year) -> "FR" | "SO" | "JR" | "SR" | None
    is_redshirt(year, recruit_year, season) -> bool
    class_fields(year, recruit_year, season) -> {"classYear": label, "redshirt": bool}
"""

from __future__ import annotations

from typing import Any

CLASS_NAMES = {1: "FR", 2: "SO", 3: "JR", 4: "SR"}


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def class_label(year: Any) -> str | None:
    number = _whole(year)
    if number is None or number < 1:
        return None
    return CLASS_NAMES.get(min(number, 4))


def is_redshirt(year: Any, recruit_year: Any = None, season: Any = None) -> bool:
    number, recruited, now = _whole(year), _whole(recruit_year), _whole(season)
    if number is None or number < 1:
        return False
    if number >= 5:
        return True
    return recruited is not None and now is not None and recruited <= now and (now - recruited + 1) > number


def class_fields(year: Any, recruit_year: Any = None, season: Any = None) -> dict[str, Any]:
    return {"classYear": class_label(year), "redshirt": is_redshirt(year, recruit_year, season)}


# --- a roster whose classes are unusable (post-freeze Wave 1, 2026-10-25) ------------------------------------------------
# CFBD's 2026 roster for the owner's team lists all 117 players as year 1, so the Roster breakdown called every one a freshman. A roster
# that puts nearly every player in one class is not believed. Each player's class then comes from his recruiting class (the
# season minus the class, plus one: the class of 2023 is in its fourth season in 2026), else from last season's roster as
# CFBD lists it there (its older rosters carry the player's current class, see players.history_classes; on that team's data the
# two agreed for 35 of 36 players), else it is unknown and the player sits outside the grid's classes.

DEGENERATE_MINIMUM = 40  # players; a short roster (a new program, a partial list) is too small to judge
DEGENERATE_SHARE = 0.9  # of the classed players in one class

INFERRED_NOTE = "CFBD lists nearly every player in one class this season, so each class here comes from the player's recruiting class, or from last season's roster."


_SAID: set[tuple[int, str]] = set()


def say_inferred(log: Any, season: int, school: str) -> None:
    """The bug round (2026-11-15): "lists nearly every player in one class" once per school and season in a process, not on
    every roster read (360 lines in two weeks)."""
    key = (int(season), str(school))
    if key in _SAID:
        return
    _SAID.add(key)
    log.warning("CFBD's %s roster for %s lists nearly every player in one class; inferring the classes", season, school)


def degenerate(years: list[Any]) -> bool:
    """True when the roster's class field cannot be believed: nearly every player in one class."""
    values = [n for n in (_whole(y) for y in years) if n is not None and n >= 1]
    if len(values) < DEGENERATE_MINIMUM:
        return False
    top = max(values.count(v) for v in set(values))
    return top / len(values) >= DEGENERATE_SHARE


def inferred_year(prior: Any = None, recruit_year: Any = None, season: Any = None) -> int | None:
    """A player's class number when CFBD's is unusable: from the recruiting class, else last season's roster as listed, else None."""
    last, recruited, now = _whole(prior), _whole(recruit_year), _whole(season)
    if recruited is not None and now is not None and recruited <= now:
        return now - recruited + 1
    if last is not None and last >= 1:
        return last
    return None
