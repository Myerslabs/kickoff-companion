"""The season prompts (Phase 17 Part 3a): the preseason load, one batch per primary team, and the coaches, one batch
per conference. Like the game notes (app/services/notes_paste.py) the app writes the prompt, any AI chat with web
search answers, and the answer is pasted back or comes from Claude Code; both read through answers.read_json and
save through SeasonNotes. Each template is editable in Settings and kept in data/season/PROMPT-<kind>.md.

    TEMPLATES[kind](data_dir)                       the Template for "preseason" or "coaches"
    preseason_prompt(data_dir, school, values)      the filled prompt for one primary team
    coaches_prompt(data_dir, conference, schools, season)
    read_preseason(text, school) / read_coaches(text, conference, schools)  -> Reading
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.answers import Template, keys_score, read_json
from app.services.season_notes import CoachesBatch, CostsBatch, PreseasonFile, PreseasonTeam, SeasonAll

MAX_ANSWER = 400_000
KINDS = ("season", "preseason", "coaches", "costs")

PRESEASON_PROMPT = """You are loading the preseason notes for a college football second-screen app, season {season}, for one team: {school} ({team_name}, {conference}).

Search the web and answer with ONE JSON object in a single ```json code block, nothing else. Use exactly this shape; every field is optional, so leave out what you cannot find, but keep these keys and types:

{shape}

What to fill, for {school} only:
1. "staff": the full coaching staff this season, each person with their role (head coach, coordinators, position coaches, strength coach).
2. "birthdates": every player on this season's roster whose date of birth is published (team bios, recruiting sites, Wikipedia), as YYYY-MM-DD, with jersey number and position. Leave out anyone whose birthdate you cannot find; never estimate one.
3. "departures": who left since last season and why (NFL draft with round, transfer with the new school, graduated, other).
4. "arrivals": who joined (transfers with the old school, notable freshmen with their recruiting standing).
5. "coachingChanges": staff changes since last season.
6. "outlook": a two- or three-sentence "summary" of the season ahead, then "predictions" (preseason polls, projected wins, conference picks, with who predicted them), "positionBattles", and "storylines" (rivalry and trophy games, revenge games, milestones within reach).
7. "injuries": players starting the season injured or suspended, with the status and the expected return.
8. "programFacts": lasting facts a fan enjoys: traditions, records, national titles, notable alumni in the NFL now, the stadium's story.
9. "sources": every page you used, with its real URL.

Rules: never invent a player, a date or a number; leave a list empty when nothing reliable is published. Set "season" to {season}, "author" to the name of the assistant writing it, "writtenAt" to the current UTC time, and the team's "school" to "{school}" exactly. Valid JSON only: no comments, no trailing commas.
"""

SEASON_PROMPT = """You are loading the season for a college football second-screen app, season {season}. One answer does it all: a deep look at the teams the owner follows, and the coaching staff heads of every FBS team.

Search the web and answer with ONE JSON object in a single ```json code block, nothing else, in exactly this shape:

{shape}

PART 1, "teams": one entry for each of these schools, and only these:
{primaries}
For each, fill what you can find; every field is optional, but keep these keys and types:
1. "staff": the full coaching staff this season, each person with their role (head coach, coordinators, position coaches, strength coach).
2. "birthdates": every player on this season's roster whose date of birth is published (team bios, recruiting sites, Wikipedia), as YYYY-MM-DD, with jersey number and position. Leave out anyone whose birthdate you cannot find; never estimate one.
3. "departures": who left since last season and why (NFL draft with round, transfer with the new school, graduated, other).
4. "arrivals": who joined (transfers with the old school, notable freshmen with their recruiting standing).
5. "coachingChanges": staff changes since last season.
6. "outlook": a two- or three-sentence "summary" of the season ahead, then "predictions" (preseason polls, projected wins, conference picks, with who predicted them), "positionBattles", and "storylines" (rivalry and trophy games, revenge games, milestones within reach).
7. "injuries": players starting the season injured or suspended, with the status and the expected return.
8. "programFacts": lasting facts a fan enjoys: traditions, records, national titles, notable alumni in the NFL now, the stadium's story.
9. "sources": every page you used, with its real URL.

PART 2, "coaches": one short row for EVERY school below (the head coach, offensive coordinator and defensive coordinator, by name), nothing else per school. Write each school's name exactly as listed. Where a team has co-coordinators, name both separated by " and "; where the head coach also calls the plays, still name the coordinator of record. Leave a name out rather than guess.
{schools}

Rules: never invent a player, a date or a number; leave a list empty when nothing reliable is published. Set "season" to {season}, "author" to the name of the assistant writing it, "writtenAt" to the current UTC time, and give every page you used in the top-level "sources" with its real URL. Valid JSON only: no comments, no trailing commas.
"""

COACHES_PROMPT = """You are loading the coaching staffs for a college football second-screen app, season {season}, for the {conference}.

