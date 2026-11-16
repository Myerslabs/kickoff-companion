"""Build the Imperialism Map's two fixed inputs (FEAT-17, Feature Set v2 Phase B), once, from the federal files the owner
approved downloading on 2026-10-30. Nothing here runs with the app; the outputs are committed.

    .\\.venv\\Scripts\\python tools\\imperialism_build.py grid --census cb_2024_us_state_20m.zip
        app/facts/imperialism/grid.json: about 12,000 hexagons over the lower 48 and Hawaii (app/services/imperialism_grid.py)

    .\\.venv\\Scripts\\python tools\\imperialism_build.py enrollment --hd HD2023.zip --ef EF2023A.zip
        app/facts/imperialism/enrollment.csv: one row per school in app/facts/team_aliases.csv, the campus's total fall
        headcount (IPEDS EF2023A, EFALEVEL 1, EFTOTLT), with a note wherever a choice was made between a system and a campus

The alias file (cfbd_school, alias, state, ipeds_unitid) is the reviewed match of CFBD's school names to IPEDS campuses;
a school with no row, an id IPEDS does not have, or a name that no longer matches the id stops the build with its name.
The Census file: https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_state_20m.zip. IPEDS:
https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip and EF2023A.zip. Exit 1 names what is wrong."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.imperialism_grid import DEFAULT_PATH as GRID_PATH  # noqa: E402
from app.services.imperialism_grid import build_grid, read_states  # noqa: E402

ALIASES = ROOT / "app" / "facts" / "team_aliases.csv"
ENROLLMENT = ROOT / "app" / "facts" / "imperialism" / "enrollment.csv"
SOURCE_YEAR = 2023

# Every school where a choice was made between a system and a campus, or where the count is not what "students on a
# campus" suggests (the spec: list each judgment call for the owner's review).
NOTES = {
    "Liberty": "IPEDS counts Liberty as one campus, and most of its students study only online; all are counted here.",
    "Arizona State": "Campus Immersion only; ASU Digital Immersion (online) is its own IPEDS unit and is left out.",
    "Florida": "University of Florida only; UF Online (5,462) is its own IPEDS unit and is left out.",
    "Penn State": "University Park (Main Campus) only; the Commonwealth campuses and World Campus are separate units.",
    "Texas A&M": "IPEDS reports College Station with the Galveston, Qatar and Health Science Center students in one unit.",
    "South Florida": "One unit since the 2020 consolidation of Tampa, St. Petersburg and Sarasota-Manatee.",
    "UConn": "IPEDS reports Storrs with the regional campuses (Stamford, Hartford, Waterbury, Avery Point) in one unit.",
    "Pittsburgh": "Pittsburgh campus only; Bradford, Greensburg, Johnstown and Titusville are separate units.",
    "Purdue": "West Lafayette only; Purdue Global (online) and the Fort Wayne and Northwest campuses are separate units.",
    "Maryland": "College Park only; University of Maryland Global Campus (online) is its own unit.",
    "Ohio State": "Columbus only; the regional campuses are separate units.",
    "Rutgers": "New Brunswick only; Newark and Camden are separate units.",
    "Cincinnati": "Main campus only; Blue Ash and Clermont are separate units.",
    "Kent State": "Kent campus only; the regional campuses are separate units.",
    "South Carolina": "Columbia only; the other campuses are separate units.",
    "Air Force": "Cadets of the Air Force Academy.",
    "Army": "Cadets of the Military Academy.",
    "Navy": "Midshipmen of the Naval Academy.",
}


def _rows(path: Path, name: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="latin-1")))
    for row in rows:
        row["UNITID"] = next((v for k, v in row.items() if k.endswith("UNITID")), "").strip().strip("'")
    return rows


def _member(path: Path, suffix: str) -> str:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(suffix)]
    if len(names) != 1:
        raise SystemExit(f"{path.name}: expected one {suffix} file inside, found {names}")
    return names[0]


def grid(args: argparse.Namespace) -> int:
    with zipfile.ZipFile(args.census) as z:
        kml = z.read(_member(Path(args.census), ".kml")).decode("utf-8")
    built = build_grid(read_states(kml), target=args.target)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"{out}: {built['count']} cells ({built['lower48']} in the lower 48, {built['hawaii']} in Hawaii), side {built['side']}")
    return 0


def enrollment(args: argparse.Namespace) -> int:
    hd = {r["UNITID"]: r for r in _rows(Path(args.hd), _member(Path(args.hd), ".csv"))}
    ef = {}
    for r in _rows(Path(args.ef), _member(Path(args.ef), ".csv")):
        if r.get("EFALEVEL", "").strip().strip("'") == "1":
            total = r.get("EFTOTLT", "").strip().strip("'")
            if total.isdigit():
                ef[r["UNITID"]] = int(total)
    with open(ALIASES, encoding="utf-8", newline="") as f:
        aliases = list(csv.DictReader(f))
    problems = []
    rows = []
    for a in sorted(aliases, key=lambda r: r["cfbd_school"]):
        school, unitid = a["cfbd_school"], a["ipeds_unitid"].strip()
        inst = hd.get(unitid)
        if inst is None:
            problems.append(f"{school}: IPEDS has no unit {unitid}")
            continue
        if inst["INSTNM"] != a["alias"]:
            problems.append(f"{school}: unit {unitid} is now named {inst['INSTNM']!r}, the alias file says {a['alias']!r}")
            continue
        total = ef.get(unitid)
        if total is None or total < 1000:
            problems.append(f"{school}: no fall total of 1,000 or more for unit {unitid} ({total})")
            continue
        rows.append([school, total, f"IPEDS EF2023A total fall headcount, unit {unitid} ({inst['INSTNM']})", SOURCE_YEAR, NOTES.get(school, "")])
    missing = sorted(set(NOTES) - {a["cfbd_school"] for a in aliases})
    problems.extend(f"{name}: a note for a school with no alias row" for name in missing)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cfbd_school", "enrollment", "source", "source_year", "note"])
        w.writerows(rows)
    print(f"{out}: {len(rows)} schools, {sum(r[1] for r in rows):,} students; {sum(1 for r in rows if r[4])} with a note")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools/imperialism_build.py", description="Build the Imperialism Map's grid and enrollment table from the federal files.")
    sub = parser.add_subparsers(dest="what", required=True)
    g = sub.add_parser("grid", help="the hex grid from the Census state outlines")
    g.add_argument("--census", required=True, help="cb_2024_us_state_20m.zip (the KML inside)")
    g.add_argument("--target", type=int, default=12000, help="cells in the lower 48 (default 12,000)")
    g.add_argument("--out", default=str(GRID_PATH))
    e = sub.add_parser("enrollment", help="the enrollment table from IPEDS")
    e.add_argument("--hd", required=True, help="HD2023.zip, the IPEDS directory")
    e.add_argument("--ef", required=True, help="EF2023A.zip, the IPEDS fall enrollment")
    e.add_argument("--out", default=str(ENROLLMENT))
    args = parser.parse_args(argv)
    return grid(args) if args.what == "grid" else enrollment(args)


if __name__ == "__main__":
    raise SystemExit(main())
