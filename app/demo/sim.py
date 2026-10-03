"""One made-up game, simulated play by play.

The model is deliberately simple and tuned to look like modern college football: about 70 snaps a
side, 28 points a team, a 62% completion rate, 4.5 yards a carry, a turnover or two. Each team
brings an offense and a defense rating in points (above or below an average team), so a good
offense against a weak defense gains more. Every random draw comes from the game's own seeded
generator, so the same game always plays out the same way: the season pass simulates every game
once for its box score, and the plays are simulated again on demand when an endpoint needs them.

Field position is `ytg`, yards to the opponent's goal line (1 to 99), the way CFBD's
`yardsToGoal` counts it. Clocks are seconds left in the period. Text is written later (`text.py`)
from the play's fields, in the grammar of the play-by-play feed the app reads.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

PERIOD_SECONDS = 900
HOME_FIELD = 2.5  # points

# Expected points by yards to goal on first and ten (anchors, interpolated).
_EP_ANCHORS = [(1, 6.2), (5, 5.6), (10, 5.0), (15, 4.6), (25, 3.8), (35, 3.1), (50, 2.2), (65, 1.3), (75, 0.7), (80, 0.3), (90, -0.5), (99, -1.2)]

PLAY_TYPE_IDS = {
    "Rush": 5, "Pass Reception": 24, "Pass Incompletion": 3, "Sack": 7, "Timeout": 21, "Kickoff": 53,
    "Kickoff Return (Offense)": 12, "Penalty": 8, "Punt": 52, "Rushing Touchdown": 68, "Passing Touchdown": 67,
    "End Period": 2, "End of Half": 65, "End of Game": 66, "Field Goal Good": 59, "Field Goal Missed": 60,
    "Fumble Recovery (Own)": 9, "Fumble Recovery (Opponent)": 29, "Pass Interception Return": 26,
    "Interception Return Touchdown": 36, "Kickoff Return Touchdown": 32, "Punt Return Touchdown": 34,
    "Safety": 20, "Fumble Return Touchdown": 39, "Two Point Rush": 16, "Two Point Pass": 15,
}

SCRIMMAGE_RUSH = ("Rush", "Rushing Touchdown")
SCRIMMAGE_PASS = ("Pass Reception", "Pass Incompletion", "Passing Touchdown", "Sack", "Pass Interception Return", "Interception Return Touchdown")


def expected_points(ytg: int, down: int = 1, distance: int = 10) -> float:
    """Expected points for the offense before a snap (the PPA baseline)."""
    ytg = max(1, min(99, int(ytg)))
    ep = _EP_ANCHORS[-1][1]
    for (y0, e0), (y1, e1) in zip(_EP_ANCHORS, _EP_ANCHORS[1:], strict=False):
        if y0 <= ytg <= y1:
            ep = e0 + (e1 - e0) * (ytg - y0) / (y1 - y0)
            break
    dist = max(1, min(distance, 30))
    if down == 2:
        ep -= 0.35 + 0.03 * dist
    elif down == 3:
        ep -= 0.9 + 0.06 * dist
    elif down == 4:
        ep -= 1.6 + 0.08 * dist
    else:
        ep -= 0.02 * (dist - 10)
    return ep


def fg_probability(distance: int, skill: float = 0.5) -> float:
    return 1.0 / (1.0 + math.exp(0.13 * (distance - 56 - 4 * (skill - 0.5))))


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def home_win_probability(home_margin: float, home_ball: bool, ytg: int, seconds_left: float, home_expected: float) -> float:
    """Chance the home team wins from here: the margin, the ball's worth, and the pregame edge for
    the time that is left, spread by how much time is left."""
    frac = max(0.0, min(1.0, seconds_left / 3600.0))
    ep = expected_points(ytg) if 1 <= ytg <= 99 else 0.0
    m = home_margin + (ep if home_ball else -ep) * min(1.0, 0.3 + frac) + home_expected * frac
    sigma = 13.5 * math.sqrt(frac) + 0.6
    return max(0.0005, min(0.9995, normal_cdf(m / sigma)))


@dataclass
class Side:
    """One team as the simulator sees it: ratings and the players it will use."""

    team_id: int
    school: str
    abbr: str
    offense: float  # points per game above an average offense
    defense: float  # points per game allowed above average (negative is good)
    special: float  # special teams points
    pass_rate: float  # share of called plays that are passes
    qbs: list[int]
    rbs: list[int]
    targets: list[tuple[int, float]]  # (player, weight): WR, TE, RB
    dline: list[int]
    lbs: list[int]
    dbs: list[int]
    kicker: int
    punter: int
    returner: int
    holder: int
    snapper: int
    kick_skill: float = 0.5


@dataclass(slots=True)
class Play:
    seq: int
    drive: int
    number: int  # within the drive
    side: int  # 0 home offense, 1 away offense (for kicks: the kicking team)
    period: int
    clock: int | None  # seconds left in the period before the snap; None in overtime
    ytg: int
    down: int
    distance: int
    gained: int
    ptype: str
    scoring: bool
    home_score: int  # before the play
    away_score: int
    home_after: int
    away_after: int
    off_timeouts: int
    def_timeouts: int
    ppa: float | None
    success: bool | None
    rush_pass: str  # rush, pass, other
    wall: int  # seconds after kickoff, wall clock
    wp: float  # home win probability after the play
    elapsed: int = 0  # game seconds the play used
    d: dict[str, Any] = field(default_factory=dict)  # who and how: players, kick details, penalty, air yards


@dataclass(slots=True)
class Drive:
    number: int
    side: int
    start_period: int
    start_clock: int | None
    start_ytg: int
    end_period: int = 0
    end_clock: int | None = None
    end_ytg: int = 0
    plays: int = 0
    yards: int = 0
    result: str = ""
    scoring: bool = False
    start_off_score: int = 0
    start_def_score: int = 0
    end_off_score: int = 0
    end_def_score: int = 0
    first_seq: int = 0
    last_seq: int = 0


@dataclass
class GameResult:
    plays: list[Play]
    drives: list[Drive]
    home_points: int
    away_points: int
    home_lines: list[int]
    away_lines: list[int]
    duration: int  # wall seconds kickoff to final
    excitement: float
    final_wp: float


class GameSim:
    """Plays one game. `home` and `away` are Sides; `home_expected` is the pregame expected home
    margin (positive favours home); `neutral` drops home field from the play model."""

    def __init__(self, seed: int, home: Side, away: Side, home_expected: float) -> None:
        self.rng = random.Random(seed)
        self.sides = (home, away)
        self.home_expected = home_expected
        self.plays: list[Play] = []
        self.drives: list[Drive] = []
        self.score = [0, 0]
        self.lines: list[list[int]] = [[0, 0, 0, 0], [0, 0, 0, 0]]
        self.timeouts = [3, 3]
        self.period = 1
        self.clock: int | None = PERIOD_SECONDS
        self.wall = 0
        self.seq = 0
        self.drive: Drive | None = None
        self.wps: list[float] = []

    # -- helpers ---------------------------------------------------------------------------
    def _edge(self, side: int) -> float:
        o, d = self.sides[side], self.sides[1 - side]
        return (o.offense + d.defense) / 20.0

    def _pick(self, items: list[int], weights: list[float] | None = None) -> int:
        if not items:
            return 0
        if weights:
            return self.rng.choices(items, weights=weights[: len(items)], k=1)[0]
        return self.rng.choice(items)

    def _qb(self, side: int) -> int:
        """The quarterback on the field: the starter, or the backup once a fourth quarter is out of reach."""
        qbs = self.sides[side].qbs
        if len(qbs) > 1 and self.period >= 4 and abs(self.score[0] - self.score[1]) > 24:
            return qbs[1]
        return qbs[0] if qbs else 0

    def _tacklers(self, defense: Side, deep: bool) -> list[int]:
        pool = (defense.dbs * 2 + defense.lbs) if deep else (defense.dline + defense.lbs * 2 + defense.dbs[:2])
        first = self._pick(pool)
        if self.rng.random() < 0.28:
            second = self._pick(pool)
            if second != first:
                return [first, second]
        return [first]

    def _seconds_left(self) -> float:
        if self.period > 4 or self.clock is None:
            return 0.0
        return (4 - self.period) * PERIOD_SECONDS + self.clock

    def _wp(self, side_with_ball: int, ytg: int) -> float:
        if self.period > 4:
            # overtime: close to even, leaning to whoever leads
            diff = self.score[0] - self.score[1]
            return 0.5 + max(-0.45, min(0.45, diff * 0.06))
        return home_win_probability(self.score[0] - self.score[1], side_with_ball == 0, ytg, self._seconds_left(), self.home_expected)

    def _use_clock(self, seconds: int) -> int:
        """Run the clock; returns the seconds actually used (stops at the end of the period)."""
        if self.clock is None:
            return 0
        used = min(self.clock, max(0, seconds))
        self.clock -= used
        return used

    def _add(self, side: int, ptype: str, ytg: int, down: int, distance: int, gained: int, *, scoring: bool = False,
             before: tuple[int, int], used: int, ppa: float | None, success: bool | None, rush_pass: str, d: dict[str, Any],
             next_ball: int, next_ytg: int) -> Play:
        self.seq += 1
        drive = self.drive
        number = 0
        if drive is not None:
            drive.plays += 1 if ptype not in ("Timeout", "End Period", "End of Half", "End of Game") else 0
            number = drive.plays
            drive.last_seq = self.seq
        wp = self._wp(next_ball, next_ytg)
        self.wall += used + (self.rng.randint(25, 45) if ptype not in ("Timeout", "End Period") else self.rng.randint(60, 150))
        play = Play(
            seq=self.seq, drive=drive.number if drive else 0, number=number, side=side, period=self.period,
            clock=self.clock + used if self.clock is not None else None, ytg=ytg, down=down, distance=distance,
            gained=gained, ptype=ptype, scoring=scoring, home_score=before[0], away_score=before[1],
            home_after=self.score[0], away_after=self.score[1], off_timeouts=self.timeouts[side],
            def_timeouts=self.timeouts[1 - side], ppa=ppa, success=success, rush_pass=rush_pass, wall=self.wall,
            wp=wp, elapsed=used, d=d,
        )
        self.plays.append(play)
        self.wps.append(wp)
        return play

    def _start_drive(self, side: int, ytg: int) -> None:
        """Open a drive for `side`, unless one is already open for it (a kickoff opens the
        receiving team's drive, as the feed files the kickoff as that drive's first play)."""
        if self.drive is not None and self.drive.side == side:
            self.drive.start_ytg = ytg
            return
        self._end_drive_if_open("", ytg)
        self.drive = Drive(
            number=len(self.drives) + 1, side=side, start_period=self.period, start_clock=self.clock,
            start_ytg=ytg, start_off_score=self.score[side], start_def_score=self.score[1 - side], first_seq=self.seq + 1,
        )
        self.drives.append(self.drive)

    def _end_drive_if_open(self, result: str, ytg: int | None = None) -> None:
        drive = self.drive
        if drive is None:
            return
        drive.result = result or drive.result or ("END OF HALF" if self.period <= 2 else "END OF GAME")
        drive.end_period = self.period
        drive.end_clock = self.clock
        drive.end_ytg = drive.start_ytg if ytg is None else max(0, min(100, ytg))
        drive.yards = drive.start_ytg - drive.end_ytg
        drive.end_off_score = self.score[drive.side]
        drive.end_def_score = self.score[1 - drive.side]
        drive.scoring = drive.result in ("TD", "FG")
        self.drive = None

    # -- kicks -----------------------------------------------------------------------------
    def _kickoff(self, kicking: int) -> int:
        """Kickoff by `kicking`; returns the receiving team's yards to goal."""
        rng = self.rng
        k = self.sides[kicking]
        r = self.sides[1 - kicking]
        before = (self.score[0], self.score[1])
        dist = rng.randint(58, 65)
        d: dict[str, Any] = {"kicker": k.kicker, "kick": dist}
        roll = rng.random()
        receive_ytg = 75
        used = 0
        ptype = "Kickoff"
        scoring = False
        if roll < 0.58:
            d["touchback"] = True
        elif roll < 0.66:
            d["fair_catch"] = True
            d["at"] = max(1, 65 - dist + 0)
            receive_ytg = 75
        else:
            land = max(0, 65 - dist)  # yards from the receiving goal line where it was fielded
            ret = max(0, int(rng.gauss(22, 8)))
            if rng.random() < 0.006:
                ret = 100 - land
            d.update(returner=r.returner, ret=ret, land=land)
            receive_ytg = 100 - (land + ret)
            used = rng.randint(4, 7)
            if receive_ytg <= 0:
                ptype = "Kickoff Return Touchdown"
                scoring = True
                self.score[1 - kicking] += 6
                self._quarter_points(1 - kicking, 6)
            else:
                d["tacklers"] = self._tacklers(k, deep=True)
        self._use_clock(used)
        self._start_drive(1 - kicking, max(1, min(99, receive_ytg)))
        self._add(kicking, ptype, 65, 0, 0, 0, scoring=scoring, before=before, used=used, ppa=None, success=None,
                  rush_pass="other", d=d, next_ball=1 - kicking, next_ytg=max(1, min(99, receive_ytg)))
        if scoring:
            self._end_drive_if_open("TD", 0)
            self._extra_point(1 - kicking)
            return -1
        return receive_ytg

    def _quarter_points(self, side: int, points: int) -> None:
        q = min(self.period, 4) - 1
        if self.period > 4:
            while len(self.lines[side]) < self.period:
                self.lines[0].append(0)
                self.lines[1].append(0)
            q = self.period - 1
        self.lines[side][q] += points

    def _extra_point(self, side: int) -> None:
        """Folded into the touchdown play's text in the feed; here it just scores."""
        s = self.sides[side]
        good = self.rng.random() < 0.97
        last = self.plays[-1]
        last.d["xp"] = good
        last.d["kicker"] = s.kicker
        last.d["holder"] = s.holder
        last.d["snapper"] = s.snapper
        if good:
            self.score[side] += 1
            self._quarter_points(side, 1)
            last.home_after, last.away_after = self.score[0], self.score[1]

    # -- the game --------------------------------------------------------------------------
    def run(self) -> GameResult:
        rng = self.rng
        first_receiver = 1 if rng.random() < 0.5 else 0
        kicking = 1 - first_receiver
        ball = None
        ytg = 75
        while True:
            if ball is None:
                r = self._kickoff(kicking)
                ball = 1 - kicking
                if r < 0:
                    kicking = ball
                    ball = None
                    if self._period_over():
                        if self._advance_period(first_receiver):
                            break
                        kicking, ball = self._half_kick(first_receiver)
                    continue
                ytg = r
            outcome, ball, ytg = self._drive(ball, ytg)
            if outcome == "score":
                kicking = ball  # the scoring team kicks off
                ball = None
            if self._period_over():
                if self._advance_period(first_receiver):
                    break
                if self.period == 3:
                    kicking, ball = self._half_kick(first_receiver)
        while self.score[0] == self.score[1]:
            self._overtime_period()
        self._end_drive_if_open("END OF GAME")
        before = (self.score[0], self.score[1])
        self.wall += 60
        self._add(0, "End of Game", 0, 0, 0, 0, before=before, used=0, ppa=None, success=None, rush_pass="other", d={},
                  next_ball=0, next_ytg=0)
        self.plays[-1].wp = 1.0 if self.score[0] > self.score[1] else 0.0
        excitement = sum(abs(a - b) for a, b in zip(self.wps, self.wps[1:], strict=False)) * 1.4
        lines = [list(self.lines[0]), list(self.lines[1])]
        return GameResult(
            plays=self.plays, drives=self.drives, home_points=self.score[0], away_points=self.score[1],
            home_lines=lines[0], away_lines=lines[1], duration=self.wall + 300, excitement=round(excitement, 4),
            final_wp=self.plays[-1].wp,
        )

    def _half_kick(self, first_receiver: int) -> tuple[int, None]:
        """Second half: the team that received first kicks."""
        return first_receiver, None

    def _period_over(self) -> bool:
        return self.clock is not None and self.clock <= 0

    def _advance_period(self, first_receiver: int) -> bool:
        """End the period; True when regulation is over."""
        before = (self.score[0], self.score[1])
        if self.period == 2:
            self._end_drive_if_open("END OF HALF")
        names = {1: "End Period", 2: "End Period", 3: "End Period", 4: "End Period"}
        self._add(0, names[self.period], 0, 0, 0, 0, before=before, used=0, ppa=None, success=None, rush_pass="other",
                  d={"ended": self.period}, next_ball=0, next_ytg=50)
        if self.period == 4:
            return True
        self.period += 1
        self.clock = PERIOD_SECONDS
        if self.period == 3:
            self.timeouts = [3, 3]
        return False

    def _overtime_period(self) -> None:
        self.period += 1
        self.clock = None
        while len(self.lines[0]) < self.period:
            self.lines[0].append(0)
            self.lines[1].append(0)
        first = self.rng.randint(0, 1)
        for side in (first, 1 - first):
            if self.period >= 7:
                self._two_point_try(side)
            else:
                self._drive(side, 25, overtime=True)

    def _two_point_try(self, side: int) -> None:
        before = (self.score[0], self.score[1])
        good = self.rng.random() < 0.45
        o = self.sides[side]
        d: dict[str, Any] = {"passer": o.qbs[0] if o.qbs else 0, "target": self._pick([t for t, _ in o.targets]), "two": good}
        if good:
            self.score[side] += 2
            self._quarter_points(side, 2)
        self._add(side, "Two Point Pass", 3, 0, 3, 3 if good else 0, scoring=good, before=before, used=0, ppa=None,
                  success=good, rush_pass="pass", d=d, next_ball=1 - side, next_ytg=3)

    def _drive(self, side: int, ytg: int, overtime: bool = False) -> tuple[str, int | None, int]:
        """Run one possession. Returns (outcome, next ball side or None for a kickoff, ytg)."""
        rng = self.rng
        self._start_drive(side, ytg)
        down, dist = 1, min(10, ytg)
        while True:
            if not overtime and self._period_over():
                if self.period in (1, 3):
                    self._advance_period(0)  # the possession carries over into the next quarter
                    continue
                self._end_drive_if_open("END OF HALF" if self.period == 2 else "END OF GAME", ytg)
                return "end", None, ytg
            # occasional timeouts near the end of a half or at random
            if not overtime and self.clock is not None and self.clock < 120 and self.period in (2, 4) and rng.random() < 0.12:
                taker = rng.randint(0, 1)
                if self.timeouts[taker] > 0:
                    self.timeouts[taker] -= 1
                    before = (self.score[0], self.score[1])
                    self._add(taker, "Timeout", ytg, down, dist, 0, before=before, used=0, ppa=None, success=None,
                              rush_pass="other", d={"team": taker}, next_ball=side, next_ytg=ytg)
            elif not overtime and rng.random() < 0.006 and self.timeouts[side] > 0:
                self.timeouts[side] -= 1
                before = (self.score[0], self.score[1])
                self._add(side, "Timeout", ytg, down, dist, 0, before=before, used=0, ppa=None, success=None,
                          rush_pass="other", d={"team": side}, next_ball=side, next_ytg=ytg)
            if down == 4:
                decision = self._fourth_down(side, ytg, dist, overtime)
                if decision == "punt":
                    return self._punt(side, ytg)
                if decision == "fg":
                    return self._field_goal(side, ytg, overtime)
            # penalties before or after the snap
            if rng.random() < 0.075:
                res = self._penalty(side, ytg, down, dist)
                if res is not None:
                    ytg, down, dist = res
                    continue
            result = self._scrimmage(side, ytg, down, dist)
            kind, new_ytg, gained = result
            if kind == "td":
                self._end_drive_if_open("TD", 0)
                self._extra_point(side)
                return "score", side, 0
            if kind == "safety":
                self._end_drive_if_open("SAFETY", 100)
                return "score", side, 0
            if kind == "turnover":
                result_name = self.plays[-1].d.get("result", "INT")
                if self.plays[-1].scoring:
                    self._end_drive_if_open(result_name + " TD", ytg)
                    self._extra_point(1 - side)
                    return "score", 1 - side, 0
                self._end_drive_if_open(result_name, new_ytg)
                if overtime:
                    return "end", None, 25
                return "turnover", 1 - side, 100 - new_ytg
            ytg = new_ytg
            if gained >= dist:
                down, dist = 1, min(10, ytg)
            else:
                down += 1
                dist -= gained
                if down > 4:
                    self._end_drive_if_open("DOWNS", ytg)
                    if overtime:
                        return "end", None, 25
                    return "downs", 1 - side, 100 - ytg

    def _fourth_down(self, side: int, ytg: int, dist: int, overtime: bool) -> str:
        rng = self.rng
        trailing = self.score[side] < self.score[1 - side]
        late = self.period == 4 and self.clock is not None and self.clock < 300
        if overtime:
            return "fg" if ytg <= 30 and (dist > 2 or rng.random() < 0.6) else "go"
        if late and trailing and (self.score[1 - side] - self.score[side]) > 3:
            return "go"
        if ytg <= 37:
            if dist <= 1 and ytg <= 5 and rng.random() < 0.55:
                return "go"
            if dist <= 2 and rng.random() < 0.18:
                return "go"
            return "fg"
        if dist <= 2 and ytg <= 60 and rng.random() < 0.45:
            return "go"
        if dist <= 1 and rng.random() < 0.2:
            return "go"
        return "punt"

    def _punt(self, side: int, ytg: int) -> tuple[str, int | None, int]:
        rng = self.rng
        o, r = self.sides[side], self.sides[1 - side]
        before = (self.score[0], self.score[1])
        gross = max(25, int(rng.gauss(43 + 2 * o.special, 6)))
        d: dict[str, Any] = {"punter": o.punter, "kick": gross}
        land = ytg - gross  # from the receiving goal line
        used = rng.randint(5, 9)
        if land <= 0:
            d["touchback"] = True
            gross = ytg
            d["kick"] = gross
            receive_ytg = 80
        else:
            roll = rng.random()
            if roll < 0.45:
                d["fair_catch"] = True
                d["returner"] = r.returner
                receive_ytg = 100 - land
            elif roll < 0.55:
                d["downed"] = True
                receive_ytg = 100 - land
            else:
                ret = max(0, int(rng.gauss(8, 7)))
                d.update(returner=r.returner, ret=ret, tacklers=self._tacklers(o, deep=True))
                receive_ytg = 100 - land - ret
        receive_ytg = max(1, min(99, receive_ytg))
        self._use_clock(used)
        ep_before = expected_points(ytg, 4, 1)
        ppa = round(-expected_points(receive_ytg) - ep_before, 3)
        self._add(side, "Punt", ytg, 4, 0, 0, before=before, used=used, ppa=ppa, success=None, rush_pass="other", d=d,
                  next_ball=1 - side, next_ytg=receive_ytg)
        self._end_drive_if_open("PUNT", ytg)
        return "punt", 1 - side, receive_ytg

    def _field_goal(self, side: int, ytg: int, overtime: bool) -> tuple[str, int | None, int]:
        rng = self.rng
        o = self.sides[side]
        before = (self.score[0], self.score[1])
        dist = ytg + 17
        good = rng.random() < fg_probability(dist, o.kick_skill)
        d = {"kicker": o.kicker, "holder": o.holder, "snapper": o.snapper, "kick": dist, "good": good}
        used = rng.randint(4, 6)
        self._use_clock(used)
        ep_before = expected_points(ytg, 4, 1)
        if good:
            self.score[side] += 3
            self._quarter_points(side, 3)
            ppa = round(3 - ep_before, 3)
            self._add(side, "Field Goal Good", ytg, 4, 0, 0, scoring=True, before=before, used=used, ppa=ppa, success=None,
                      rush_pass="other", d=d, next_ball=1 - side, next_ytg=75)
            self._end_drive_if_open("FG", ytg)
            return "score", side, 0
        miss_ytg = max(20, 100 - (ytg + 7))
        d["miss"] = rng.choice(("wide right", "wide left", "short"))
        ppa = round(-expected_points(miss_ytg) - ep_before, 3)
        self._add(side, "Field Goal Missed", ytg, 4, 0, 0, before=before, used=used, ppa=ppa, success=None,
                  rush_pass="other", d=d, next_ball=1 - side, next_ytg=miss_ytg)
        self._end_drive_if_open("MISSED FG", ytg)
        if overtime:
            return "end", None, 25
        return "missed", 1 - side, miss_ytg

    def _penalty(self, side: int, ytg: int, down: int, dist: int) -> tuple[int, int, int] | None:
        rng = self.rng
        on_offense = rng.random() < 0.55
        before = (self.score[0], self.score[1])
        if on_offense:
            name, yards = rng.choice((("False Start", 5), ("False Start", 5), ("Holding", 10), ("Delay of Game", 5), ("Illegal Formation", 5)))
            yards = min(yards, max(1, (100 - ytg) // 2)) if 100 - ytg <= 2 * yards else yards
            new_ytg = min(99, ytg + yards)
            gained = -yards
            new_down, new_dist = down, dist + yards
            first = False
        else:
            name, yards = rng.choice((("Offside", 5), ("Encroachment", 5), ("Pass Interference", 15), ("Personal Foul", 15), ("Roughing the Passer", 15), ("Defensive Holding", 5)))
            yards = min(yards, max(1, ytg // 2)) if ytg <= 2 * yards else yards
            new_ytg = max(1, ytg - yards)
            gained = yards
            first = yards >= dist or name in ("Pass Interference", "Personal Foul", "Roughing the Passer", "Defensive Holding")
            new_down, new_dist = (1, min(10, new_ytg)) if first else (down, dist - yards)
        flagged = side if on_offense else 1 - side
        d = {"flag": flagged, "name": name, "yards": yards, "first": first, "from": ytg, "to": new_ytg}
        self._use_clock(0)
        ppa = round(expected_points(new_ytg, new_down, new_dist) - expected_points(ytg, down, dist), 3)
        self._add(side, "Penalty", ytg, down, dist, gained, before=before, used=0, ppa=ppa, success=None, rush_pass="other",
                  d=d, next_ball=side, next_ytg=new_ytg)
        return new_ytg, new_down, new_dist

    def _scrimmage(self, side: int, ytg: int, down: int, dist: int) -> tuple[str, int, int]:
        """A run or a pass. Returns (kind, new ytg, yards gained); kind is play, td, turnover or safety."""
        rng = self.rng
        o, df = self.sides[side], self.sides[1 - side]
        edge = self._edge(side)
        late_lead = self.period == 4 and self.clock is not None and self.clock < 150 and self.score[side] > self.score[1 - side]
        pass_rate = o.pass_rate + (0.18 if dist >= 8 and down >= 2 else 0) - (0.15 if dist <= 2 else 0)
        if self.period == 4 and self.clock is not None and self.clock < 300:
            pass_rate += 0.25 if self.score[side] < self.score[1 - side] else -0.3
        before = (self.score[0], self.score[1])
        ep_before = expected_points(ytg, down, dist)
        down_type = "passing" if (down == 2 and dist >= 8) or (down >= 3 and dist >= 5) else "standard"
        d: dict[str, Any] = {"down_type": down_type, "form": rng.choice(("", "Shotgun ", "Shotgun ", "No Huddle-Shotgun ", "No Huddle "))}
        if late_lead and down <= 3 and self.clock is not None and self.clock < 100:
            # victory formation
            d.update(rusher=self._qb(side), kneel=True, dir="middle")
            gained = -1
            used = self._use_clock(40)
            new_ytg = min(99, ytg + 1)
            ppa = round(expected_points(new_ytg, min(4, down + 1), dist + 1) - ep_before, 3)
            self._add(side, "Rush", ytg, down, dist, gained, before=before, used=used, ppa=ppa, success=False, rush_pass="rush",
                      d=d, next_ball=side, next_ytg=new_ytg)
            return "play", new_ytg, gained
        if rng.random() < pass_rate:
            return self._pass(side, o, df, ytg, down, dist, edge, before, ep_before, d)
        return self._rush(side, o, df, ytg, down, dist, edge, before, ep_before, d)

    def _success(self, down: int, dist: int, gained: int) -> bool:
        need = {1: 0.5, 2: 0.7}.get(down, 1.0) * dist
        return gained >= need

    def _rush(self, side: int, o: Side, df: Side, ytg: int, down: int, dist: int, edge: float, before, ep_before: float, d) -> tuple[str, int, int]:
        rng = self.rng
        qb_run = rng.random() < 0.13
        rusher = self._qb(side) if qb_run and o.qbs else self._pick(o.rbs, [0.58, 0.28, 0.14])
        roll = rng.random()
        if roll < 0.06 + 0.012 * edge:
            gained = rng.randint(12, 30) if rng.random() < 0.8 else rng.randint(31, 80)
        elif roll < 0.20 - 0.02 * edge:
            gained = rng.randint(-4, 0)
        else:
            gained = max(-2, int(rng.gauss(4.0 + 0.9 * edge, 2.6)))
        if dist <= 2 and rng.random() < 0.15:
            gained = max(gained, rng.randint(0, 3))
        d.update(rusher=rusher, dir=rng.choice(("left", "middle", "middle", "right", "left end", "right end")))
        if gained >= ytg:
            gained = ytg
            used = self._use_clock(rng.randint(5, 9))
            self.score[side] += 6
            self._quarter_points(side, 6)
            ppa = round(6.95 - ep_before, 3)
            self._add(side, "Rushing Touchdown", ytg, down, dist, gained, scoring=True, before=before, used=used, ppa=ppa,
                      success=True, rush_pass="rush", d=d, next_ball=1 - side, next_ytg=75)
            return "td", 0, gained
        new_ytg = ytg - gained
        if new_ytg >= 100:
            return self._safety(side, ytg, down, dist, before, ep_before, d, "Rush")
        # fumbles
        if rng.random() < 0.012:
            lost = rng.random() < 0.5
            d.update(fumble=rusher, recovered=1 - side if lost else side, recoverer=self._pick(df.dline + df.lbs) if lost else rusher)
            used = self._use_clock(rng.randint(5, 9))
            if lost:
                d["result"] = "FUMBLE"
                ret = rng.randint(0, 6)
                d["ret"] = ret
                new_ytg = min(99, new_ytg + ret)
                ppa = round(-expected_points(100 - new_ytg) - ep_before, 3)
                self._add(side, "Fumble Recovery (Opponent)", ytg, down, dist, gained, before=before, used=used, ppa=ppa,
                          success=False, rush_pass="rush", d=d, next_ball=1 - side, next_ytg=100 - new_ytg)
                return "turnover", new_ytg, gained
            ppa = round(expected_points(new_ytg, min(4, down + 1), max(1, dist - gained)) - ep_before, 3)
            self._add(side, "Fumble Recovery (Own)", ytg, down, dist, gained, before=before, used=used, ppa=ppa,
                      success=self._success(down, dist, gained), rush_pass="rush", d=d, next_ball=side, next_ytg=new_ytg)
            return "play", new_ytg, gained
        d["tacklers"] = self._tacklers(df, deep=gained >= 10)
        out_of_bounds = rng.random() < 0.12
        used = self._use_clock(rng.randint(6, 9) if out_of_bounds else rng.randint(28, 40))
        first = gained >= dist
        d["first"] = first
        nd, nds = (1, min(10, new_ytg)) if first else (min(4, down + 1), max(1, dist - gained))
        ppa = round(expected_points(new_ytg, nd, nds) - ep_before, 3) if down < 4 or first else round(-expected_points(100 - new_ytg) - ep_before, 3)
        self._add(side, "Rush", ytg, down, dist, gained, before=before, used=used, ppa=ppa, success=self._success(down, dist, gained),
                  rush_pass="rush", d=d, next_ball=side if (first or down < 4) else 1 - side, next_ytg=new_ytg)
        return "play", new_ytg, gained

    def _safety(self, side: int, ytg: int, down: int, dist: int, before, ep_before: float, d, kind: str) -> tuple[str, int, int]:
        self.score[1 - side] += 2
        self._quarter_points(1 - side, 2)
        used = self._use_clock(self.rng.randint(5, 8))
        self._add(side, "Safety", ytg, down, dist, -ytg, scoring=True, before=before, used=used, ppa=round(-2 - ep_before, 3),
                  success=False, rush_pass="rush" if kind == "Rush" else "pass", d=d, next_ball=1 - side, next_ytg=60)
        return "safety", 100, -ytg

    def _pass(self, side: int, o: Side, df: Side, ytg: int, down: int, dist: int, edge: float, before, ep_before: float, d) -> tuple[str, int, int]:
        rng = self.rng
        qb = self._qb(side)
        d["passer"] = qb
        d["dir"] = rng.choice(("left", "middle", "right", "left", "right"))
        # sacks
        if rng.random() < 0.062 - 0.015 * edge:
            loss = max(1, int(rng.gauss(7, 3)))
            gained = -loss
            sackers = [self._pick(df.dline + df.dline + df.lbs)]
            if rng.random() < 0.2:
                sackers.append(self._pick(df.dline + df.lbs))
            d.update(sackers=sackers, sack=True)
            new_ytg = ytg + loss
            if new_ytg >= 100:
                return self._safety(side, ytg, down, dist, before, ep_before, d, "Pass")
            if rng.random() < 0.08:
                lost = rng.random() < 0.55
                d.update(fumble=qb, recovered=1 - side if lost else side, recoverer=sackers[0] if lost else qb)
                if lost:
                    d["result"] = "FUMBLE"
                    used = self._use_clock(rng.randint(5, 8))
                    ppa = round(-expected_points(100 - new_ytg) - ep_before, 3)
                    self._add(side, "Fumble Recovery (Opponent)", ytg, down, dist, gained, before=before, used=used, ppa=ppa,
                              success=False, rush_pass="pass", d=d, next_ball=1 - side, next_ytg=100 - new_ytg)
                    return "turnover", new_ytg, gained
            used = self._use_clock(rng.randint(25, 38))
            nd, nds = min(4, down + 1), dist + loss
            ppa = round(expected_points(new_ytg, nd, nds) - ep_before, 3) if down < 4 else round(-expected_points(100 - new_ytg) - ep_before, 3)
            self._add(side, "Sack", ytg, down, dist, gained, before=before, used=used, ppa=ppa, success=False, rush_pass="pass",
                      d=d, next_ball=side if down < 4 else 1 - side, next_ytg=new_ytg)
            return "play", new_ytg, gained
        targets = [t for t, _ in o.targets]
        weights = [w for _, w in o.targets]
        target = self._pick(targets, weights)
        deep = rng.random() < 0.2
        air = rng.randint(16, min(55, max(16, ytg))) if deep else rng.randint(-3, min(15, max(1, ytg)))
        air = min(air, ytg)
        d.update(target=target, air=air, depth="deep" if deep else "short")
        if rng.random() < 0.18:
            d["hurry"] = self._pick(df.dline + df.lbs)
        # interceptions
        int_rate = (0.022 - 0.007 * edge) * (1.8 if deep else 1.0)
        if rng.random() < int_rate:
            picker = self._pick(df.dbs + df.dbs + df.lbs)
            ret = max(0, int(rng.gauss(10, 10)))
            spot = ytg - air  # where it was caught, from the passing team's view: yards to goal
            spot = max(1, min(99, spot))
            back = 100 - spot  # the defense's yards to goal at the catch
            d.update(interceptor=picker, ret=ret, result="INT", at=spot)
            used = self._use_clock(rng.randint(6, 10))
            if ret >= back:
                d["ret"] = back
                self.score[1 - side] += 6
                self._quarter_points(1 - side, 6)
                ppa = round(-6.95 - ep_before, 3)
                self._add(side, "Interception Return Touchdown", ytg, down, dist, 0, scoring=True, before=before, used=used,
                          ppa=ppa, success=False, rush_pass="pass", d=d, next_ball=side, next_ytg=75)
                return "turnover", 0, 0
            new_def_ytg = back - ret
            ptype = "Pass Interception Return" if ret > 0 else "Interception"
            ppa = round(-expected_points(new_def_ytg) - ep_before, 3)
            if ret > 0:
                d["tacklers"] = [self._pick(o.targets and [t for t, _ in o.targets] or [qb])]
            self._add(side, ptype, ytg, down, dist, 0, before=before, used=used, ppa=ppa, success=False, rush_pass="pass",
                      d=d, next_ball=1 - side, next_ytg=new_def_ytg)
            return "turnover", 100 - new_def_ytg, 0
        comp = 0.66 + 0.05 * edge - (0.2 if deep else 0) - (0.04 if down_is_passing(d) else 0)
        if rng.random() < comp:
            yac = max(0, int(rng.expovariate(1 / (4.5 + edge)))) if not deep else max(0, int(rng.expovariate(1 / 6)))
            gained = air + yac
            if rng.random() < 0.05:
                gained += rng.randint(10, 40)
                yac = gained - air
            gained = min(gained, ytg)
            yac = gained - air
            d.update(yac=yac, complete=True)
            new_ytg = ytg - gained
            if new_ytg <= 0:
                used = self._use_clock(rng.randint(5, 9))
                self.score[side] += 6
                self._quarter_points(side, 6)
                ppa = round(6.95 - ep_before, 3)
                self._add(side, "Passing Touchdown", ytg, down, dist, gained, scoring=True, before=before, used=used, ppa=ppa,
                          success=True, rush_pass="pass", d=d, next_ball=1 - side, next_ytg=75)
                return "td", 0, gained
            if rng.random() < 0.008:
                lost = rng.random() < 0.5
                d.update(fumble=target, recovered=1 - side if lost else side, recoverer=self._pick(df.dbs) if lost else target)
                if lost:
                    d["result"] = "FUMBLE"
                    used = self._use_clock(rng.randint(5, 9))
                    ppa = round(-expected_points(100 - new_ytg) - ep_before, 3)
                    self._add(side, "Fumble Recovery (Opponent)", ytg, down, dist, gained, before=before, used=used, ppa=ppa,
                              success=False, rush_pass="pass", d=d, next_ball=1 - side, next_ytg=100 - new_ytg)
                    return "turnover", new_ytg, gained
            d["tacklers"] = self._tacklers(df, deep=gained >= 12)
            out_of_bounds = rng.random() < 0.25
            used = self._use_clock(rng.randint(6, 9) if out_of_bounds else rng.randint(24, 36))
            first = gained >= dist
            d["first"] = first
            nd, nds = (1, min(10, new_ytg)) if first else (min(4, down + 1), max(1, dist - gained))
            ppa = round(expected_points(new_ytg, nd, nds) - ep_before, 3) if down < 4 or first else round(-expected_points(100 - new_ytg) - ep_before, 3)
            self._add(side, "Pass Reception", ytg, down, dist, gained, before=before, used=used, ppa=ppa,
                      success=self._success(down, dist, gained), rush_pass="pass", d=d,
                      next_ball=side if (first or down < 4) else 1 - side, next_ytg=new_ytg)
            return "play", new_ytg, gained
        if rng.random() < 0.3:
            d["broken_up"] = self._pick(df.dbs + df.lbs)
        used = self._use_clock(rng.randint(4, 7))
        nd, nds = min(4, down + 1), dist
        ppa = round(expected_points(ytg, nd, nds) - ep_before, 3) if down < 4 else round(-expected_points(100 - ytg) - ep_before, 3)
        self._add(side, "Pass Incompletion", ytg, down, dist, 0, before=before, used=used, ppa=ppa, success=False,
                  rush_pass="pass", d=d, next_ball=side if down < 4 else 1 - side, next_ytg=ytg)
        return "play", ytg, 0


def down_is_passing(d: dict[str, Any]) -> bool:
    return d.get("down_type") == "passing"
