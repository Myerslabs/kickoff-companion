"""The Imperialism Map's grid (FEAT-17, Feature Set v2 Phase B, owner 2026-10-30): flat-top hexagons over the lower 48 states
and Hawaii, made once from the US Census Bureau's state outlines (cb_2024_us_state_20m, federal; the owner's 2026-10-08 rule
keeps the app off volunteer sources, so not Natural Earth) and kept in app/facts/imperialism/grid.json.

The map is equal-area: the lower 48 in the Albers conic equal-area projection US maps use (standard parallels 29.5 and
45.5 N, centered on 96 W), so every hexagon covers the same ground and land is a fair score. Hawaii sits in the usual
corner in its own Albers (parallels 8 and 18 N, centered on 157 W), drawn HAWAII_SCALE times larger than true scale
(owner's plan page of 2026-10-30: at true scale the islands hold about 25 cells against a share near 60, and the rest of
Hawaii's land would start on the California coast). Alaska has no FBS team and is left off.

A cell is (col, row) on one lattice across the whole 960 x 600 picture: its center x = X0 + col * 1.5 * side, y = Y0 +
row * sqrt(3) * side, odd columns half a row lower. A lattice point whose center falls inside a state is a cell; ids run
by column, then row, so the same outlines always give the same grid. Each cell keeps its latitude and longitude (the
projection run backwards) for the distances the rules use.

    Albers(...)                 forward(lon, lat) -> (x, y) in the picture; inverse(x, y) -> (lon, lat)
    lower48(), hawaii()         the two projections the picture uses
    read_states(kml_text)       {state code: [rings of (lon, lat)]} from the Census KML
    build_grid(states, target)  {side, x0, y0, cells: [...], states: path}, about `target` cells in the lower 48
    neighbors(col, row)         the six lattice neighbors
    load_grid(path) -> Grid     the committed file, with each cell's unit vector for distances
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WIDTH, HEIGHT = 960, 600
SCALE = 1273  # the lower 48 920 px across, 20 px from each side
HAWAII_SCALE = 1.6
SQRT3 = math.sqrt(3)
FORMAT = 1
LEFT_OFF = {"AK", "PR"}  # no FBS team; Puerto Rico is outside the picture
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "facts" / "imperialism" / "grid.json"


class Albers:
    """Albers conic equal-area, scaled and placed in the picture: (lon, lat) in degrees to (x, y) in picture units, y down."""

    def __init__(self, lon0: float, lat0: float, lat1: float, lat2: float, scale: float, tx: float, ty: float) -> None:
        p1, p2 = math.radians(lat1), math.radians(lat2)
        self.n = (math.sin(p1) + math.sin(p2)) / 2
        self.c = math.cos(p1) ** 2 + 2 * self.n * math.sin(p1)
        self.lon0 = math.radians(lon0)
        self.rho0 = math.sqrt(self.c - 2 * self.n * math.sin(math.radians(lat0))) / self.n
        self.scale, self.tx, self.ty = scale, tx, ty

    def forward(self, lon: float, lat: float) -> tuple[float, float]:
        rho = math.sqrt(max(0.0, self.c - 2 * self.n * math.sin(math.radians(lat)))) / self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        x = rho * math.sin(theta)
        y = self.rho0 - rho * math.cos(theta)
        return self.tx + self.scale * x, self.ty - self.scale * y

    def inverse(self, px: float, py: float) -> tuple[float, float]:
        x = (px - self.tx) / self.scale
        y = (self.ty - py) / self.scale
        rho = math.copysign(math.hypot(x, self.rho0 - y), self.n)
        theta = math.atan2(x, self.rho0 - y)
        lon = math.degrees(self.lon0 + theta / self.n)
        lat = math.degrees(math.asin(max(-1.0, min(1.0, (self.c - (rho * self.n) ** 2) / (2 * self.n)))))
        return lon, lat


def lower48() -> Albers:
    return Albers(-96.0, 38.7, 29.5, 45.5, SCALE, 489.6, 294.6)  # the lower 48 from 20 to 940 across, 10 to 590 down


def hawaii() -> Albers:
    return Albers(-157.0, 20.5, 8.0, 18.0, SCALE * HAWAII_SCALE, 215.0, 530.0)  # under Arizona, off Baja California, 25 px clear


def projection_for(region: str) -> Albers:
    return hawaii() if region == "hawaii" else lower48()


# --- the Census outlines ----------------------------------------------------------------------------------------


def read_states(kml_text: str) -> dict[str, list[list[tuple[float, float]]]]:
    """{two-letter code: outer rings as (lon, lat)} from cb_<year>_us_state_<res>.kml. Holes are not kept: a lake inside a
    state stays land for the game. Alaska and Puerto Rico are left off."""
    root = ET.fromstring(kml_text.encode("utf-8"))

    def local(el: ET.Element) -> str:
        return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""

    out: dict[str, list[list[tuple[float, float]]]] = {}
    for mark in (el for el in root.iter() if local(el) == "Placemark"):
        code = None
        for data in (el for el in mark.iter() if local(el) == "SimpleData"):
            if data.get("name") == "STUSPS":
                code = (data.text or "").strip()
        if not code or code in LEFT_OFF:
            continue
        rings = []
        for outer in (el for el in mark.iter() if local(el) == "outerBoundaryIs"):
            coords = next((el for el in outer.iter() if local(el) == "coordinates"), None)
            if coords is None or not coords.text:
                continue
            ring = []
            for token in coords.text.split():
                parts = token.split(",")
                if len(parts) >= 2:
                    ring.append((float(parts[0]), float(parts[1])))
            if len(ring) >= 4:
                rings.append(ring)
        if rings:
            out[code] = rings
    return dict(sorted(out.items()))


def _project(states: dict[str, list[list[tuple[float, float]]]]) -> dict[str, list[list[tuple[float, float]]]]:
    main, island = lower48(), hawaii()
    out = {}
    for code, rings in states.items():
        proj = island if code == "HI" else main
        out[code] = [[proj.forward(lon, lat) for lon, lat in ring] for ring in rings]
    return out


def _crossings(rings: list[list[tuple[float, float]]], y: float) -> list[float]:
    """The x of every ring edge crossing the horizontal line at y (even-odd)."""
    xs = []
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return xs


def _inside(xs: list[float], x: float) -> bool:
    count = 0
    for cx in xs:
        if cx > x:
            break
        count += 1
    return count % 2 == 1


def center(col: int, row: int, side: float, x0: float, y0: float) -> tuple[float, float]:
    h = SQRT3 * side
    return x0 + col * 1.5 * side, y0 + row * h + (h / 2 if col % 2 else 0.0)


def neighbors(col: int, row: int) -> list[tuple[int, int]]:
    """The six cells around (col, row) on the odd-columns-down lattice."""
    if col % 2 == 0:
        return [(col, row - 1), (col, row + 1), (col - 1, row - 1), (col - 1, row), (col + 1, row - 1), (col + 1, row)]
    return [(col, row - 1), (col, row + 1), (col - 1, row), (col - 1, row + 1), (col + 1, row), (col + 1, row + 1)]


def _lattice(projected: dict[str, list[list[tuple[float, float]]]], side: float) -> list[tuple[int, int, str]]:
    """Every lattice point inside a state: (col, row, region), by column then row."""
    x0, y0 = side, side
    lower = [ring for code, rings in projected.items() if code != "HI" for ring in rings]
    island = projected.get("HI", [])
    cols = int((WIDTH - 2 * side) / (1.5 * side)) + 1
    rows = int((HEIGHT - 2 * side) / (SQRT3 * side)) + 1
    found: list[tuple[int, int, str]] = []
    lines: dict[float, tuple[list[float], list[float]]] = {}
    for col in range(cols):
        for row in range(rows):
            x, y = center(col, row, side, x0, y0)
            key = round(y, 6)
            if key not in lines:
                lines[key] = (_crossings(lower, y), _crossings(island, y))
            main_xs, island_xs = lines[key]
            if _inside(main_xs, x):
                found.append((col, row, "lower48"))
            elif _inside(island_xs, x):
                found.append((col, row, "hawaii"))
    return found


def _path(projected: dict[str, list[list[tuple[float, float]]]], min_step: float = 0.6) -> str:
    """Every state's outline as one SVG path, points closer than min_step dropped."""
    parts = []
    for code in sorted(projected):
        for ring in projected[code]:
            kept = [ring[0]]
            for x, y in ring[1:]:
                if math.hypot(x - kept[-1][0], y - kept[-1][1]) >= min_step:
                    kept.append((x, y))
            if len(kept) < 3:
                continue
            parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in kept) + "Z")
    return "".join(parts)


