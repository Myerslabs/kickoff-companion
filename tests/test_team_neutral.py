"""Public release Phase 3: nothing in the code names a real team, conference, station or person's
team. The team comes from TEAM in .env and CFBD's team list (app/services/identity.py); examples in
comments use the made-up league or no team at all.

The scan covers the app, the static files, the tools and the tests. It leaves out the private
recordings (tests/fixtures/cfbd/, kept only in the private repo for the shape check) and the two
places that must name real schools to prove the league avoids them.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Real teams, conferences and the old install's own words. Case matters for the short ones.
PATTERN = re.compile(
    r"\b(?:Florida|Gators?|UF|SEC|Gainesville|Ole Miss|Auburn|Missouri|Mizzou|WRUF|Napier|floridagators|Ben Hill Griffin)\b"
    r"|--(?:gator|swamp)\b|\bGATOR_|gators[.:]|gators\.db|\bswamp\b"
    # identifiers and compounds, any case: florida_ppa, GatorsGameDay, OLE_MISS_GAME, AUBURN_GAME
    r"|(?i:\bflorida)|(?i:\bgators?)|(?i:\bole_?miss)|(?i:\bauburn)|(?i:\bmizzou)|(?i:\bmissouri)",
)

# A line may name the old install's words on purpose (a legacy file name it migrates); it says so.
ALLOW = "team-neutral: allowed"

SCANNED = ("app", "static", "tools", "tests", "start.ps1", "start.sh", ".env.example", "pyproject.toml")
SKIPPED_DIRS = {"__pycache__", "fixtures", "fonts", "icons"}
SKIPPED_FILES = {
    "tests/test_team_neutral.py",  # this file names the words it looks for
    "tests/test_demo_league.py",  # checks the league against the real FBS list
}
SUFFIXES = {".py", ".js", ".css", ".html", ".ps1", ".json", ".webmanifest", ".md", ".example", ".txt"}


def files() -> list[Path]:
    out: list[Path] = []
    for name in SCANNED:
        path = ROOT / name
        if path.is_file():
            out.append(path)
            continue
        for f in path.rglob("*"):
            if not f.is_file() or any(part in SKIPPED_DIRS for part in f.relative_to(ROOT).parts):
                continue
            if f.suffix in SUFFIXES or f.name == ".env.example":
                out.append(f)
    return [f for f in out if f.relative_to(ROOT).as_posix() not in SKIPPED_FILES]


def hits() -> list[str]:
    found: list[str] = []
    for f in files():
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if ALLOW in line:
                continue
            for match in PATTERN.finditer(line):
                found.append(f"{f.relative_to(ROOT).as_posix()}:{number}: {match.group(0)}")
    return found


def test_no_real_team_in_the_code():
    found = hits()
    assert found == [], f"{len(found)} mentions, first ones:\n" + "\n".join(found[:40])


if __name__ == "__main__":
    from collections import Counter

    rows = hits()
    for path, count in Counter(r.split(":", 1)[0] for r in rows).most_common():
        print(f"{count:5d}  {path}")
    print(len(rows), "mentions")
