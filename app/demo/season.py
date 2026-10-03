"""Both seasons of the made-up league, played out: every game, Elo, standings, conference
championships, bowls, the 12-team playoff, weekly polls and the rating systems.

The whole of each season is simulated up front, the current one included; what the outside world
may see is decided by a clock (`World.now`). A game is final once its last play is over, polls
come out on Sundays (the committee's on Tuesdays from week 10), and season numbers count only the
games that are final. That is what lets the demo play a game "live" without re-running anything.
"""

from __future__ import annotations

import bisect
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from app.demo import names as N
from app.demo import stats as S
from app.demo.league import GameSlot, League, Player, Team, saturday
from app.demo.sim import HOME_FIELD, GameResult, GameSim, Side, normal_cdf

POLLS = ("AP Top 25", "Coaches Poll")
COMMITTEE = "Playoff Committee Rankings"
POLL_VOTERS = {"AP Top 25": 63, "Coaches Poll": 66}


@dataclass
class Record:
    """One game, simulated: the slot plus everything the endpoints need without the plays."""

    slot: GameSlot
    home_points: int
    away_points: int
    home_lines: list[int]
    away_lines: list[int]
    excitement: float
    duration: int
    home_pre_elo: int
    away_pre_elo: int
    home_post_elo: int
    away_post_elo: int
    home_expected: float
    home_wp_pre: float
    attendance: int
    counts: tuple[Counter, Counter]
    advanced: tuple[Counter, Counter]
    lines: tuple[dict[int, Counter], dict[int, Counter]]
    ppa: tuple[dict[int, Counter], dict[int, Counter]]
    usage: tuple[Counter, Counter]
    ppa_split: tuple[dict, dict]
    drives: tuple[int, int]

    @property
    def id(self) -> int:
        return self.slot.id

    @property
    def end(self) -> datetime:
        return self.slot.start + timedelta(seconds=self.duration)

    @property
    def spread(self) -> float:
        """CFBD's spread: negative when the home team is favoured."""
        return -round(self.home_expected * 2) / 2

    def side_of(self, team_id: int) -> int:
        return 0 if self.slot.home == team_id else 1


@dataclass
class SeasonData:
    year: int
    records: list[Record] = field(default_factory=list)
    by_id: dict[int, Record] = field(default_factory=dict)
    sides: dict[int, Side] = field(default_factory=dict)
    elo_start: dict[int, float] = field(default_factory=dict)
    preseason: dict[int, float] = field(default_factory=dict)  # projected strength (points)
    strength: dict[int, tuple[float, float, float]] = field(default_factory=dict)  # offense, defense, special
    ends: list[datetime] = field(default_factory=list)  # sorted end times
    by_end: list[Record] = field(default_factory=list)


