"""Build the shipped facts file, app/facts/schools.json, from conference batches (the preloaded facts, owner 2026-10-21).

    .\\.venv\\Scripts\\python tools\\facts_build.py BATCH.json [BATCH.json ...] [--checked 2026-10-21] [--fbs tests/fixtures/cfbd/teams_fbs.json]

Each batch is an answer in the facts prompt's shape (app/services/season_prompts.py read_facts: a conference, its teams,
sources), the way a Claude chat or the research of 2026-10-21 writes it. Every batch is read through the same parser the
app uses for a pasted answer, so a bad row is dropped and counted, never shipped. The teams are merged into the shipped
file (a later batch for the same school replaces the earlier), each school stamped with the checked date and its
conference. With --fbs, the FBS list is checked: a school in the list with no facts is named, a school in a batch that
the list does not know is named too (a misspelling), and the exit code is 1 when any school is missing.

This is the yearly task at the software level: new batches in, the file rebuilt, a release carries it; every install
reads it under its own facts (app/services/season_notes.py shipped_facts)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import season_prompts  # noqa: E402

OUT = ROOT / "app" / "facts" / "schools.json"
FIELDS = ("founded", "stadium", "stadiumNickname", "stadiumOpened", "capacity", "conferenceSince", "firstSeason", "allTimeRecord", "nationalTitles", "conferenceTitles", "conferenceTitleYears", "heismans", "bowlRecord", "rivalries", "headCoachRecord", "winningestCoach", "longestWinStreak", "recordCrowd", "retiredNumbers", "mascotName", "mascotOrigin", "colorsOrigin", "fightSong", "traditions", "nflAlumni", "dates")


def fbs_list(path: Path) -> dict[str, str]:
    """{school: conference} from a /teams/fbs answer (the recorded fixture, or a saved one)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("payload") or raw.get("data") or []
    out: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("school"), str) and row.get("classification", "fbs") == "fbs":
            out[row["school"]] = row.get("conference") or "FBS Independents"
    return out


def _sources_labelled(head: dict) -> dict:
    """A source written as {"title", "url"} becomes the app's {"label", "url"} (the research of 2026-10-21 wrote titles)."""
    def fix(sources):
        out = []
        for source in sources if isinstance(sources, list) else []:
            if isinstance(source, dict) and "label" not in source and isinstance(source.get("title"), str):
                source = {**{k: v for k, v in source.items() if k != "title"}, "label": source["title"]}
            out.append(source)
        return out

    head = {**head, "sources": fix(head.get("sources"))}
    head["teams"] = [{**t, "sources": fix(t.get("sources"))} if isinstance(t, dict) else t for t in (head.get("teams") if isinstance(head.get("teams"), list) else [])]
    return head


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower().removeprefix("the ").removesuffix(" conference"))


def conference_in(fbs: dict[str, str], name: str) -> str | None:
    """The FBS list's spelling of a conference named loosely (a short form, the initials, "the ... Conference"), or None.

    No conference is named here: the loose name's best match is the list's spelling it equals, then the one it begins,
    then the one whose initials (with "Conference" after it) it is, then the one it ends."""
    key = _key(name)
    if not key:
        return None
    best: tuple[int, str] | None = None
    for known in sorted(set(fbs.values()), key=len):
        kk = _key(known)
        initials = "".join(w[0] for w in re.findall(r"[a-z0-9]+", known.lower() + " conference"))
        rank = 0 if key == kk else 1 if len(key) >= 4 and kk.startswith(key) else 2 if key == initials else 3 if len(key) >= 4 and kk.endswith(key) else None
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, known)
    return best[1] if best else None


def read_batch(path: Path, fbs: dict[str, str] | None) -> tuple[str | None, list[dict], list[str]]:
    """(conference, team rows, warnings) of one batch file, through the app's own parser."""
    text = path.read_text(encoding="utf-8-sig")
    try:
        head = json.loads(text)
    except ValueError as exc:
        return None, [], [f"{path.name}: not JSON ({exc})"]
    if isinstance(head, dict):
        text = json.dumps(_sources_labelled(head))
    conference = head.get("conference") if isinstance(head, dict) else None
    if not isinstance(conference, str) or not conference:
        return None, [], [f"{path.name}: no conference named"]
    named = [t.get("school") for t in head.get("teams", []) if isinstance(t, dict) and isinstance(t.get("school"), str)]
    warnings: list[str] = []
    if fbs is None:
        schools = named
    elif known := conference_in(fbs, conference):
        conference = known
        schools = [s for s, c in fbs.items() if c == conference]
    else:
        warnings.append(f"{path.name}: {conference!r} is not a conference in the FBS list; its teams are taken by name")
        schools = [s for s in named if s in fbs]
    reading = season_prompts.read_facts(text, conference, schools)
    if reading.value is None:
        return conference, [], [*warnings, f"{path.name}: {reading.error}"]
    warnings.extend(f"{path.name}: {w}" for w in reading.warnings)
    rows = []
    for team in reading.value.teams:
        dump = team.model_dump(exclude_none=True)
        sources = [s.model_dump(exclude_none=True) for s in (team.sources or reading.value.sources)][:8]
        rows.append({**dump, "sources": sources})
    return conference, rows, warnings


def build(batches: list[Path], checked: str, fbs: dict[str, str] | None, author: str) -> tuple[dict, list[str], int]:
    """(the shipped file's content, warnings, the count of schools missing from the FBS list)."""
    teams: dict[str, dict] = {}
    warnings: list[str] = []
    for path in batches:
        conference, rows, notes = read_batch(path, fbs)
        warnings.extend(notes)
        for row in rows:
            school = row.pop("school")
            if fbs is not None and school not in fbs:
                warnings.append(f"{path.name}: {school!r} is not an FBS school by that spelling; left out")
                continue
            empty = [f for f in FIELDS if row.get(f) in (None, [], "")]
            if len(empty) > len(FIELDS) // 2:
                warnings.append(f"{school}: {len(empty)} of {len(FIELDS)} fields empty ({', '.join(empty[:6])}{'…' if len(empty) > 6 else ''})")
            teams[school] = {**row, "conference": fbs.get(school, conference) if fbs else conference, "checkedAt": checked}
    missing = [s for s in sorted(fbs or {}) if s not in teams]
    for school in missing:
        warnings.append(f"no facts for {school} ({(fbs or {}).get(school)})")
    out = {"format": 1, "checkedAt": checked, "author": author, "schools": len(teams), "teams": dict(sorted(teams.items()))}
    return out, warnings, len(missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("batches", nargs="+", type=Path, help="batch files in the facts prompt's answer shape")
    parser.add_argument("--checked", default=date.today().isoformat(), help="the date the facts were checked (default: today)")
    parser.add_argument("--fbs", type=Path, default=None, help="a /teams/fbs answer to check coverage and spellings against")
    parser.add_argument("--author", default="Claude research", help="who wrote the batches")
    parser.add_argument("--out", type=Path, default=OUT, help=f"where to write (default: {OUT.relative_to(ROOT)})")
    args = parser.parse_args(argv)
    fbs = fbs_list(args.fbs) if args.fbs else None
    out, warnings, missing = build(args.batches, args.checked, fbs, args.author)
    for warning in warnings:
        print("  " + warning)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{args.out}: {out['schools']} schools, checked {args.checked}, {len(warnings)} note(s), {missing} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
