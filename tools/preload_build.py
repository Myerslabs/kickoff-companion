"""Build the shipped season files from research batches (the preloading, owner 2026-10-22: "the preloaded data should show
its date from the data that gets downloaded with the program").

    .\\.venv\\Scripts\\python tools\\preload_build.py FOLDER [--checked 2026-10-22] [--season 2026] [--fbs tests/fixtures/cfbd/teams_fbs.json]

FOLDER holds the research answers in the prompts' own shapes: coaches-<conference>.json (a coaches batch), costs-<conference>.json
(a roster-costs batch) and season-*.json (a season load: {"season", "teams": [a preseason team each]}). Each coaches and
costs batch is read through the parser the app uses for a pasted answer (app/services/season_prompts.py), each season team
through the PreseasonTeam model, so a bad row is dropped and counted, never shipped. A school is matched to the FBS list
the way CFBD spells it (case and accents aside). The files written, every row stamped with the checked date and its
conference:

    app/facts/coaches.json      every FBS team's head coach and coordinators
    app/facts/costs.json        every FBS team's rumored roster costs (a team with no reported total is left out)
    app/facts/preseason.json    every FBS team's season load (staff, moves, coaching changes, outlook, injuries; no birthdates)

Each file carries its season: an install reads it only for that season (app/services/season_notes.py shipped_for_season), under
its own loads. With --fbs, the schools still missing from each file are named; the exit code is 1 when the coaches miss any."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from facts_build import fbs_list  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.services import season_prompts  # noqa: E402
from app.services.season_notes import SHIPPED_COACHES, SHIPPED_COSTS, SHIPPED_PRESEASON, PreseasonTeam  # noqa: E402

AUTHOR = "Claude research"


def fold(name: str) -> str:
    """A school's name for matching: no accents, no case, one kind of apostrophe, single spaces."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", plain.replace("’", "'").replace("ʻ", "'")).strip().lower()


def conference_of(path: Path, conferences: dict[str, list[str]]) -> str | None:
    """The conference a batch file names: its "conference" field, else its file name's slug."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    named = raw.get("conference") if isinstance(raw, dict) else None
    slug = path.stem.split("-", 1)[1] if "-" in path.stem else ""
    for conference in conferences:
        if isinstance(named, str) and fold(named) == fold(conference):
            return conference
        if slug and slug == re.sub(r"[^a-z0-9]+", "-", conference.lower()).strip("-"):
            return conference
    return None


def write(path: Path, season: int, checked: str, teams: dict[str, dict]) -> None:
    body = {"format": 1, "season": season, "checkedAt": checked, "author": AUTHOR, "schools": len(teams), "teams": dict(sorted(teams.items()))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--checked", default=date.today().isoformat(), help="the date the research was checked (YYYY-MM-DD)")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--fbs", type=Path, default=ROOT / "tests" / "fixtures" / "cfbd" / "teams_fbs.json")
    parser.add_argument("--out", type=Path, default=None, help="a folder to write the three files to instead of app/facts")
    args = parser.parse_args(argv)
    fbs = fbs_list(args.fbs)
    conferences: dict[str, list[str]] = {}
    for school, conference in fbs.items():
        conferences.setdefault(conference, []).append(school)
    by_fold = {fold(s): s for s in fbs}
    out = {"coaches": args.out / "coaches.json" if args.out else SHIPPED_COACHES, "costs": args.out / "costs.json" if args.out else SHIPPED_COSTS, "preseason": args.out / "preseason.json" if args.out else SHIPPED_PRESEASON}

    coaches: dict[str, dict] = {}
    costs: dict[str, dict] = {}
    dropped = 0
    for kind in ("coaches", "costs"):
        for path in sorted(args.folder.glob(f"{kind}-*.json")):
            conference = conference_of(path, conferences)
            if conference is None:
                print(f"  {path.name}: no FBS conference by that name, skipped")
                continue
            schools = conferences[conference]
            text = path.read_text(encoding="utf-8-sig")
            reading = season_prompts.read_coaches(text, conference, schools) if kind == "coaches" else season_prompts.read_costs(text, conference, schools)
            if reading.value is None:
                print(f"  {path.name}: {reading.error}")
                continue
            batch = reading.value
            for row in batch.teams:
                school = by_fold.get(fold(row.school))
                if school is None or fbs.get(school) != conference:
                    dropped += 1
                    continue
                sources = [s.model_dump(exclude_none=True) for s in (getattr(row, "sources", None) or batch.sources)][:6]
                if kind == "coaches":
                    if not any((row.headCoach, row.offensiveCoordinator, row.defensiveCoordinator)):
                        continue
                    coaches[school] = {"conference": conference, "headCoach": row.headCoach, "offensiveCoordinator": row.offensiveCoordinator, "defensiveCoordinator": row.defensiveCoordinator, "checkedAt": args.checked, "sources": sources}
                else:
                    if row.totalUsd is None and not row.positions and not row.players:
                        continue  # nothing reported: the team stays not loaded rather than a row of blanks
                    dump = row.model_copy(update={"school": school, "sources": [s for s in (row.sources or batch.sources)][:6]}).model_dump(exclude_none=True)
                    costs[school] = {**dump, "conference": conference, "checkedAt": args.checked}
            for warning in reading.warnings:
                print(f"  {path.name}: {warning}")

    preseason: dict[str, dict] = {}
    for path in sorted(args.folder.glob("season-*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            print(f"  {path.name}: not JSON ({exc}), skipped")
            continue
        rows = raw.get("teams") if isinstance(raw, dict) and isinstance(raw.get("teams"), list) else []
        for value in rows:
            if not isinstance(value, dict) or not isinstance(value.get("school"), str):
                dropped += 1
                continue
            school = by_fold.get(fold(value["school"]))
            if school is None:
                print(f"  {path.name}: {value['school']!r} is not an FBS school, skipped")
                dropped += 1
                continue
            try:
                team = PreseasonTeam.model_validate({**value, "school": school, "birthdates": []})
            except ValidationError as exc:
                print(f"  {path.name}: {school} did not read ({exc.errors()[0].get('msg') if exc.errors() else exc}), skipped")
                dropped += 1
                continue
            preseason[school] = {**team.model_dump(mode="json", exclude_none=True), "conference": fbs[school], "checkedAt": args.checked}

    for kind, teams in (("coaches", coaches), ("costs", costs), ("preseason", preseason)):
        if teams:
            write(out[kind], args.season, args.checked, teams)
        missing = sorted(s for s in fbs if s not in teams)
        print(f"{kind}: {len(teams)} of {len(fbs)} FBS schools{f'; missing: {", ".join(missing[:12])}{"…" if len(missing) > 12 else ""}' if missing else ''}")
    if dropped:
        print(f"{dropped} row(s) dropped (not an FBS school of that conference, or damaged)")
    return 1 if len(coaches) < len(fbs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