class World:
    """The league plus both simulated seasons."""

    def __init__(self, league: League) -> None:
        self.league = league
        self.season = league.season
        self.seasons: dict[int, SeasonData] = {}
        self.pos_of: dict[int, str] = {int(pid): p.position for pid, p in league.players.items()}
        self.who_cache: dict[int, tuple[int, str]] = {}
        elo = self._initial_elo()
        for year in (self.season - 1, self.season):
            data = SeasonData(year)
            self.seasons[year] = data
            self._ratings(data)
            data.elo_start = dict(elo)
            elo = self._play_season(data, elo)
            elo = {tid: 1500 + (v - 1500) * 0.7 for tid, v in elo.items()}

    # -- setup -------------------------------------------------------------------------------
    def _initial_elo(self) -> dict[int, float]:
        rng = random.Random(self.league.seed * 13)
        return {t.id: 1500 + 500 * (t.prestige - 0.45) + rng.gauss(0, 60) if t.is_fbs else 1150 + rng.gauss(0, 60) for t in self.league.teams}

    def _ratings(self, data: SeasonData) -> None:
        """Team strength from the players on the field this season."""
        league = self.league
        year = data.year
        rng = random.Random(league.seed * 101 + year)
        raw: dict[int, tuple[float, float]] = {}
        for team in league.teams:
            roster = league.roster(team.id, year)
            side, off_ab, def_ab = self._depth(team, roster, year)
            data.sides[team.id] = side
            raw[team.id] = (off_ab, def_ab)
        fbs_ids = [t.id for t in league.fbs]
        mo = sum(raw[t][0] for t in fbs_ids) / len(fbs_ids)
        md = sum(raw[t][1] for t in fbs_ids) / len(fbs_ids)
        so = math.sqrt(sum((raw[t][0] - mo) ** 2 for t in fbs_ids) / len(fbs_ids)) or 1
        sd = math.sqrt(sum((raw[t][1] - md) ** 2 for t in fbs_ids) / len(fbs_ids)) or 1
        for team in league.teams:
            off_ab, def_ab = raw[team.id]
            if team.is_fbs:
                offense = 7.5 * (off_ab - mo) / so + rng.gauss(0, 2.0)
                defense = -7.5 * (def_ab - md) / sd + rng.gauss(0, 2.0)
            else:
                offense = rng.gauss(-13, 3)
                defense = rng.gauss(13, 3)
            special = rng.gauss(0, 1.0)
            side = data.sides[team.id]
            side.offense, side.defense, side.special = offense, defense, special
            side.pass_rate = max(0.38, min(0.62, 0.5 + 0.04 * (offense / 7.5) + rng.gauss(0, 0.04)))
            data.strength[team.id] = (offense, defense, special)
            data.preseason[team.id] = offense - defense + special + rng.gauss(0, 3.0)

    def _depth(self, team: Team, roster: list[Player], year: int) -> tuple[Side, float, float]:
        def best(positions: tuple[str, ...], n: int) -> list[Player]:
            pool = sorted((p for p in roster if p.position in positions), key=lambda p: -p.ability(year))
            return pool[:n]

        def ids(players: list[Player]) -> list[int]:
            return [int(p.id) for p in players]

        def avg(players: list[Player]) -> float:
            return sum(p.ability(year) for p in players) / len(players) if players else 0.2

        qbs = best(("QB",), 2) or best(("RB", "WR"), 1)
        rbs = best(("RB",), 3) or best(("WR",), 2)
        wrs = best(("WR",), 4)
        tes = best(("TE",), 2)
        ol = best(("OL",), 5)
        dl = best(("DL",), 4)
        lbs = best(("LB",), 3)
        dbs = best(("CB", "S", "DB"), 4)
        kicker = best(("PK",), 1) or best(("P",), 1) or best(("WR",), 1)
        punter = best(("P",), 1) or best(("PK",), 1) or kicker
        snapper = best(("LS",), 1) or best(("OL",), 1)[-1:] or kicker
        returner = (wrs[2:3] or rbs[1:2] or dbs[:1] or rbs[:1])
        targets: list[tuple[int, float]] = []
        for players, weights in ((wrs, (0.24, 0.19, 0.14, 0.07)), (tes, (0.14, 0.04)), (rbs, (0.10, 0.05))):
            for p, w in zip(players, weights, strict=False):
                targets.append((int(p.id), w))
        if not targets:
            targets = [(int(qbs[0].id), 1.0)] if qbs else [(0, 1.0)]
        side = Side(
            team_id=team.id, school=team.school, abbr=team.abbr, offense=0, defense=0, special=0, pass_rate=0.5,
            qbs=ids(qbs) or [0], rbs=ids(rbs) or ids(qbs), targets=targets, dline=ids(dl) or ids(lbs), lbs=ids(lbs) or ids(dl),
            dbs=ids(dbs) or ids(lbs), kicker=int(kicker[0].id) if kicker else 0, punter=int(punter[0].id) if punter else 0,
            returner=int(returner[0].id) if returner else 0, holder=int(punter[0].id) if punter else 0,
            snapper=int(snapper[0].id) if snapper else 0, kick_skill=avg(kicker),
        )
        off_ab = 0.3 * avg(qbs[:1]) + 0.25 * avg(ol) + 0.25 * avg(wrs[:3] + tes[:1]) + 0.2 * avg(rbs[:2])
        def_ab = 0.35 * avg(dl) + 0.25 * avg(lbs) + 0.4 * avg(dbs)
        return side, off_ab, def_ab

    # -- playing ---------------------------------------------------------------------------
    def _sim(self, slot: GameSlot, data: SeasonData) -> tuple[GameResult, float, Side, Side]:
        home = data.sides[slot.home]
        away = data.sides[slot.away]
        hfa = 0.0 if slot.neutral else HOME_FIELD
        ho, hd, hs = data.strength[slot.home]
        ao, ad, as_ = data.strength[slot.away]
        expected = (ho - hd + hs) - (ao - ad + as_) + hfa
        h = replace(home, offense=home.offense + hfa / 2, defense=home.defense - hfa / 2)
        a = replace(away)
        result = GameSim(slot.id, h, a, expected).run()
        return result, expected, h, a

    def simulate(self, game_id: int) -> GameResult | None:
        """The plays of one game (simulated again; the season pass kept only the totals)."""
        return _cached_sim(self, game_id)

    def _play_season(self, data: SeasonData, elo: dict[int, float]) -> dict[int, float]:
        league = self.league
        slots = sorted(league.schedules[data.year], key=lambda s: (s.start, s.id))
        elo = dict(elo)
        for slot in slots:
            self._record(slot, data, elo)
        champs = self._championships(data, elo)
        for slot in champs:
            self._record(slot, data, elo)
        league.schedules[data.year].extend(champs)
        post = self._postseason(data, elo)
        league.schedules[data.year].extend(post)
        data.by_end = sorted(data.records, key=lambda r: (r.end, r.id))
        data.ends = [r.end for r in data.by_end]
        return elo

    def _record(self, slot: GameSlot, data: SeasonData, elo: dict[int, float]) -> Record:
        result, expected, _, _ = self._sim(slot, data)
        rng = random.Random(slot.id)
        he, ae = elo[slot.home], elo[slot.away]
        margin = result.home_points - result.away_points
        hfa_elo = 0 if slot.neutral else 55
        exp_home = 1 / (1 + 10 ** ((ae - he - hfa_elo) / 400))
        won = 1.0 if margin > 0 else 0.0
        k = 25 * math.log(abs(margin) + 1) * (2.2 / ((he - ae if won else ae - he) * 0.001 + 2.2))
        delta = k * (won - exp_home)
        elo[slot.home] = he + delta
        elo[slot.away] = ae - delta
        counts = (S.team_counts(result, 0, self._pos), S.team_counts(result, 1, self._pos))
        advanced = (S.advanced_counts(result, 0, self._pos), S.advanced_counts(result, 1, self._pos))
        lines = (dict(S.player_lines(result, 0)), dict(S.player_lines(result, 1)))
        ppa = (dict(S.ppa_lines(result, 0)), dict(S.ppa_lines(result, 1)))
        usage = (S.usage_base(result, 0), S.usage_base(result, 1))
        split = (S.ppa_split(S.scrimmage(result.plays, 0)), S.ppa_split(S.scrimmage(result.plays, 1)))
        venue = slot.venue
        record = Record(
            slot=slot, home_points=result.home_points, away_points=result.away_points, home_lines=result.home_lines,
            away_lines=result.away_lines, excitement=result.excitement, duration=result.duration,
            home_pre_elo=round(he), away_pre_elo=round(ae), home_post_elo=round(elo[slot.home]), away_post_elo=round(elo[slot.away]),
            home_expected=expected, home_wp_pre=round(min(0.999, max(0.001, normal_cdf(expected / 14.0))), 3),
            attendance=int(venue.capacity * rng.uniform(0.62, 1.02)), counts=counts, advanced=advanced, lines=lines, ppa=ppa,
            usage=usage, ppa_split=split, drives=(sum(1 for d in result.drives if d.side == 0), sum(1 for d in result.drives if d.side == 1)),
        )
        data.records.append(record)
        data.by_id[slot.id] = record
        return record

    def _pos(self, pid: int) -> str:
        return self.pos_of.get(pid, "")

    def standings(self, data: SeasonData, records: list[Record] | None = None) -> dict[int, dict[str, Counter]]:
        out: dict[int, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        for r in records if records is not None else data.records:
            s = r.slot
            for side, tid in ((0, s.home), (1, s.away)):
                pts = (r.home_points, r.away_points)
                won = pts[side] > pts[1 - side]
                buckets = ["total", "regularSeason" if s.season_type == "regular" else "postseason"]
                if s.conference_game:
                    buckets.append("conferenceGames")
                buckets.append("neutralSiteGames" if s.neutral else ("homeGames" if side == 0 else "awayGames"))
                for b in buckets:
                    out[tid][b]["games"] += 1
                    out[tid][b]["wins" if won else "losses"] += 1
                out[tid]["_"]["expected"] += r.home_wp_pre if side == 0 else 1 - r.home_wp_pre
        return out

    def _championships(self, data: SeasonData, elo: dict[int, float]) -> list[GameSlot]:
        league = self.league
        table = self.standings(data)
        slots: list[GameSlot] = []
        rng = random.Random(league.seed * 17 + data.year)
        by_conf: dict[str, list[Team]] = defaultdict(list)
        for t in league.fbs:
            if t.conference != "FBS Independents":
                by_conf[t.conference].append(t)
        for conference, members in by_conf.items():
            ranked = sorted(members, key=lambda t: (-table[t.id]["conferenceGames"]["wins"], -table[t.id]["total"]["wins"], -elo[t.id]))
            a, b = ranked[0], ranked[1]
            start = datetime.combine(saturday(data.year, 15), datetime.min.time(), timezone.utc) + timedelta(hours=rng.choice((17, 20, 24)))
            venue = rng.choice([t.venue for t in league.fbs if t.venue.capacity > 60_000])
            slots.append(GameSlot(
                id=league.next_game_id(data.year), season=data.year, week=15, season_type="regular", start=start, tbd=False,
                home=a.id, away=b.id, neutral=True, conference_game=True, venue=venue, notes=f"{conference} Championship",
                outlet=rng.choice(N.NETWORKS[:4]), announce=datetime.combine(saturday(data.year, 14), datetime.min.time(), timezone.utc) + timedelta(days=1, hours=8),
            ))
        return slots

    def power(self, data: SeasonData, elo: dict[int, float], records: list[Record]) -> dict[int, float]:
        table = self.standings(data, records)
        return {t.id: elo[t.id] + 35 * table[t.id]["total"]["wins"] - 70 * table[t.id]["total"]["losses"] for t in self.league.fbs}

    def _postseason(self, data: SeasonData, elo: dict[int, float]) -> list[GameSlot]:
        league = self.league
        rng = random.Random(league.seed * 23 + data.year)
        power = self.power(data, elo, data.records)
        ranked = sorted(league.fbs, key=lambda t: -power[t.id])
        champs = {data.by_id[s.id].slot.home if data.by_id[s.id].home_points > data.by_id[s.id].away_points else data.by_id[s.id].slot.away
                  for s in league.schedules[data.year] if s.week == 15}
        champ_ranked = [t for t in ranked if t.id in champs][:5]
        field_ids: list[int] = [t.id for t in champ_ranked]
        for t in ranked:
            if len(field_ids) >= 12:
                break
            if t.id not in field_ids:
                field_ids.append(t.id)
        seeds = sorted(field_ids, key=lambda tid: -power[tid])
        seed_of = {tid: i + 1 for i, tid in enumerate(seeds)}
        data.__dict__["playoff_seeds"] = seed_of
        data.__dict__["selection_power"] = power  # the committee's last ranking is this order
        selection = datetime.combine(saturday(data.year, 15), datetime.min.time(), timezone.utc) + timedelta(days=1, hours=20)
        feeds = {"QF1": "FR4", "QF2": "FR1", "QF3": "FR3", "QF4": "FR2", "SF1": "QF2", "SF2": "QF4", "CH": "SF2"}
        ends: dict[str, datetime] = {}
        dec = datetime(data.year, 12, 1, tzinfo=timezone.utc)
        third_sat = dec + timedelta(days=(5 - dec.weekday()) % 7 + 14)
        slots: list[GameSlot] = []
        results: dict[str, int] = {}

        def play(slot_name: str, round_key: str, round_name: str, hi: int, lo: int, when: datetime, bowl: str | None) -> int:
            home, away = (hi, lo) if seed_of[hi] < seed_of[lo] else (lo, hi)
            neutral = round_key != "first_round"
            venue = league.by_id[home].venue if not neutral else rng.choice([t.venue for t in league.fbs if t.venue.capacity > 70_000])
            bowl_name = bowl or "College Football Playoff First Round Game"
            notes = ("College Football Playoff First Round Game" if round_key == "first_round"
                     else f"College Football Playoff {round_name} at the {bowl}" if round_key != "championship"
                     else "College Football Playoff National Championship")
            slot = GameSlot(
                id=league.next_game_id(data.year), season=data.year, week=1, season_type="postseason", start=when, tbd=False,
                home=home, away=away, neutral=neutral, conference_game=False, venue=venue, notes=notes,
                playoff={"competition": "cfp", "format": "twelve_team_2025", "round": round_key, "roundName": round_name,
                         "bracketSlot": slot_name, "homeSeed": seed_of[home], "awaySeed": seed_of[away],
                         "bowlName": bowl if bowl else ("College Football Playoff National Championship" if round_key == "championship" else bowl_name)},
                outlet=rng.choice(N.NETWORKS[:2]), announce=ends.get(feeds.get(slot_name, ""), selection),
            )
            if slot_name in ("SF1", "SF2", "CH"):
                slot.announce = max(ends.get(k, selection) for k in {"SF1": ("QF1", "QF2"), "SF2": ("QF3", "QF4"), "CH": ("SF1", "SF2")}[slot_name])
            slots.append(slot)
            rec = self._record(slot, data, elo)
            ends[slot_name] = rec.end
            winner = home if rec.home_points > rec.away_points else away
            results[slot_name] = winner
            return winner

        s = seeds
        fr_time = third_sat + timedelta(hours=20)
        play("FR1", "first_round", "First Round", s[4], s[11], fr_time + timedelta(days=1), None)
        play("FR2", "first_round", "First Round", s[5], s[10], fr_time, None)
        play("FR3", "first_round", "First Round", s[6], s[9], fr_time + timedelta(hours=4), None)
        play("FR4", "first_round", "First Round", s[7], s[8], fr_time - timedelta(hours=4), None)
        sites = list(N.PLAYOFF_SITES)
        rng.shuffle(sites)
        qf = datetime(data.year, 12, 31, 22, tzinfo=timezone.utc)
        play("QF1", "quarterfinal", "Quarterfinal", s[0], results["FR4"], qf + timedelta(days=1), sites[0])
        play("QF2", "quarterfinal", "Quarterfinal", s[3], results["FR1"], qf + timedelta(days=1, hours=4), sites[1])
        play("QF3", "quarterfinal", "Quarterfinal", s[1], results["FR3"], qf, sites[2])
        play("QF4", "quarterfinal", "Quarterfinal", s[2], results["FR2"], qf + timedelta(days=2), sites[3])
        sf = datetime(data.year + 1, 1, 9, 0, 30, tzinfo=timezone.utc)
        play("SF1", "semifinal", "Semifinal", results["QF1"], results["QF2"], sf + timedelta(days=1), sites[4])
        play("SF2", "semifinal", "Semifinal", results["QF3"], results["QF4"], sf, sites[5])
        play("CH", "championship", "National Championship", results["SF1"], results["SF2"], datetime(data.year + 1, 1, 20, 0, 30, tzinfo=timezone.utc), None)
        # bowls for the other teams with six wins
        table = self.standings(data)
        eligible = [t for t in ranked if t.id not in field_ids and table[t.id]["total"]["wins"] >= 6]
        bowls = list(N.BOWLS)
        rng.shuffle(bowls)
        pairs: list[tuple[Team, Team]] = []
        pool = eligible[:]
        while len(pool) >= 2 and bowls:
            a = pool.pop(0)
            partner = next((b for b in pool if b.conference != a.conference), pool[0])
            pool.remove(partner)
            pairs.append((a, partner))
        for i, (a, b) in enumerate(pairs[: len(bowls)]):
            when = datetime(data.year, 12, 16, 19, tzinfo=timezone.utc) + timedelta(hours=int(i * 18.5 % (18 * 24)))
            venue = rng.choice(self.league.venues[:136])
            slot = GameSlot(
                id=league.next_game_id(data.year), season=data.year, week=1, season_type="postseason", start=when, tbd=False,
                home=a.id, away=b.id, neutral=True, conference_game=False, venue=venue, notes=bowls[i], outlet=rng.choice(N.NETWORKS),
                announce=selection,
            )
            slots.append(slot)
            self._record(slot, data, elo)
        return slots

    # -- what the clock allows -------------------------------------------------------------
    def final(self, year: int, now: datetime) -> list[Record]:
        data = self.seasons.get(year)
        if data is None:
            return []
        k = bisect.bisect_right(data.ends, now)
        return data.by_end[:k]

    def is_final(self, record: Record, now: datetime) -> bool:
        return record.end <= now

    def in_progress(self, record: Record, now: datetime) -> bool:
        return record.slot.start <= now < record.end

    def who(self, pid: int) -> tuple[int, str]:
        cached = self.who_cache.get(pid)
        if cached is not None:
            return cached
        player = self.league.players.get(str(pid))
        if player is None:
            out = (0, "TEAM")
        else:
            season = self.season
            stint = player.stint_in(season) or player.stint_in(season - 1) or (player.stints[-1] if player.stints else None)
            out = (stint.jersey if stint else 0, player.short)
        self.who_cache[pid] = out
        return out

    def jersey(self, player: Player, year: int) -> int:
        stint = player.stint_in(year) or (player.stints[-1] if player.stints else None)
        return stint.jersey if stint else 0

    # -- ratings over time -----------------------------------------------------------------
    def team_strength_now(self, year: int, now: datetime) -> dict[int, dict[str, float]]:
        """SP+-like ratings through the final games: the preseason projection, then more and more
        the season's own opponent-adjusted margins."""
        return _strength(self, year, len(self.final(year, now)))


@lru_cache(maxsize=64)
def _cached_sim(world: World, game_id: int) -> GameResult | None:
    for data in world.seasons.values():
        record = data.by_id.get(game_id)
        if record is not None:
            return world._sim(record.slot, data)[0]
    return None


@lru_cache(maxsize=64)
def _strength(world: World, year: int, count: int) -> dict[int, dict[str, float]]:
    data = world.seasons[year]
    records = data.by_end[:count]
    perf: dict[int, list[tuple[float, float]]] = defaultdict(list)
    pre = data.preseason
    for r in records:
        s = r.slot
        hfa = 0 if s.neutral else HOME_FIELD
        for side, tid, opp in ((0, s.home, s.away), (1, s.away, s.home)):
            pf = r.home_points if side == 0 else r.away_points
            pa = r.away_points if side == 0 else r.home_points
            adj = (hfa if side == 1 else -hfa) / 2
            perf[tid].append((pf + adj - 28 + 0.5 * pre.get(opp, -10) / 2, pa - adj - 28 - 0.5 * pre.get(opp, -10) / 2))
    out: dict[int, dict[str, float]] = {}
    for t in world.league.teams:
        o_true, d_true, st = data.strength[t.id]
        games = perf.get(t.id, [])
        w = len(games) / (len(games) + 4)
        off_perf = sum(g[0] for g in games) / len(games) if games else 0.0
        def_perf = sum(g[1] for g in games) / len(games) if games else 0.0
        pre_off = o_true + (pre[t.id] - (o_true - d_true + st)) / 2
        pre_def = d_true - (pre[t.id] - (o_true - d_true + st)) / 2
        offense = (1 - w) * pre_off + w * (0.6 * off_perf + 0.4 * o_true)
        defense = (1 - w) * pre_def + w * (0.6 * def_perf + 0.4 * d_true)
        out[t.id] = {"offense": offense, "defense": defense, "special": st, "rating": offense - defense + st, "games": len(games)}
    return out


def build_world(seed: int = 2026, season: int = 2026) -> World:
    return World(League(seed, season))


def last_completed_week(world: World, now: datetime) -> tuple[str, int]:
    """(seasonType, week) of the latest week whose games are all final."""
    year = world.season
    data = world.seasons[year]
    weeks: dict[tuple[str, int], bool] = {}
    for r in data.records:
        key = (r.slot.season_type, r.slot.week)
        weeks[key] = weeks.get(key, True) and r.end <= now
    done = [k for k, ok in weeks.items() if ok]
    if not done:
        return ("regular", 0)
    return max(done, key=lambda k: (k[0] == "postseason", k[1]))


def any_of(values: list[Any]) -> Any:
    return values[0] if values else None
