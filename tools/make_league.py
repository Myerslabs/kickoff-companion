r"""The made-up league's developer tool (public release Phase 2).

    .\.venv\Scripts\python tools\make_league.py --check
        Build the league (cached in data/demo/) and check every twin of a recorded fixture against
        the shapes in tests/fixtures/league/shapes.json. Prints each problem; exit code 1 if any.

    .\.venv\Scripts\python tools\make_league.py --out data\demo\fixtures
        Write every twin as JSON, in the recorded envelope, to look at.

    .\.venv\Scripts\python tools\make_league.py --signatures
        Private repo only: rebuild tests/fixtures/league/shapes.json from the recordings in
        tests/fixtures/cfbd/. The shapes keep field names and JSON types, never a value.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.demo.fixtures import RECORDINGS, league_fixture, roles  # noqa: E402
from app.demo.shapes import compare, shape_of  # noqa: E402
from app.demo.upstream import load_world  # noqa: E402

RECORDED = ROOT / "tests" / "fixtures" / "cfbd"
SHAPES = ROOT / "tests" / "fixtures" / "league" / "shapes.json"
CACHE = ROOT / "data" / "demo"


def signatures() -> int:
    if not RECORDED.is_dir():
        print(f"No recordings at {RECORDED}: this only runs in the private repo.", file=sys.stderr)
        return 1
    out: dict[str, dict] = {}
    for path in sorted(RECORDED.glob("*.json")):
        if path.stem == "MANIFEST" or path.stem not in RECORDINGS:
            continue
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope.get("payload")
        out[path.stem] = {"endpoint": envelope.get("endpoint"), "status": envelope.get("status"),
                          "empty": payload in (None, [], {}), "shape": shape_of(payload)}
    missing = sorted(set(RECORDINGS) - set(out))
    SHAPES.parent.mkdir(parents=True, exist_ok=True)
    SHAPES.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} shapes to {SHAPES}" + (f"; no recording for {missing}" if missing else ""))
    return 0


def check(verbose: bool = True) -> list[str]:
    shapes = json.loads(SHAPES.read_text(encoding="utf-8"))
    world = load_world(cache_dir=CACHE)
    values = roles(world)
    problems: list[str] = []
    for name, spec in sorted(shapes.items()):
        twin = league_fixture(world, name, values=values)
        if twin["status"] != spec["status"]:
            problems.append(f"{name}: status {twin['status']}, CFBD answered {spec['status']}")
            continue
        payload = twin["payload"]
        if spec["empty"] or payload in (None, [], {}):
            if not spec["empty"] and payload in (None, [], {}):
                problems.append(f"{name}: empty, CFBD sent data")
            continue
        for p in compare(spec["shape"], shape_of(payload)):
            problems.append(f"{name}: {p}")
    if verbose:
        for p in problems:
            print(p)
        print(f"{len(shapes)} fixtures checked, {len(problems)} problems")
    return problems


def write(out: Path) -> int:
    world = load_world(cache_dir=CACHE)
    values = roles(world)
    out.mkdir(parents=True, exist_ok=True)
    for name in sorted(RECORDINGS):
        twin = league_fixture(world, name, values=values)
        (out / f"{name}.json").write_text(json.dumps(twin, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(RECORDINGS)} fixtures to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The made-up league's developer tool.")
    parser.add_argument("--signatures", action="store_true", help="rebuild shapes.json from the private recordings")
    parser.add_argument("--check", action="store_true", help="check the league against shapes.json")
    parser.add_argument("--out", type=Path, help="write the league's fixtures to this folder")
    args = parser.parse_args(argv)
    started = time.monotonic()
    code = 0
    if args.signatures:
        code |= signatures()
    if args.check:
        code |= 1 if check() else 0
    if args.out:
        code |= write(args.out)
    if not (args.signatures or args.check or args.out):
        parser.print_help()
    print(f"({time.monotonic() - started:.1f} s)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
