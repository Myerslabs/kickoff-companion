"""The team My Team is about (public release Phase 5b, the layout pass's board 9; batch 3, owner 2026-11-19: "I want to
take out all the secondary teams. The initial idea was to have them so they warm loaded, but now we do that a different
way. Let's just have one team listed, and a change team for the switch").

Until batch 3 this module also held the My teams page (every primary and secondary team's record, ranks and games) and
the warm-up that loaded the primary teams' pages when a device connected (POST /api/myteams/warm). The app knows one
team now (app/services/teamset.py), another team is seen through Change team on one device (static/js/viewing.js), and
the nightly warm (app/services/warm.py) keeps our pages ready, so both are gone. What is left is the line My Team draws
its head from.

    season_picker(chosen, teams, picked) -> {teams, picked, home, allowed, note, plansUrl}
"""

from __future__ import annotations

from typing import Any

from app.cfbd.models import Team
from app.services import plan, teamset


def season_picker(chosen: teamset.TeamSet, teams: list[Team], picked: str) -> dict[str, Any]:
    """My Team's head: our team (the home team), then the team this device changed to when it is another one (role
    "viewing"), each with its abbreviation and colors. With one team there is nothing to add, so no note."""
    meta = {t.school: t for t in teams if isinstance(t, Team) and t.school}

    def row(school: str, role: str | None) -> dict[str, Any]:
        team = meta.get(school)
        return {
            "school": school,
            "abbreviation": team.abbreviation if team else None,
            "color": team.color if team else None,
            "altColor": team.alternate_color if team else None,
            "conference": team.conference if team else None,
            "role": role,
            "known": team is not None or not meta,
        }

    rows = [row(school, chosen.role(school)) for school in chosen.primaries]
    if picked and picked not in [r["school"] for r in rows]:
        rows.append(row(picked, "viewing"))
    return {"teams": rows, "picked": picked, "home": chosen.home, "allowed": chosen.allowed, "note": None, "plansUrl": plan.PLANS_URL}
