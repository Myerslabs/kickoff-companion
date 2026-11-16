"""The Imperialism Map's rules (FEAT-17, Feature Set v2 Phase B, B.1 to B.8). Every FBS team
starts the season on its own campus, holding land grown from it by its enrollment where there is room (v3, owner 2026-10-30:
"the schools need to be anchored in their locations"); a win takes land from the loser; on Selection
Sunday the twelve playoff teams split everyone else's land; in the playoff the winner takes it all.

The season is replayed from scratch on every run (B.5): the deal, then every decisive finished game in order, a snapshot
after each week, Selection Sunday and each playoff round. Nothing is patched, so a corrected score redraws the whole
season and the same inputs give the same bytes.

Distances are between points on the unit sphere (app/services/imperialism_grid.py unit): the larger the dot product, the
nearer. "Nearest to a team's land" is the nearest of its edge cells, those with a lattice neighbor it does not hold:
on the hex lattice an interior cell always has a neighbor at least as near to any cell outside the territory, so the
nearest edge cell is the nearest cell, and the search stays small (B.4 asks to measure; a full season replays in seconds).

    read_enrollment(path) -> {school: students}      the committed table, checked (B.2)
    quotas(enrollment, cells) -> {school: cells}      largest remainder, exact, ties by the school's name (B.3)
    home_cells(grid, teams) -> [cell]                 each team's campus cell (the nearest free cell to its campus)
    deal(grid, teams) -> owners                      grown from each campus in fair turns toward its share (B.3, v3)
    Season(grid, teams, ...).replay(...) -> table    the snapshots, the events, each team's record (B.4 to B.7)
    pack(owners) / unpack(text)                      int16, gzip, base64 (B.8)
    ImperialismStore(data_dir, season)                data/season/<year>/imperialism.json, written whole
"""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import heapq
import json
import logging
import math
import struct
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write
from app.services.imperialism_grid import Grid, projection_for, unit

log = logging.getLogger("kickoff.imperialism")

FORMAT = 1
FIELD_SIZE = 12
MIN_ENROLLMENT = 1000
ENROLLMENT_PATH = Path(__file__).resolve().parents[1] / "facts" / "imperialism" / "enrollment.csv"
ROUNDS = {"first_round": 1, "quarterfinal": 2, "semifinal": 3, "championship": 4}
ROUND_LABELS = {1: "R1", 2: "QF", 3: "SF", 4: "Final"}
PENDING_HOURS = 6  # a game that started this recently and is not final is still being played: its week is in progress
RULES = "Every school starts on its own campus, its land grown from there by its enrollment where there is room. A win takes up to the winner's starting size from the loser, the cells nearest the winner first. On Selection Sunday the twelve playoff teams split everyone else's land. In the playoff the winner takes everything."


class ImperialismError(Exception):
    """The map cannot be dealt or replayed; the message names what is wrong (a school missing from the enrollment table)."""


# --- the enrollment table and the shares -----------------------------------------------------------------------------


def read_enrollment(path: Path = ENROLLMENT_PATH) -> dict[str, int]:
    """{CFBD school: students}. A row with no school, a count under 1,000 or not a whole number, or a school twice stops
    the read with every problem named (B.2)."""
    problems: list[str] = []
    out: dict[str, int] = {}
    try:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError as exc:
        raise ImperialismError(f"The enrollment table {path} could not be read: {exc}") from exc
    for n, row in enumerate(rows, start=2):
        school = (row.get("cfbd_school") or "").strip()
        raw = (row.get("enrollment") or "").strip()
        if not school:
            problems.append(f"line {n}: no school")
            continue
        if school in out:
            problems.append(f"{school}: listed twice")
            continue
        if not raw.isdigit() or int(raw) < MIN_ENROLLMENT:
            problems.append(f"{school}: enrollment {raw!r} is not a whole number of at least {MIN_ENROLLMENT:,}")
            continue
        out[school] = int(raw)
    if problems:
        raise ImperialismError("The enrollment table has problems: " + "; ".join(problems))
    return dict(sorted(out.items()))