def build_grid(states: dict[str, list[list[tuple[float, float]]]], target: int = 12000) -> dict[str, Any]:
    """The grid with about `target` cells in the lower 48: the side is found by halving the gap, then every cell's
    latitude and longitude come from the projection run backwards. Deterministic."""
    projected = _project(states)
    lo, hi = 1.5, 6.0
    best: tuple[float, list[tuple[int, int, str]]] | None = None
    for _ in range(18):
        side = (lo + hi) / 2
        cells = _lattice(projected, side)
        count = sum(1 for c in cells if c[2] == "lower48")
        if best is None or abs(count - target) < abs(sum(1 for c in best[1] if c[2] == "lower48") - target):
            best = (side, cells)
        if abs(count - target) <= target * 0.002:
            break
        if count > target:
            lo = side
        else:
            hi = side
    assert best is not None
    side, cells = best
    side = round(side, 4)
    cells = _lattice(projected, side)
    rows = []
    for cid, (col, row, region) in enumerate(cells):
        x, y = center(col, row, side, side, side)
        lon, lat = projection_for(region).inverse(x, y)
        rows.append([cid, col, row, region, round(lat, 4), round(lon, 4), round(x, 2), round(y, 2)])
    return {
        "format": FORMAT,
        "source": "US Census Bureau cartographic boundary file cb_2024_us_state_20m (KML)",
        "viewBox": [0, 0, WIDTH, HEIGHT],
        "projection": {"lower48": "Albers equal-area, parallels 29.5 and 45.5 N, centered 96 W", "hawaii": f"Albers equal-area, parallels 8 and 18 N, centered 157 W, {HAWAII_SCALE} times true scale"},
        "side": side,
        "x0": side,
        "y0": side,
        "count": len(rows),
        "lower48": sum(1 for r in rows if r[3] == "lower48"),
        "hawaii": sum(1 for r in rows if r[3] == "hawaii"),
        "columns": ["id", "col", "row", "region", "lat", "lon", "x", "y"],
        "cells": rows,
        "states": _path(projected),
    }


