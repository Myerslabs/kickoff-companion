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