Search the web and answer with ONE JSON object in a single ```json code block, nothing else, in exactly this shape:

{shape}

For each of these schools, the current head coach, offensive coordinator and defensive coordinator, by name:
{schools}

Write each school's name exactly as listed. Where a team has co-coordinators, name both separated by " and "; where the head coach also calls the plays, still name the coordinator of record. Leave a name out rather than guess. Set "conference" to "{conference}", "season" to {season}, "author" to the name of the assistant writing it, and list every page you used in "sources" with its real URL. Valid JSON only: no comments, no trailing commas.
"""


COSTS_PROMPT = """You are loading rumored roster costs for a college football second-screen app, season {season}, for the {conference}: what each program is reported to spend on its players through revenue sharing and NIL.

Keep the search shallow: a few minutes of reading recent news reports and NIL valuation sites, not an investigation. Rumored and estimated figures are fine; say so in the note. Leave a figure out rather than invent one.

Answer with ONE JSON object in a single ```json code block, nothing else, in exactly this shape:

{shape}

For each of these schools, "totalUsd": the rumored total for this season's roster, in whole US dollars, with a short "note" on what it covers and "asOf" the date of the report:
{schools}

For these schools only, also fill "positions" (rumored spending by position group) and "players" (individual players with a reported or estimated value), where any are reported:
{detailed}