# --- the committed grid, read back --------------------------------------------------------------------------------


def unit(lat: float, lon: float) -> tuple[float, float, float]:
    """A point on the unit sphere: the closer two points, the larger their dot product (1 is the same spot)."""
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))


@dataclass
class Grid:
    side: float
    x0: float
    y0: float
    ids: list[int]
    cols: list[int]
    rows: list[int]
    regions: list[str]
    lats: list[float]
    lons: list[float]
    vectors: list[tuple[float, float, float]] = field(default_factory=list)
    states: str = ""

    @property
    def count(self) -> int:
        return len(self.ids)

    def neighbor_ids(self) -> list[list[int]]:
        at = {(c, r): i for i, c, r in zip(self.ids, self.cols, self.rows, strict=True)}
        return [sorted(at[n] for n in neighbors(c, r) if n in at) for c, r in zip(self.cols, self.rows, strict=True)]

    def compact(self) -> dict[str, Any]:
        """What the tablet needs to draw it: the lattice and each cell's (col, row), and the states' outlines."""
        flat: list[int] = []
        for c, r in zip(self.cols, self.rows, strict=True):
            flat.extend((c, r))
        return {"format": FORMAT, "viewBox": [0, 0, WIDTH, HEIGHT], "side": self.side, "x0": self.x0, "y0": self.y0, "count": self.count, "cells": flat, "states": self.states}


def load_grid(path: Path = DEFAULT_PATH) -> Grid:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("format") != FORMAT or not isinstance(raw.get("cells"), list):
        raise ValueError(f"{path} is not a grid this build reads")
    cols = raw["columns"]
    at = {name: i for i, name in enumerate(cols)}
    rows = raw["cells"]
    grid = Grid(
        side=float(raw["side"]),
        x0=float(raw["x0"]),
        y0=float(raw["y0"]),
        ids=[int(r[at["id"]]) for r in rows],
        cols=[int(r[at["col"]]) for r in rows],
        rows=[int(r[at["row"]]) for r in rows],
        regions=[str(r[at["region"]]) for r in rows],
        lats=[float(r[at["lat"]]) for r in rows],
        lons=[float(r[at["lon"]]) for r in rows],
        states=str(raw.get("states") or ""),
    )
    if grid.ids != list(range(grid.count)):
        raise ValueError(f"{path}: the cell ids must run 0 to {grid.count - 1} in order")
    grid.vectors = [unit(la, lo) for la, lo in zip(grid.lats, grid.lons, strict=True)]
    return grid