def quotas(enrollment: dict[str, int], cells: int) -> dict[str, int]:
    """Each school's share of the cells, floor first, then one more each for the largest remainders until the shares
    add up to `cells` exactly (B.3). Integer arithmetic, so no rounding drift; a tie goes to the school first by name."""
    if cells < 0 or not enrollment:
        return {}
    total = sum(enrollment.values())
    base = {t: cells * e // total for t, e in enrollment.items()}
    left = cells - sum(base.values())
    order = sorted(enrollment, key=lambda t: (-(cells * enrollment[t] % total), t))
    for t in order[:left]:
        base[t] += 1
    return dict(sorted(base.items()))


# --- the board -----------------------------------------------------------------------------------------------------


@dataclass
class TeamSpot:
    key: str
    index: int
    quota: int  # the enrollment share, in cells
    lat: float
    lon: float
    vector: tuple[float, float, float] = field(default=(0.0, 0.0, 1.0))
    start: int | None = None  # the land it was dealt (v3: grown from its campus, not always its share); a win takes up to this

    @property
    def cap(self) -> int:
        """A win takes up to the winner's starting size: the land it was dealt, else its share."""
        return self.start if self.start is not None else self.quota


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# The weighted split (owner 2026-10-30, "Weighted split", over the spec's B.3 nearest-campus-with-room rule, which scattered
# crowded schools' extra land as stripes across the Plains: 321 pieces against 186). Each team gets a reach, a number added
# to every cell's nearness to it; a cell goes to the team where nearness plus reach is highest. The reaches are tuned until
# each team's land is its share, so every territory is one solid region (a power diagram on the sphere), and where schools
# are crowded the extra land sits beside them rather than scattered far away. A last pass, highest score first, makes the
# shares exact. Selection Sunday splits the pool the same way (B.6 says the same method as the start).
WEIGHT_ROUNDS = 300
WEIGHT_STEP = 0.004
WEIGHT_DECAY = 0.985
CANDIDATES = 48  # the campuses each cell weighs: its 48 nearest, which every crowded school's region stays inside
DEAL_VERSION = 3  # 1 the spec's nearest-campus-with-room rule, 2 the weighted split (exact shares, but most regions slid west of their campus), 3 grown from each campus; a kept start map of another version is worked out again


def weighted_assign(scores: list[list[tuple[int, float]]], capacity: list[int], best_open: Any = None) -> list[int]:
    """Each item's team: the one with the highest score plus reach among its candidates, the reaches tuned round by round
    toward each team's capacity, then a pass highest first that holds every team to its capacity exactly. An item whose
    candidates are all full goes to `best_open(item, open_teams)` (default: the first open team). Deterministic: ties by
    team, then item. Capacities must add up to the items."""
    teams = len(capacity)
    if sum(capacity) != len(scores):
        raise ImperialismError(f"The shares add up to {sum(capacity)} for {len(scores)} cells")
    reach = [0.0] * teams
    step = WEIGHT_STEP
    for _round in range(WEIGHT_ROUNDS):
        counts = [0] * teams
        for cands in scores:
            best_t, best = -1, float("-inf")
            for t, sc in cands:
                v = sc + reach[t]
                if v > best:
                    best, best_t = v, t
            counts[best_t] += 1
        miss = [counts[t] - capacity[t] for t in range(teams)]
        if not any(miss):
            break
        for t in range(teams):
            reach[t] -= step * miss[t] / max(capacity[t], 1)
        step *= WEIGHT_DECAY
    owners = [-1] * len(scores)
    held = [0] * teams
    for _v, t, j in sorted((-(sc + reach[t]), t, j) for j, cands in enumerate(scores) for t, sc in cands):
        if owners[j] < 0 and held[t] < capacity[t]:
            owners[j] = t
            held[t] += 1
    for j in range(len(scores)):
        if owners[j] >= 0:
            continue
        open_teams = [t for t in range(teams) if held[t] < capacity[t]]
        t = best_open(j, open_teams, reach) if best_open else open_teams[0]
        owners[j] = t
        held[t] += 1
    return owners


def _angle(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.acos(max(-1.0, min(1.0, _dot(a, b))))


def home_cells(grid: Grid, teams: list[TeamSpot]) -> list[int]:
    """Each team's campus cell, in team order: the cell nearest its campus, or, when an earlier team already sits there (two
    campuses a few miles apart), the nearest cell still free."""
    vectors = grid.vectors
    taken: set[int] = set()
    out = []
    for t in teams:
        best = max(range(grid.count), key=lambda c: (_dot(vectors[c], t.vector), -c))
        if best in taken:
            best = next(c for _d, c in sorted((-_dot(vectors[c], t.vector), c) for c in range(grid.count)) if c not in taken)
        taken.add(best)
        out.append(best)
    return out


FIRST_RING = 7  # every school's equal first turns: its campus and the six cells around it, before turns go by share


def deal(grid: Grid, teams: list[TeamSpot], homes: list[int] | None = None) -> list[int]:
    """Every cell's owner at the start, grown from each campus (owner 2026-10-30: "the schools need to be anchored in their
    locations"; "Grow from campus"). Every school starts on its campus cell and grows one cell at a time, always the free
    cell beside its land that lies nearest its campus. The turns: first an equal start, each school to its campus ring
    (FIRST_RING cells), so a school between a big neighbor and the sea is not shut in at once; then the school furthest
    behind its enrollment share goes next, until it holds its share or has no free cell beside it. The land still free
    (where a school ran out of room) goes, cell by cell, to the school beside it whose campus is reached first at its
    speed, the square root of its share. Every school holds its campus and one solid piece around it; the crowded East
    comes out below its shares and the open West above. A cell no land touches (an island) goes to the school whose
    campus would reach it first anyway. Deterministic: ties by team, then cell."""
    vectors = grid.vectors
    neighbors = grid.neighbor_ids()
    homes = homes if homes is not None else home_cells(grid, teams)
    owners = [-1] * grid.count
    held = [0] * len(teams)
    frontier: list[list[tuple[float, int]]] = [[] for _ in teams]

    def claim(ti: int, c: int) -> None:
        owners[c] = ti
        held[ti] += 1
        for n in neighbors[c]:
            if owners[n] < 0:
                heapq.heappush(frontier[ti], (_angle(vectors[n], teams[ti].vector), n))

    def turn_key(ti: int) -> tuple[int, float]:
        if held[ti] < min(FIRST_RING, teams[ti].quota):
            return (0, float(held[ti]))
        return (1, held[ti] / max(teams[ti].quota, 1))

    for t in teams:
        claim(t.index, homes[t.index])
    turns = [(turn_key(t.index), t.index) for t in teams if held[t.index] < t.quota]
    heapq.heapify(turns)
    while turns:
        _key, ti = heapq.heappop(turns)
        room = frontier[ti]
        while room and owners[room[0][1]] >= 0:
            heapq.heappop(room)
        if not room:
            continue  # shut in: no free cell beside its land
        _d, c = heapq.heappop(room)
        claim(ti, c)
        if held[ti] < teams[ti].quota:
            heapq.heappush(turns, (turn_key(ti), ti))
    speed = [math.sqrt(max(t.quota, 1)) for t in teams]
    spread = [(_angle(vectors[n], teams[owners[c]].vector) / speed[owners[c]], owners[c], n) for c in range(grid.count) if owners[c] >= 0 for n in neighbors[c] if owners[n] < 0]
    heapq.heapify(spread)
    while spread:
        _when, ti, c = heapq.heappop(spread)
        if owners[c] >= 0:
            continue
        owners[c] = ti
        for n in neighbors[c]:
            if owners[n] < 0:
                heapq.heappush(spread, (_angle(vectors[n], teams[ti].vector) / speed[ti], ti, n))
    for c in range(grid.count):
        if owners[c] < 0:
            owners[c] = min(range(len(teams)), key=lambda ti: (_angle(vectors[c], teams[ti].vector) / speed[ti], ti))
    return owners


class Board:
    """The map as it stands: each cell's owner and each team's cells."""

    def __init__(self, grid: Grid, teams: list[TeamSpot], owners: list[int]) -> None:
        self.grid = grid
        self.teams = teams
        self.owners = list(owners)
        self.neighbors = grid.neighbor_ids()
        self.cells: list[set[int]] = [set() for _ in teams]
        for c, ti in enumerate(self.owners):
            self.cells[ti].add(c)

    def edge(self, ti: int) -> list[int]:
        """The team's cells with fewer than six neighbors of its own (a coast counts as not its own)."""
        own = self.cells[ti]
        return sorted(c for c in own if len(self.neighbors[c]) < 6 or any(self.owners[n] != ti for n in self.neighbors[c]))

    def closeness(self, ti: int, cells: Iterable[int]) -> dict[int, float]:
        """{cell: how near it is to team ti's land} (the dot product with the nearest edge cell; with no land, with the
        team's campus)."""
        vectors = self.grid.vectors
        anchors = [vectors[c] for c in self.edge(ti)] or [self.teams[ti].vector]
        out = {}
        for c in cells:
            v = vectors[c]
            out[c] = max(a[0] * v[0] + a[1] * v[1] + a[2] * v[2] for a in anchors)
        return out

    def move(self, cells: Iterable[int], to: int) -> int:
        n = 0
        for c in cells:
            was = self.owners[c]
            if was == to:
                continue
            self.cells[was].discard(c)
            self.cells[to].add(c)
            self.owners[c] = to
            n += 1
        return n

    def capped_take(self, winner: int, loser: int) -> list[int]:
        """B.4: up to the winner's starting size of the loser's cells, the ones nearest the winner's land first (ties by
        cell id). Returns the cells moved."""
        theirs = sorted(self.cells[loser])
        take = min(len(theirs), self.teams[winner].cap)
        if take <= 0:
            return []
        near = self.closeness(winner, theirs)
        chosen = sorted(theirs, key=lambda c: (-near[c], c))[:take]
        self.move(chosen, winner)
        return chosen

    def take_all(self, winner: int, loser: int) -> list[int]:
        cells = sorted(self.cells[loser])
        self.move(cells, winner)
        return cells

    def selection(self, seeds: list[int]) -> dict[tuple[int, int], int]:
        """B.6: every cell of a team outside the field, pooled and split evenly among the twelve, one more each to the
        best seeds for what does not divide; each playoff team's share placed by the start's method, the weighted split,
        with nearness to its own land (so its new land lies against it). Returns {(receiver, giver): cells}."""
        field_set = set(seeds)
        pool = sorted(c for c, ti in enumerate(self.owners) if ti not in field_set)
        if not pool:
            return {}
        share, extra = divmod(len(pool), len(seeds))
        room = [share + (1 if i < extra else 0) for i in range(len(seeds))]
        nearness = [self.closeness(ti, pool) for ti in seeds]
        scores = [[(k, nearness[k][c]) for k in range(len(seeds))] for c in pool]
        picks = weighted_assign(scores, room, lambda j, open_k, reach: max(open_k, key=lambda k: (nearness[k][pool[j]] + reach[k], -k)))
        given = {c: seeds[k] for c, k in zip(pool, picks, strict=True)}
        moved: Counter[tuple[int, int]] = Counter()
        for c, ti in sorted(given.items()):
            moved[(ti, self.owners[c])] += 1
        for c, ti in sorted(given.items()):
            self.move([c], ti)
        return dict(sorted(moved.items()))


# --- packing a snapshot (B.8) ----------------------------------------------------------------------------------------


def pack(owners: list[int]) -> str:
    """Owners as little-endian int16, gzipped with no timestamp (same bytes every time), in base64."""
    raw = struct.pack(f"<{len(owners)}h", *owners)
    return base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")


def unpack(text: str) -> list[int]:
    raw = gzip.decompress(base64.b64decode(text.encode("ascii")))
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


# --- the season ------------------------------------------------------------------------------------------------------


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def decisive(game: Any) -> tuple[str, str] | None:
    """(winner, loser) of a finished game with both scores and no tie, else None (B.1: a cancelled, forfeited or
    unscored game moves nothing)."""
    if getattr(game, "completed", None) is not True:
        return None
    hp, ap = getattr(game, "home_points", None), getattr(game, "away_points", None)
    if not isinstance(hp, int) or not isinstance(ap, int) or isinstance(hp, bool) or isinstance(ap, bool) or hp == ap:
        return None
    home, away = getattr(game, "home_team", None), getattr(game, "away_team", None)
    if not isinstance(home, str) or not isinstance(away, str):
        return None
    return (home, away) if hp > ap else (away, home)


def _order(game: Any) -> tuple[str, int]:
    return (str(getattr(game, "start_date", None) or ""), getattr(game, "id", 0) if isinstance(getattr(game, "id", None), int) else 0)


def cfp_round(game: Any) -> int | None:
    """1 to 4 for a College Football Playoff game (CFBD's playoff block), else None."""
    block = getattr(game, "playoff", None)
    if block is None or str(getattr(block, "competition", "") or "").lower() != "cfp":
        return None
    return ROUNDS.get(str(getattr(block, "round", "") or ""))


@dataclass
class Snapshot:
    phase: str
    week: int
    label: str
    partial: bool
    owners: list[int]
    records: dict[str, tuple[int, int]]


class Season:
    """One season's replay over the grid. `teams` are the season's FBS schools with an enrollment row, in name order."""

    def __init__(self, grid: Grid, enrollment: dict[str, int], fbs: dict[str, dict[str, Any]], campuses: dict[str, tuple[float, float]], now: datetime) -> None:
        missing = sorted(s for s in fbs if s not in enrollment)
        if missing:
            raise ImperialismError(f"No enrollment row for {len(missing)} FBS school{'s' if len(missing) != 1 else ''}: {', '.join(missing)}")
        no_campus = sorted(s for s in fbs if s not in campuses)
        if no_campus:
            raise ImperialismError(f"No campus location from CFBD for: {', '.join(no_campus)}")
        keys = sorted(fbs)
        shares = quotas({k: enrollment[k] for k in keys}, grid.count)
        self.grid = grid
        self.fbs = fbs
        self.now = now
        self.teams = [TeamSpot(k, i, shares[k], campuses[k][0], campuses[k][1], unit(*campuses[k])) for i, k in enumerate(keys)]
        self.index = {t.key: t.index for t in self.teams}
        self.events: list[dict[str, Any]] = []
        self.snapshots: list[Snapshot] = []
        self.records: dict[str, list[int]] = {k: [0, 0] for k in keys}
        self.notes: list[str] = []

    def _record(self, game: Any) -> None:
        result = decisive(game)
        if result is None:
            return
        winner, loser = result
        if winner in self.records:
            self.records[winner][0] += 1
        if loser in self.records:
            self.records[loser][1] += 1

    def _snap(self, board: Board, phase: str, week: int, label: str, partial: bool) -> None:
        self.snapshots.append(Snapshot(phase, week, label, partial, list(board.owners), {k: (v[0], v[1]) for k, v in self.records.items()}))

    def _event(self, phase: str, week: int, game: Any, winner: str | None, loser: str | None, moved: int, rule: str) -> None:
        hp, ap = getattr(game, "home_points", None), getattr(game, "away_points", None)
        high, low = (max(hp, ap), min(hp, ap)) if isinstance(hp, int) and isinstance(ap, int) else (None, None)
        self.events.append({"phase": phase, "week": week, "gameId": getattr(game, "id", None) if game is not None else None, "winner": winner, "loser": loser, "winnerPoints": high, "loserPoints": low, "cellsMoved": moved, "rule": rule})

    def _play(self, board: Board, phase: str, week: int, game: Any, playoff: bool) -> None:
        self._record(game)
        result = decisive(game)
        if result is None:
            return
        winner, loser = result
        if winner not in self.index or loser not in self.index:
            self._event(phase, week, game, winner, loser, 0, "none")  # an FCS side holds no land: nothing moves
            return
        w, lo = self.index[winner], self.index[loser]
        moved = board.take_all(w, lo) if playoff else board.capped_take(w, lo)
        self._event(phase, week, game, winner, loser, len(moved), ("winner_take_all" if playoff else "capped") if moved else "none")

    def _pending(self, games: list[Any]) -> bool:
        cutoff = self.now - timedelta(hours=PENDING_HOURS)
        for g in games:
            if getattr(g, "completed", None) is True:
                continue
            start = _time(getattr(g, "start_date", None))
            if start is not None and start > cutoff:
                return True
        return False

    def start_key(self, grid_version: str) -> str:
        """What the start map depends on: the method's version, the grid, and each team's share and campus."""
        basis = [DEAL_VERSION, grid_version, [[t.key, t.quota, round(t.lat, 5), round(t.lon, 5)] for t in self.teams]]
        return hashlib.sha256(json.dumps(basis, separators=(",", ":")).encode("utf-8")).hexdigest()

    def replay(self, regular: list[Any], postseason: list[Any], field: list[tuple[str, int]] | None, field_source: str, start: list[int] | None = None) -> Board:
        """The season from the start map (`start`, when kept from an earlier run of the same inputs and every school still
        holds its own campus in it, else dealt now). Each team's quota becomes the land it starts with: a win takes up to the
        winner's starting size (`start`; the share stays in `quota`, which the start map's key reads)."""
        self.homes = home_cells(self.grid, self.teams)
        valid = start is not None and len(start) == self.grid.count and all(isinstance(o, int) and 0 <= o < len(self.teams) for o in start) and all(start[h] == i for i, h in enumerate(self.homes))
        self.start = list(start) if valid and start is not None else deal(self.grid, self.teams, self.homes)
        self.dealt = not valid
        held = Counter(self.start)
        for t in self.teams:
            t.start = held[t.index]
        board = Board(self.grid, self.teams, self.start)
        fbs = set(self.fbs)
        involved = [g for g in regular if str(getattr(g, "season_type", None) or "regular") == "regular" and (getattr(g, "home_team", None) in fbs or getattr(g, "away_team", None) in fbs) and isinstance(getattr(g, "week", None), int)]
        by_week: dict[int, list[Any]] = defaultdict(list)
        for g in involved:
            by_week[g.week].append(g)
        start_week = -1 if 0 in by_week else 0
        self._snap(board, "regular", start_week, "Start", False)
        played_weeks = [w for w in sorted(by_week) if any(decisive(g) for g in by_week[w])]
        last_played = played_weeks[-1] if played_weeks else None
        is_title = lambda g: "championship" in str(getattr(g, "notes", None) or "").lower()  # noqa: E731
        title_weeks = [w for w in sorted(by_week) if any(is_title(g) for g in by_week[w])]
        seeds = self._field(field, postseason)
        regular_done = bool(title_weeks) and all(getattr(g, "completed", None) is True for w in title_weeks for g in by_week[w] if is_title(g))
        selected = seeds is not None and regular_done
        # Selection Sunday follows the conference championships; a later regular week (Army-Navy) is played after it
        after_selection = [w for w in sorted(by_week) if selected and w > title_weeks[-1]]

        def play_week(week: int) -> None:
            games = sorted(by_week[week], key=_order)
            for g in games:
                self._play(board, "regular", week, g, playoff=False)
            label = "CCG" if games and all(is_title(g) for g in games) else f"Wk {week}"
            self._snap(board, "regular", week, label, self._pending(games))

        for week in sorted(by_week):
            if last_played is None or week > last_played or week in after_selection:
                break
            play_week(week)
        if not selected:
            self.notes.append("CFP field not yet known" if seeds is None else "the conference championships are not over")
            self._upcoming(by_week, is_title)
            return board
        assert seeds is not None
        self.notes.append(f"CFP field from {field_source if field else 'the seeds on the playoff games'}")
        moved = board.selection([self.index[s] for s in seeds])
        for (to, frm), n in moved.items():
            self.events.append({"phase": "selection", "week": 0, "gameId": None, "winner": self.teams[to].key, "loser": self.teams[frm].key, "winnerPoints": None, "loserPoints": None, "cellsMoved": n, "rule": "selection_sunday"})
        self._snap(board, "selection", 0, "Selection Sunday", False)
        for week in after_selection:
            if last_played is not None and week <= last_played:
                play_week(week)
        post = sorted((g for g in postseason if str(getattr(g, "season_type", None) or "") == "postseason"), key=_order)
        rounds: dict[int, list[Any]] = defaultdict(list)
        last_of_round: dict[int, int] = {}
        for i, g in enumerate(post):
            r = cfp_round(g)
            if r is not None:
                rounds[r].append(g)
                last_of_round[r] = i
        for i, g in enumerate(post):
            r = cfp_round(g)
            self._play(board, "postseason", r or 0, g, playoff=r is not None)
            if r is None or last_of_round[r] != i:
                continue
            finished = [getattr(x, "completed", None) is True for x in rounds[r]]
            if any(finished):  # a round with a final in it gets its snapshot, in progress until every game is final
                self._snap(board, "postseason", r, ROUND_LABELS[r], not all(finished))
        self._upcoming(by_week, is_title)
        return board

    def _upcoming(self, by_week: dict[int, list[Any]], is_title: Any) -> None:
        """The labels of what is still to come, in order, for the page's faded ticks: the regular weeks left (the week of
        the conference championships as CCG), Selection Sunday, a regular week after the championships (Army-Navy), then
        the playoff rounds not yet played."""
        done = {(s.phase, s.week) for s in self.snapshots}
        weeks = sorted(w for w in by_week if w >= 1 and ("regular", w) not in done)
        titles = [w for w in sorted(by_week) if any(is_title(g) for g in by_week[w])]
        late = [w for w in weeks if titles and w > titles[-1]]

        def label(w: int) -> str:
            return "CCG" if by_week[w] and all(is_title(g) for g in by_week[w]) else f"Wk {w}"

        upcoming = [label(w) for w in weeks if w not in late]
        if ("selection", 0) not in done:
            upcoming.append("Selection Sunday")
        upcoming += [label(w) for w in late]
        upcoming += [ROUND_LABELS[r] for r in sorted(ROUND_LABELS) if ("postseason", r) not in done]
        self.upcoming = upcoming

    def _field(self, field: list[tuple[str, int]] | None, postseason: list[Any]) -> list[str] | None:
        """The twelve playoff teams in seed order: CFBD's participants when it names twelve FBS teams, else the seeds on
        the playoff games' brackets (B.6); None while neither has twelve."""
        teams = set(self.index)
        if field:
            seeded = sorted((seed, team) for team, seed in field if team in teams)
            if len(seeded) == FIELD_SIZE and len({t for _s, t in seeded}) == FIELD_SIZE:
                return [t for _s, t in seeded]
        seeds: dict[str, int] = {}
        for g in postseason:
            block = getattr(g, "playoff", None)
            if cfp_round(g) is None or block is None:
                continue
            for team, seed in ((getattr(g, "home_team", None), getattr(block, "home_seed", None)), (getattr(g, "away_team", None), getattr(block, "away_seed", None))):
                if isinstance(team, str) and team in teams and isinstance(seed, int):
                    seeds.setdefault(team, seed)
        if len(seeds) == FIELD_SIZE:
            return [t for t, _s in sorted(seeds.items(), key=lambda kv: (kv[1], kv[0]))]
        return None


def build_table(season: Season, identities: dict[str, dict[str, Any]], computed_week: int | None, sources: dict[str, Any], grid_version: str) -> dict[str, Any]:
    """The job's output: the teams (index order), each snapshot packed, the events, each team's record by snapshot."""
    teams = []
    for t in season.teams:
        ident = identities.get(t.key, {})
        homes = getattr(season, "homes", None)
        home = homes[t.index] if isinstance(homes, list) and t.index < len(homes) else None  # the campus cell, where the page anchors the logo
        # the campus point itself in the picture (owner 2026-11-01: "still not centered on each schools campus"): the cell is a
        # hex some thirty miles across, so the logo sits on the point, not the cell's middle, while the school holds the cell
        campus = None
        if isinstance(home, int) and 0 <= home < len(season.grid.regions):
            px, py = projection_for(season.grid.regions[home]).forward(t.lon, t.lat)
            campus = [round(px, 2), round(py, 2)]
        teams.append({"team": t.key, "index": t.index, "id": ident.get("id"), "quota": t.cap, "share": t.quota, "home": home, "campus": campus, "lat": t.lat, "lon": t.lon, "abbreviation": ident.get("abbreviation"), "conference": ident.get("conference"), "color": ident.get("color"), "altColor": ident.get("altColor")})
    return {
        "format": FORMAT,
        "season": None,
        "gridVersion": grid_version,
        "cells": season.grid.count,
        "computedWeek": computed_week,
        "rules": RULES,
        "notes": season.notes,
        "upcoming": getattr(season, "upcoming", []),
        "sources": dict(sorted(sources.items())),
        "teams": teams,
        "snapshots": [{"phase": s.phase, "week": s.week, "label": s.label, "partial": s.partial, "holdings": pack(s.owners), "records": {k: list(v) for k, v in sorted(s.records.items())}} for s in season.snapshots],
        "events": season.events,
    }


# --- the store -------------------------------------------------------------------------------------------------------


class ImperialismStore:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.path = Path(data_dir) / "season" / str(season) / "imperialism.json"
        self.start_path = self.path.with_name("imperialism-start.json")  # the weighted start map, kept per season (about 20 s to work out)
        self.season = season
        self._cache: tuple[tuple[int, int], dict[str, Any]] | None = None

    def save(self, table: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps({**table, "season": self.season}, separators=(",", ":"), ensure_ascii=False) + "\n")
        self._cache = None

    def load_start(self, key: str) -> list[int] | None:
        """The kept start map when it was worked out from the same inputs (`key`), else None."""
        try:
            raw = json.loads(self.start_path.read_text(encoding="utf-8"))
            return unpack(raw["owners"]) if isinstance(raw, dict) and raw.get("key") == key else None
        except (OSError, ValueError, KeyError, TypeError, struct.error):
            return None

    def save_start(self, key: str, owners: list[int]) -> None:
        self.start_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.start_path, json.dumps({"format": FORMAT, "key": key, "owners": pack(owners)}) + "\n")

    def load(self) -> dict[str, Any] | None:
        try:
            info = self.path.stat()
            stamp = (info.st_mtime_ns, info.st_size)  # the size too: two writes inside one clock tick share a time on Windows
        except OSError:
            return None
        if self._cache is not None and self._cache[0] == stamp:
            return self._cache[1]
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("The Imperialism Map could not be read (%s)", exc)
            return None
        if not isinstance(raw, dict) or raw.get("format") != FORMAT or not isinstance(raw.get("snapshots"), list) or not isinstance(raw.get("teams"), list):
            log.warning("The Imperialism Map at %s is not one this build reads; it is left alone", self.path)
            return None
        for snap in raw["snapshots"]:
            try:
                snap["owners"] = unpack(snap["holdings"])
            except (KeyError, ValueError, TypeError, OSError, struct.error) as exc:
                log.warning("A snapshot of the Imperialism Map could not be unpacked (%s); the file is left alone", exc)
                return None
        self._cache = (stamp, raw)
        return raw