Write each school's name exactly as listed. Set "conference" to "{conference}", "season" to {season}, "author" to the name of the assistant writing it, and give every page you used in "sources" with its real URL. Valid JSON only: no comments, no trailing commas.
"""


def costs_shape(conference: str, school: str) -> str:
    example = {
        "conference": conference,
        "season": 2026,
        "author": "Assistant name",
        "teams": [{
            "school": school,
            "totalUsd": 20500000,
            "note": "Revenue-sharing cap plus reported collective NIL, rumored",
            "asOf": "2026-08-01",
            "positions": [{"group": "Quarterbacks", "amountUsd": 4000000, "note": "reported"}],
            "players": [{"name": "Player Name", "position": "QB", "amountUsd": 2500000, "note": "NIL valuation site estimate"}],
            "sources": [{"label": "Where the figure was reported", "url": "https://..."}],
        }],
        "sources": [{"label": "A report covering the conference", "url": "https://..."}],
    }
    return json.dumps(example, indent=2)


def costs_prompt(data_dir: Path, *, conference: str, schools: list[str], detailed: list[str], season: int) -> str:
    listing = "\n".join(f"- {s}" for s in schools)
    detail = "\n".join(f"- {s}" for s in detailed) if detailed else "- (none in this conference)"
    return template("costs", data_dir).fill({"season": season, "conference": conference, "schools": listing, "detailed": detail, "shape": costs_shape(conference, schools[0] if schools else "School")})


def read_costs(text: Any, conference: str, schools: list[str]) -> Reading:
    parsed = read_json(text, CostsBatch, keys_score(("teams", "conference")), max_chars=MAX_ANSWER, what="a roster-costs batch", keys_text="teams or conference")
    if parsed.value is None:
        return Reading(None, error=parsed.error)
    batch: CostsBatch = parsed.value
    warnings = list(parsed.warnings)
    if not batch.teams:
        return Reading(None, warnings=warnings, error="The answer lists no teams.")
    wanted = {s.lower() for s in schools}
    named = [t.school for t in batch.teams]
    unknown = [n for n in named if n.strip().lower() not in wanted]
    if unknown:
        warnings.append(f"Not in the {conference}, so left out: {', '.join(unknown[:6])}{'…' if len(unknown) > 6 else ''}.")
    if len(unknown) == len(named):
        return Reading(None, warnings=warnings, error=f"None of the teams in the answer is in the {conference}.")
    figures = sum(1 for t in batch.teams if t.totalUsd is not None and t.school.strip().lower() in wanted)
    if not figures:
        warnings.append("No team total was found; saved anyway, so the page shows they were looked for.")
    if not batch.sources and not any(t.sources for t in batch.teams):
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    return Reading(batch, {"conference": conference, "teams": len(named) - len(unknown), "of": len(schools), "totals": figures}, warnings)


def preseason_shape(school: str) -> str:
    example = {
        "season": 2026,
        "author": "Assistant name",
        "writtenAt": "2026-08-01T12:00:00Z",
        "teams": [{
            "school": school,
            "staff": [{"name": "Coach Name", "role": "Head coach"}, {"name": "Coach Name", "role": "Offensive line coach"}],
            "birthdates": [{"name": "Player Name", "number": 12, "position": "QB", "born": "2005-04-17"}],
            "departures": [{"name": "Player Name", "position": "WR", "kind": "NFL draft", "detail": "Round 2, pick 40"}],
            "arrivals": [{"name": "Player Name", "position": "LB", "kind": "Transfer", "detail": "From Other School"}],
            "coachingChanges": [{"title": "New defensive coordinator", "detail": "Who, and from where"}],
            "outlook": {"summary": "Two or three sentences.", "predictions": [{"title": "Preseason AP poll", "detail": "No. 18"}], "positionBattles": [{"title": "Quarterback", "detail": "Who is competing"}], "storylines": [{"title": "Rivalry game", "detail": "Why it matters this year"}]},
            "injuries": [{"name": "Player Name", "position": "RB", "status": "Out for the season", "detail": "knee", "expectedReturn": "2027"}],
            "programFacts": [{"title": "A tradition", "detail": "One or two sentences."}],
            "sources": [{"label": "Team roster", "url": "https://..."}],
        }],
    }
    return json.dumps(example, indent=2)


def coaches_shape(conference: str, school: str) -> str:
    example = {
        "conference": conference,
        "season": 2026,
        "author": "Assistant name",
        "teams": [{"school": school, "headCoach": "Name", "offensiveCoordinator": "Name", "defensiveCoordinator": "Name"}],
        "sources": [{"label": "Where the staff is listed", "url": "https://..."}],
    }
    return json.dumps(example, indent=2)


def season_shape(primary: str, school: str) -> str:
    one = json.loads(preseason_shape(primary))
    example = {**one, "coaches": [{"school": school, "headCoach": "Name", "offensiveCoordinator": "Name", "defensiveCoordinator": "Name"}], "sources": [{"label": "Where the staffs are listed", "url": "https://..."}]}
    return json.dumps(example, indent=2)


def template(kind: str, data_dir: Path) -> Template:
    folder = Path(data_dir) / "season"
    if kind == "season":
        return Template(folder / "PROMPT-season.md", SEASON_PROMPT, ("season", "primaries", "schools", "shape"), required="primaries")
    if kind == "preseason":
        return Template(folder / "PROMPT-preseason.md", PRESEASON_PROMPT, ("season", "school", "team_name", "conference", "shape"), required="school")
    if kind == "coaches":
        return Template(folder / "PROMPT-coaches.md", COACHES_PROMPT, ("season", "conference", "schools", "shape"), required="schools")
    if kind == "costs":
        return Template(folder / "PROMPT-costs.md", COSTS_PROMPT, ("season", "conference", "schools", "detailed", "shape"), required="schools")
    raise ValueError(f"no season prompt {kind!r}")


def preseason_prompt(data_dir: Path, *, school: str, team_name: str | None, conference: str | None, season: int) -> str:
    return template("preseason", data_dir).fill({"season": season, "school": school, "team_name": team_name or school, "conference": conference or "its conference", "shape": preseason_shape(school)})


def season_prompt(data_dir: Path, *, primaries: list[str], conferences: dict[str, list[str]], season: int) -> str:
    listing = "\n".join(f"- {s}" for s in primaries) or "- (none)"
    schools = "\n".join(f"{conference}: " + "; ".join(names) for conference, names in sorted(conferences.items()))
    first = next(iter(next(iter(conferences.values()), [])), "School")
    return template("season", data_dir).fill({"season": season, "primaries": listing, "schools": schools, "shape": season_shape(primaries[0] if primaries else "School", first)})


def coaches_prompt(data_dir: Path, *, conference: str, schools: list[str], season: int) -> str:
    listing = "\n".join(f"- {s}" for s in schools)
    return template("coaches", data_dir).fill({"season": season, "conference": conference, "schools": listing, "shape": coaches_shape(conference, schools[0] if schools else "School")})


# --- reading the answers ---------------------------------------------------------------------------------


@dataclass
class Reading:
    value: Any | None
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.value is not None, "summary": self.summary, "warnings": self.warnings, "error": self.error}


def read_preseason(text: Any, school: str) -> Reading:
    """The one team this batch asked for. An answer that names it differently, or holds only another team, still
    counts when it holds exactly one team (saved under the asked name, with a warning)."""
    parsed = read_json(text, PreseasonFile, keys_score(("teams", "season", "author")), max_chars=MAX_ANSWER, what="a preseason load", keys_text="teams")
    if parsed.value is None:
        return Reading(None, error=parsed.error)
    file: PreseasonFile = parsed.value
    warnings = list(parsed.warnings)
    team: PreseasonTeam | None = next((t for t in file.teams if t.school.strip().lower() == school.lower()), None)
    if team is None and len(file.teams) == 1:
        team = file.teams[0]
        warnings.append(f'The answer is for "{team.school}", not {school}. Saving puts it on {school}.')
    if team is None:
        return Reading(None, warnings=warnings, error=f"The answer has no team named {school}." if file.teams else "The answer has no team in it.")
    counts = {k: len(getattr(team, k)) for k in ("staff", "birthdates", "departures", "arrivals", "coachingChanges", "injuries", "programFacts", "sources")}
    if not any(v for k, v in counts.items() if k != "sources") and not (team.outlook and (team.outlook.summary or team.outlook.predictions)):
        return Reading(None, {"counts": counts}, warnings, "The answer has nothing in it for this team.")
    if not team.sources:
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    if not team.birthdates:
        warnings.append("No birthdates were found, so this team's players show no ages.")
    return Reading(team, {"school": school, "author": file.author, "counts": counts}, warnings)


def read_season(text: Any, primaries: list[str], conferences: dict[str, list[str]]) -> Reading:
    """The one-paste answer split into what the page keeps: a PreseasonTeam for each primary team the answer names, and
    a CoachesBatch for each conference (only schools CFBD lists). Value: {"teams": {school: PreseasonTeam}, "coaches": {conference: CoachesBatch}}."""
    parsed = read_json(text, SeasonAll, keys_score(("teams", "coaches", "season")), max_chars=MAX_ANSWER, what="a season load", keys_text="teams or coaches")
    if parsed.value is None:
        return Reading(None, error=parsed.error)
    file: SeasonAll = parsed.value
    warnings = list(parsed.warnings)
    wanted = {p.lower(): p for p in primaries}
    teams: dict[str, PreseasonTeam] = {}
    for team in file.teams:
        school = wanted.get(team.school.strip().lower())
        if school is None:
            warnings.append(f"{team.school} is not one of your primary teams, so it is left out.")
        elif any(getattr(team, k) for k in ("staff", "birthdates", "departures", "arrivals", "coachingChanges", "injuries", "programFacts")) or (team.outlook and (team.outlook.summary or team.outlook.predictions)):
            teams[school] = team
        else:
            warnings.append(f"{school} came back empty.")
    missing_teams = [p for p in primaries if p not in teams]
    if missing_teams:
        warnings.append(f"No preseason load for {', '.join(missing_teams)}.")
    index = {s.lower(): (conference, s) for conference, names in conferences.items() for s in names}
    by_conference: dict[str, list[Any]] = {}
    for row in file.coaches:
        hit = index.get(row.school.strip().lower())
        if hit is not None and any((row.headCoach, row.offensiveCoordinator, row.defensiveCoordinator)):
            by_conference.setdefault(hit[0], []).append(row)
    coaches = {conference: CoachesBatch(conference=conference, season=file.season, author=file.author, teams=rows, sources=file.sources) for conference, rows in by_conference.items()}
    named = sum(len(rows) for rows in by_conference.values())
    total = sum(len(names) for names in conferences.values())
    if not teams and not named:
        return Reading(None, warnings=warnings, error="The answer has no usable team or coaches in it.")
    if named < total:
        warnings.append(f"Coaches for {named} of {total} teams; the rest stay empty until another load.")
    if not file.sources and not any(t.sources for t in teams.values()):
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    return Reading({"teams": teams, "coaches": coaches}, {"teams": len(teams), "coachTeams": named, "of": total, "author": file.author}, warnings)


def read_coaches(text: Any, conference: str, schools: list[str]) -> Reading:
    parsed = read_json(text, CoachesBatch, keys_score(("teams", "conference")), max_chars=MAX_ANSWER, what="a coaches batch", keys_text="teams or conference")
    if parsed.value is None:
        return Reading(None, error=parsed.error)
    batch: CoachesBatch = parsed.value
    warnings = list(parsed.warnings)
    if not batch.teams:
        return Reading(None, warnings=warnings, error="The answer lists no teams.")
    wanted = {s.lower() for s in schools}
    named = [t.school for t in batch.teams]
    unknown = [n for n in named if n.strip().lower() not in wanted]
    missing = [s for s in schools if s.lower() not in {n.strip().lower() for n in named}]
    if unknown:
        warnings.append(f"Not in the {conference}, so left out: {', '.join(unknown[:6])}{'…' if len(unknown) > 6 else ''}.")
    if missing:
        warnings.append(f"No staff for {', '.join(missing[:6])}{'…' if len(missing) > 6 else ''}.")
    if isinstance(batch.conference, str) and batch.conference.strip() and batch.conference.strip().lower() != conference.lower():
        warnings.append(f'The answer says "{batch.conference}"; saving it as the {conference}.')
    if len(unknown) == len(named):
        return Reading(None, warnings=warnings, error=f"None of the teams in the answer is in the {conference}.")
    if not batch.sources:
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    return Reading(batch, {"conference": conference, "teams": len(named) - len(unknown), "of": len(schools)}, warnings)
