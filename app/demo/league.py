"""The made-up league: teams, venues, coaches, players, recruiting classes, transfers and schedules.

Everything is drawn from one seeded generator, in a fixed order, so a league built twice with the
same seed and season is identical. Seasons run like the real calendar: week 1 on the last Saturday
of August, conference championships in week 15, the postseason after that.
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.demo import names as N

STATE_FIPS = {
    "AL": "01", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "FL": "12", "GA": "13", "ID": "16",
    "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25",
    "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}

RECRUIT_POSITIONS = {
    "WR": 530, "IOL": 376, "DL": 369, "LB": 360, "S": 329, "ATH": 320, "CB": 319, "OT": 296, "EDGE": 293,
    "QB": 255, "RB": 237, "TE": 221, "K": 30, "P": 22, "LS": 18,
}

# (height range in inches, weight range in pounds) by roster position
BODY = {
    "QB": ((72, 77), (200, 230)), "RB": ((68, 72), (188, 222)), "WR": ((70, 76), (172, 205)), "TE": ((75, 78), (232, 256)),
    "OL": ((75, 79), (292, 332)), "DL": ((74, 78), (255, 310)), "LB": ((72, 75), (218, 242)), "CB": ((70, 73), (178, 198)),
    "S": ((71, 74), (190, 210)), "DB": ((70, 74), (180, 205)), "PK": ((70, 74), (180, 205)), "P": ((72, 76), (190, 215)),
    "LS": ((72, 75), (220, 240)),
}

# The numbers each position wears (the college convention: linemen in the 50s to 70s, receivers in the
# teens and 80s, backs under 50, quarterbacks under 20).
JERSEYS = {
    "QB": (range(0, 20),), "RB": (range(0, 50),), "WR": (range(0, 20), range(80, 90), range(20, 50)), "TE": (range(80, 90), range(0, 50)),
    "OL": (range(50, 80),), "DL": (range(90, 100), range(50, 80), range(0, 50)), "LB": (range(0, 60), range(90, 100)),
    "CB": (range(0, 50),), "S": (range(0, 50),), "DB": (range(0, 50),), "PK": (range(0, 50), range(90, 100)),
    "P": (range(0, 50), range(90, 100)), "LS": (range(40, 70),),
}
DEFENSE = frozenset({"DL", "LB", "CB", "S", "DB"})  # a defender may share a number with an offensive player

# Public release Phase 7: an FBS roster by position, about 110 players like a real one (5 quarterbacks, 3
# kickers, 2 long snappers). Each class and each walk-on fills the positions a team is short of; once a team
# is at every target, positions are drawn in these proportions. DB counts as S.
ROSTER_TARGETS = {"QB": 5, "RB": 7, "WR": 14, "TE": 7, "OL": 18, "DL": 17, "LB": 11, "CB": 11, "S": 9, "PK": 3, "P": 3, "LS": 2}
SPECIALISTS = frozenset({"PK", "P", "LS"})
ROSTER_SIZE = 112  # classes and walk-ons stop short of this many
# The recruiting label a signee at a roster position is listed under: (label, chance), the rest the first label.
RECRUIT_LABELS = {
    "QB": (("QB", 1.0),), "RB": (("RB", 0.9), ("ATH", 0.1)), "WR": (("WR", 0.9), ("ATH", 0.1)), "TE": (("TE", 1.0),),
    "OL": (("IOL", 0.55), ("OT", 0.45)), "DL": (("DL", 0.7), ("EDGE", 0.3)), "LB": (("LB", 0.85), ("EDGE", 0.15)),
    "CB": (("CB", 0.88), ("ATH", 0.12)), "S": (("S", 0.92), ("ATH", 0.08)), "PK": (("K", 1.0),), "P": (("P", 1.0),), "LS": (("LS", 1.0),),
}
NUMBER_FIRST = ("QB", "PK", "P", "LS", "WR", "TE", "OL", "RB", "DL", "LB", "CB", "S", "DB")  # who picks first in a year

FCS_TEAMS = [
    ("Pebble Creek", "Pebbles"), ("Turnip Tech", "Roots"), ("Muskrat Falls", "Muskrats"), ("Gopher Gulch", "Gophers"),
    ("Biscuit College", "Crumbs"), ("Soda Springs", "Fizz"), ("Haystack", "Needles"), ("Corn Maze", "Wanderers"),
    ("Popcorn State", "Kernels"), ("Wishbone", "Wishes"), ("Mudpie", "Puddlers"), ("Lima Bean", "Beans"),
    ("Tin Can", "Clankers"), ("Clothesline", "Pins"), ("Rocking Chair", "Rockers"), ("Porch Light", "Moths"),
    ("Jelly Jar", "Jams"), ("Gumdrop", "Drops"), ("Scarecrow State", "Crows"), ("Weathervane", "Spinners"),
    ("Thimble", "Stitches"), ("Teapot Dome", "Kettles"), ("Sawdust", "Chips"), ("Bramble", "Thorns"),
]
FCS_CONFERENCES = ("Crumb Conference", "Saltine League", "Pantry Conference")


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


@dataclass
class Venue:
    id: int
    name: str
    city: str
    state: str
    zip: str
    timezone: str
    latitude: float
    longitude: float
    elevation: float
    capacity: int
    construction_year: int
    grass: bool
    dome: bool


@dataclass
class Coach:
    id: int
    first: str
    last: str
    hire_year: int
    hire_month: int
    history: dict[int, tuple[int, int]] = field(default_factory=dict)  # year -> (wins, losses) before the simulated seasons


@dataclass
class Team:
    id: int
    school: str
    mascot: str
    abbr: str
    conference: str
    conf_short: str
    classification: str
    color: str
    alt_color: str
    venue: Venue
    prestige: float
    twitter: str | None
    coach: Coach | None = None

    @property
    def is_fbs(self) -> bool:
        return self.classification == "fbs"


@dataclass(slots=True)
class Recruit:
    id: str
    year: int
    name: str
    first: str
    last: str
    position: str
    high_school: str
    height: float
    weight: int
    stars: int
    rating: float
    city: str
    state: str
    latitude: float
    longitude: float
    fips: str
    committed: int | None = None  # team id
    athlete: str | None = None  # player id once enrolled
    ranking: int = 0


@dataclass(slots=True)
class Stint:
    team: int
    start: int
    end: int  # exclusive: the first season not with this team
    jersey: int


@dataclass(slots=True)
class Player:
    id: str
    first: str
    last: str
    position: str
    height: int
    weight: int
    city: str
    state: str
    latitude: float
    longitude: float
    fips: str
    enroll: int
    leave: int  # exclusive
    base: float  # 0..1 from the recruiting rating
    growth: float
    noise: float
    stints: list[Stint] = field(default_factory=list)
    recruit: str | None = None  # recruit id

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def short(self) -> str:
        return f"{self.first[0]}.{self.last}"

    def ability(self, year: int) -> float:
        years_in = max(0, year - self.enroll)
        return max(0.05, min(1.0, 0.25 + 0.6 * self.base + self.growth * years_in + self.noise))

    def stint_in(self, year: int) -> Stint | None:
        for s in self.stints:
            if s.start <= year < s.end:
                return s
        return None


@dataclass(slots=True)
class Transfer:
    season: int
    player: str
    first: str
    last: str
    position: str
    origin: str  # school
    destination: str | None
    date: datetime
    rating: float | None
    stars: int | None
    eligibility: str


@dataclass(slots=True)
class GameSlot:
    """A scheduled game; results live in the season module."""

    id: int
    season: int
    week: int
    season_type: str  # regular, postseason
    start: datetime
    tbd: bool
    home: int
    away: int
    neutral: bool
    conference_game: bool
    venue: Venue
    notes: str | None = None
    playoff: dict | None = None
    outlet: str | None = None
    announce: datetime | None = None  # when the matchup becomes known (championships, bowls, playoff rounds)


def first_saturday(year: int) -> date:
    """Week 1's Saturday: Labor Day weekend, the first Saturday on or after August 30."""
    d = date(year, 8, 30)
    while d.weekday() != 5:
        d += timedelta(days=1)
    return d


def _at(day: date, hours: int, minutes: int = 0) -> datetime:
    return datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=hours, minutes=minutes)


def week_window(year: int, week: int, season_type: str = "regular") -> tuple[datetime, datetime]:
    """CFBD's calendar windows: week 1 takes in the Saturday before ("week 0"), later weeks run
    Monday to Monday, the postseason from the Monday after championship week to January 21."""
    sat1 = first_saturday(year)
    if season_type == "postseason":
        return _at(saturday(year, 15) + timedelta(days=2), 7), datetime(year + 1, 1, 21, 6, 59, tzinfo=timezone.utc)
    if week == 1:
        return _at(sat1 - timedelta(days=7), 7), _at(sat1 + timedelta(days=3), 6, 59)
    if week == 2:
        return _at(sat1 + timedelta(days=3), 7), _at(saturday(year, 2) + timedelta(days=2), 6, 59)
    sat = saturday(year, week)
    return _at(sat - timedelta(days=5), 7), _at(sat + timedelta(days=2), 6, 59)


def saturday(year: int, week: int) -> date:
    return first_saturday(year) + timedelta(days=7 * (week - 1))


class League:
    def __init__(self, seed: int = 2026, season: int = 2026) -> None:
        self.seed = seed
        self.season = season
        self.rng = random.Random(seed * 7919 + season)
        self.teams: list[Team] = []
        self.by_id: dict[int, Team] = {}
        self.by_school: dict[str, Team] = {}
        self.players: dict[str, Player] = {}
        self.recruits: dict[str, Recruit] = {}
        self.recruits_by_year: dict[int, list[Recruit]] = {}
        self.transfers: list[Transfer] = []
        self.schedules: dict[int, list[GameSlot]] = {}
        self.venues: list[Venue] = []
        self._used_ids: set[int] = set()
        self._used_player_ids: set[str] = set()
        self._jerseys: dict[int, list[tuple[int, int, int]]] = {}
        self._spans: dict[int, list[tuple[Stint, str]]] = {}  # each team's stints and positions, for its needs
        self._roster_hint: dict[str, str] = {}  # the roster position a signee was recruited for
        self._build_teams()
        self._build_people()
        self._build_fcs_rosters()
        self._number_by_position()
        self._sign_at_home()
        for year in (season - 1, season):
            self.schedules[year] = self._schedule(year)

    # -- ids -------------------------------------------------------------------------------
    def _new_id(self, low: int, high: int) -> int:
        while True:
            value = self.rng.randint(low, high)
            if value not in self._used_ids:
                self._used_ids.add(value)
                return value

    def _player_id(self) -> str:
        while True:
            value = str(self.rng.randint(4_000_000, 5_299_999))
            if value not in self._used_player_ids:
                self._used_player_ids.add(value)
                return value

    def _town(self) -> str:
        return self.rng.choice(N.TOWN_HEADS) + self.rng.choice(N.TOWN_TAILS)

    def _place(self, state: str, spread: float = 1.6) -> tuple[float, float]:
        lat, lon, _ = N.STATES[state]
        return round(lat + self.rng.uniform(-spread, spread), 7), round(lon + self.rng.uniform(-spread * 1.3, spread * 1.3), 7)

    # -- teams -----------------------------------------------------------------------------
    def _build_teams(self) -> None:
        rng = self.rng
        golden = 0.6180339887
        hue = rng.random()
        for conference, short, schools in N.CONFERENCES:
            power = conference in N.POWER_CONFERENCES
            for school, mascot, abbr in schools:
                hue = (hue + golden) % 1.0
                primary = _hex(colorsys.hls_to_rgb(hue, rng.uniform(0.28, 0.4), rng.uniform(0.55, 0.85)))
                roll = rng.random()
                if roll < 0.4:
                    alt = "#ffffff"
                elif roll < 0.7:
                    alt = _hex(colorsys.hls_to_rgb((hue + 0.5) % 1, 0.55, 0.85))
                else:
                    alt = _hex(colorsys.hls_to_rgb(0.12 + rng.uniform(-0.02, 0.03), 0.55, 0.9))
                prestige = rng.betavariate(5, 3) if power else rng.betavariate(2.2, 4.5)
                if school == N.OUR_SCHOOL:
                    primary, alt, prestige = "#00838f", "#f2b705", 0.82
                venue = self._venue(school, mascot, conference, power)
                team = Team(
                    id=self._new_id(2, 2999), school=school, mascot=mascot, abbr=abbr, conference=conference,
                    conf_short=short, classification="fbs", color=primary, alt_color=alt, venue=venue,
                    prestige=round(prestige, 4), twitter=f"@{abbr.title()}Football" if rng.random() < 0.85 else None,
                )
                self._add_team(team)
        for i, (school, mascot) in enumerate(FCS_TEAMS):
            hue = (hue + golden) % 1.0
            conference = FCS_CONFERENCES[i % len(FCS_CONFERENCES)]
            venue = self._venue(school, mascot, "FBS Independents", False, small=True)
            team = Team(
                id=self._new_id(3000, 3999), school=school, mascot=mascot, abbr=school.replace(" ", "")[:4].upper(),
                conference=conference, conf_short=conference.split()[0][:4].upper(), classification="fcs",
                color=_hex(colorsys.hls_to_rgb(hue, 0.35, 0.6)), alt_color="#ffffff", venue=venue,
                prestige=round(rng.uniform(0.0, 0.15), 4), twitter=None,
            )
            self._add_team(team)
        for team in self.teams:
            team.coach = self._coach(team)

    def _add_team(self, team: Team) -> None:
        self.teams.append(team)
        self.by_id[team.id] = team
        self.by_school[team.school] = team
        self.venues.append(team.venue)

    def _venue(self, school: str, mascot: str, conference: str, power: bool, small: bool = False) -> Venue:
        rng = self.rng
        state = rng.choice(N.CONFERENCE_STATES.get(conference, ["OH"]))
        lat, lon = self._place(state)
        form = rng.choice(N.STADIUM_FORMS)
        name = form.format(school=school, mascot=mascot, last=rng.choice(N.LAST_NAMES))
        capacity = rng.randint(55_000, 104_000) if power else rng.randint(9_000, 18_000) if small else rng.randint(20_000, 52_000)
        return Venue(
            id=self._new_id(3000, 9999), name=name, city=self._town(), state=state, zip=f"{rng.randint(10000, 99899):05d}",
            timezone=N.STATES[state][2], latitude=lat, longitude=lon, elevation=round(rng.uniform(2, 2200), 6),
            capacity=capacity, construction_year=rng.randint(1915, 2012), grass=rng.random() < 0.55, dome=rng.random() < 0.04,
        )

    def _coach(self, team: Team) -> Coach:
        rng = self.rng
        hire_year = self.season - min(int(rng.expovariate(1 / 4)), 14)
        coach = Coach(id=self._new_id(100, 2999), first=rng.choice(N.FIRST_NAMES), last=rng.choice(N.LAST_NAMES),
                      hire_year=hire_year, hire_month=rng.choice((11, 12, 1)))
        for year in range(hire_year, self.season - 1):
            wins = max(0, min(12, round(rng.gauss(4 + 6 * team.prestige, 2.2))))
            coach.history[year] = (wins, 12 - wins)
        return coach

    # -- people ----------------------------------------------------------------------------
    def _build_people(self) -> None:
        """Recruiting classes from eight years back to next year, enrolled players, walk-ons,
        departures and the transfer portal, year by year."""
        rng = self.rng
        fbs = [t for t in self.teams if t.is_fbs]
        first_class = self.season - 8
        for year in range(first_class, self.season + 2):
            year_recruits: list[Recruit] = []
            for team in fbs:
                count = rng.randint(20, 26) if team.conference in N.POWER_CONFERENCES else rng.randint(18, 24)
                have = self._counts(team.id, year)
                count = max(12, min(count, ROSTER_SIZE - 8 - sum(have.values())))  # a full roster signs a small class
                for _ in range(count):
                    roster_pos = self._need(have, specialists=0.35)
                    have[roster_pos] = have.get(roster_pos, 0) + 1
                    pos = self._label(roster_pos)
                    rating = self._rating(team.prestige)
                    recruit = self._recruit(year, pos, rating, team.conference, roster_pos)
                    recruit.committed = team.id if year <= self.season or rng.random() < 0.72 else None
                    year_recruits.append(recruit)
                    if year <= self.season and recruit.committed is not None:
                        self._enroll(recruit, team, year)
                if year <= self.season:
                    for _ in range(max(2, min(rng.randint(6, 9), ROSTER_SIZE - sum(have.values())))):
                        roster_pos = self._need(have, specialists=4.0)  # specialists mostly walk on
                        have[roster_pos] = have.get(roster_pos, 0) + 1
                        self._walk_on(team, year, roster_pos if roster_pos in SPECIALISTS else None, roster_pos)
            # unsigned and uncommitted prospects fill out the national list
            for _ in range(rng.randint(260, 320)):
                pos = rng.choices(list(RECRUIT_POSITIONS), weights=list(RECRUIT_POSITIONS.values()))[0]
                year_recruits.append(self._recruit(year, pos, self._rating(rng.uniform(0.0, 0.5)), None))
            year_recruits.sort(key=lambda r: (-r.rating, r.id))
            for rank, recruit in enumerate(year_recruits, start=1):
                recruit.ranking = rank
            self.recruits_by_year[year] = year_recruits
            if year <= self.season and year >= first_class + 1:
                self._portal(year)

    def _build_fcs_rosters(self) -> None:
        """FCS opponents need players for their side of a box score: small rosters, no recruiting."""
        for team in self.teams:
            if team.is_fbs:
                continue
            for year in range(self.season - 5, self.season + 1):
                for k in range(11):
                    special = ("PK", "P", "LS")[k] if k < 3 else None
                    pos = special or self.rng.choice(("QB", "RB", "WR", "WR", "TE", "OL", "OL", "DL", "DL", "LB", "CB", "S"))
                    self._walk_on(team, year, pos)
                    self.players[next(reversed(self.players))].base = self.rng.uniform(0.05, 0.35)

    def _counts(self, team_id: int, year: int) -> dict[str, int]:
        """How many players the team has at each roster position in `year` (DB counts as S)."""
        have: dict[str, int] = {}
        for stint, pos in self._spans.get(team_id, []):
            if stint.start <= year < stint.end:
                key = "S" if pos == "DB" else pos
                have[key] = have.get(key, 0) + 1
        return have

    def _need(self, have: dict[str, int], specialists: float) -> str:
        """A roster position to fill: the bigger the gap to its target, the likelier; at every target, in
        proportion. `specialists` scales the kickers', punters' and snappers' share."""
        positions = list(ROSTER_TARGETS)
        weights = []
        for pos in positions:
            target = ROSTER_TARGETS[pos]
            weight = max(target - have.get(pos, 0), 0) + 0.06 * target
            weights.append(weight * (specialists if pos in SPECIALISTS else 1.0))
        return self.rng.choices(positions, weights=weights)[0]

    def _label(self, roster_pos: str) -> str:
        """The recruiting position a signee for `roster_pos` is listed under."""
        options = RECRUIT_LABELS.get(roster_pos, ((roster_pos, 1.0),))
        roll = self.rng.random()
        for label, chance in options:
            if roll < chance:
                return label
            roll -= chance
        return options[0][0]

    def _rating(self, prestige: float) -> float:
        value = self.rng.gauss(0.80 + 0.085 * prestige, 0.035)
        return round(max(0.75, min(0.9999, value)), 4)

    @staticmethod
    def _stars(rating: float) -> int:
        return 2 if rating < 0.80 else 3 if rating < 0.89 else 4 if rating < 0.9834 else 5

    def _home(self, conference: str | None) -> tuple[str, str, float, float, str]:
        rng = self.rng
        if conference and rng.random() < 0.5:
            state = rng.choice(N.CONFERENCE_STATES.get(conference, ["TX"]))
        else:
            state = rng.choices(list(N.RECRUIT_STATE_WEIGHTS), weights=list(N.RECRUIT_STATE_WEIGHTS.values()))[0]
        lat, lon = self._place(state, 2.0)
        fips = STATE_FIPS.get(state, "48") + f"{rng.randint(1, 199) * 2 - 1:03d}"
        return self._town(), state, lat, lon, fips

    def _recruit(self, year: int, pos: str, rating: float, conference: str | None, roster_pos: str | None = None) -> Recruit:
        rng = self.rng
        first, last = rng.choice(N.FIRST_NAMES), rng.choice(N.LAST_NAMES)
        city, state, lat, lon, fips = self._home(conference)
        roster_pos = roster_pos or self._roster_position(pos)
        (h0, h1), (w0, w1) = BODY.get(roster_pos, BODY["WR"])
        while True:
            rid = str(rng.randint(100_000, 199_999))
            if rid not in self.recruits:
                break
        recruit = Recruit(
            id=rid, year=year, name=f"{first} {last}", first=first, last=last, position=pos,
            high_school=f"{city.split()[0]} {rng.choice(N.HIGH_SCHOOL_TAILS)}", height=float(rng.randint(h0, h1)),
            weight=rng.randint(w0, w1), stars=self._stars(rating), rating=rating, city=city, state=state,
            latitude=lat, longitude=lon, fips=fips,
        )
        self.recruits[rid] = recruit
        self._roster_hint[rid] = roster_pos
        return recruit

    def _roster_position(self, pos: str) -> str:
        rng = self.rng
        if pos in ("IOL", "OT"):
            return "OL"
        if pos == "EDGE":
            return "DL" if rng.random() < 0.6 else "LB"
        if pos == "ATH":
            return rng.choice(("WR", "CB", "S", "RB"))
        if pos == "K":
            return "PK"
        if pos == "S" and rng.random() < 0.15:
            return "DB"
        return pos

    def _jersey(self, team_id: int, start: int, end: int) -> int:
        """A first number free on the team for the player's years. The draws here are part of the league's
        stream, so the league stays as it was; _number_by_position gives the numbers worn."""
        taken = {n for (s, e, n) in self._jerseys.get(team_id, []) if s < end and start < e}
        free = [n for n in range(0, 100) if n not in taken]
        number = self.rng.choice(free) if free else self.rng.randint(0, 99)
        self._jerseys.setdefault(team_id, []).append((start, end, number))
        return number

    def _sign_at_home(self) -> None:
        """Bring a share of each school's signees from its own state, more where the state grows more
        players (a Texas school signs Texans; a Vermont school signs few Vermonters). A pass of its own
        after the build, on its own stream: hometowns never feed back into the league."""
        rng = random.Random(self.seed * 7883 + self.season)
        top = max(N.RECRUIT_STATE_WEIGHTS.values())
        for recruit in sorted(self.recruits.values(), key=lambda r: r.id):
            team = self.by_id.get(recruit.committed) if recruit.committed is not None else None
            state = team.venue.state if team is not None and team.is_fbs else None
            if state is None or state not in N.STATES or recruit.state == state:
                continue
            if rng.random() >= 0.08 + 0.5 * N.RECRUIT_STATE_WEIGHTS.get(state, 0) / top:
                continue
            lat, lon, _ = N.STATES[state]
            city = rng.choice(N.TOWN_HEADS) + rng.choice(N.TOWN_TAILS)
            recruit.city, recruit.state = city, state
            recruit.latitude = round(lat + rng.uniform(-2.0, 2.0), 7)
            recruit.longitude = round(lon + rng.uniform(-2.6, 2.6), 7)
            recruit.fips = STATE_FIPS.get(state, "48") + f"{rng.randint(1, 199) * 2 - 1:03d}"
            recruit.high_school = f"{city.split()[0]} {rng.choice(N.HIGH_SCHOOL_TAILS)}"
            player = self.players.get(recruit.athlete) if recruit.athlete else None
            if player is not None:
                player.city, player.state, player.latitude, player.longitude, player.fips = city, state, recruit.latitude, recruit.longitude, recruit.fips

    def _number_by_position(self) -> None:
        """Renumber every stint by its position's range (JERSEYS), from a stream of its own. Two players on
        a team in the same season share a number only when one plays defense and the other doesn't (as
        college teams do), or when the team has run out of numbers."""
        rng = random.Random(self.seed * 7907 + self.season)
        worn: dict[tuple[int, bool], list[Stint]] = {}
        stints = [(stint, player.position) for player in self.players.values() for stint in player.stints]
        first = {position: i for i, position in enumerate(NUMBER_FIRST)}
        stints.sort(key=lambda item: (item[0].start, item[0].team, first.get(item[1], len(first)), item[0].jersey))
        for stint, position in stints:
            unit = (stint.team, position in DEFENSE)
            taken = {s.jersey for s in worn.get(unit, []) if s.start < stint.end and stint.start < s.end}
            number = None
            for band in JERSEYS.get(position, ()):
                fits = [n for n in band if n not in taken]
                if fits:
                    number = rng.choice(fits)
                    break
            if number is None:
                free = [n for n in range(0, 100) if n not in taken]
                number = rng.choice(free) if free else rng.randint(0, 99)
            stint.jersey = number
            worn.setdefault(unit, []).append(stint)

    def _stay(self, base: float) -> int:
        roll = self.rng.random()
        if roll < 0.04 + 0.08 * base:
            return 3
        if roll < 0.75:
            return 4
        return 5

    def _enroll(self, recruit: Recruit, team: Team, year: int) -> None:
        rng = self.rng
        base = (recruit.rating - 0.75) / 0.25
        pos = self._roster_hint.get(recruit.id) or self._roster_position(recruit.position)
        if pos == "S" and rng.random() < 0.15:
            pos = "DB"  # CFBD lists some safeties as DB
        (h0, h1), (w0, w1) = BODY.get(pos, BODY["WR"])
        player = Player(
            id=self._player_id(), first=recruit.first, last=recruit.last, position=pos, height=int(recruit.height),
            weight=rng.randint(w0, w1), city=recruit.city, state=recruit.state, latitude=recruit.latitude,
            longitude=recruit.longitude, fips=recruit.fips, enroll=year, leave=year + self._stay(base), base=base,
            growth=rng.uniform(0.03, 0.09), noise=rng.gauss(0, 0.07), recruit=recruit.id,
        )
        self._join(player, Stint(team.id, year, player.leave, self._jersey(team.id, year, player.leave)))
        recruit.athlete = player.id
        self.players[player.id] = player

    def _join(self, player: Player, stint: Stint) -> None:
        player.stints.append(stint)
        self._spans.setdefault(stint.team, []).append((stint, player.position))

    def _walk_on(self, team: Team, year: int, special: str | None, position: str | None = None) -> None:
        rng = self.rng
        pos = special or position or rng.choice(("WR", "DB", "LB", "OL", "RB", "TE", "DL", "S", "QB"))
        (h0, h1), (w0, w1) = BODY.get(pos, BODY["WR"])
        city, state, lat, lon, fips = self._home(team.conference)
        player = Player(
            id=self._player_id(), first=rng.choice(N.FIRST_NAMES), last=rng.choice(N.LAST_NAMES), position=pos,
            height=rng.randint(h0, h1), weight=rng.randint(w0, w1), city=city, state=state, latitude=lat, longitude=lon,
            fips=fips, enroll=year, leave=year + rng.choice((2, 3, 4, 4, 5)),
            base=0.12 if not special else rng.uniform(0.3, 0.8), growth=rng.uniform(0.02, 0.06), noise=rng.gauss(0, 0.05),
        )
        self._join(player, Stint(team.id, year, player.leave, self._jersey(team.id, year, player.leave)))
        self.players[player.id] = player

    def _portal(self, year: int) -> None:
        """Before season `year`: some players with eligibility left enter the portal."""
        rng = self.rng
        fbs = [t for t in self.teams if t.is_fbs]
        fcs = [t for t in self.teams if not t.is_fbs]
        weights = [0.3 + t.prestige for t in fbs]
        for player in list(self.players.values()):
            stint = player.stint_in(year - 1)
            if stint is None or player.leave <= year or stint.end != player.leave:
                continue
            ability = player.ability(year - 1)
            if rng.random() >= 0.13 + 0.16 * (1 - ability) * (1 if player.enroll < year - 1 else 0.5):
                continue
            origin = self.by_id[stint.team]
            when = datetime(year - 1, 12, rng.randint(1, 31), rng.randint(12, 23), rng.randint(0, 59), tzinfo=timezone.utc) if rng.random() < 0.7 \
                else datetime(year, 4, rng.randint(10, 30), rng.randint(12, 23), rng.randint(0, 59), tzinfo=timezone.utc)
            rating = round(min(0.97, max(0.78, 0.78 + 0.2 * ability + rng.gauss(0, 0.02))), 2)
            roll = rng.random()
            eligibility = "Immediate"
            destination: Team | None = None
            if roll < 0.03:
                eligibility = "Withdrawn"
            elif roll < 0.8:
                destination = rng.choices(fbs, weights=weights)[0]
                if destination.id == origin.id:
                    destination = rng.choice(fbs)
                if rng.random() < 0.08:
                    destination = rng.choice(fcs)
            if eligibility != "Withdrawn":
                stint.end = year
                if destination is not None:
                    if destination.id == origin.id:
                        stint.end = player.leave
                    else:
                        self._join(player, Stint(destination.id, year, player.leave, self._jersey(destination.id, year, player.leave)))
                else:
                    player.leave = year
            self.transfers.append(Transfer(
                season=year, player=player.id, first=player.first, last=player.last,
                position=player.position if player.position not in ("CB", "S") else "DB" if rng.random() < 0.3 else player.position,
                origin=origin.school, destination=destination.school if destination else None, date=when,
                rating=rating if rng.random() < 0.85 else None, stars=self._stars(rating) if rng.random() < 0.85 else None,
                eligibility=eligibility if rng.random() > 0.004 else "TBD",
            ))

    # -- lookups ---------------------------------------------------------------------------
    def roster(self, team_id: int, year: int) -> list[Player]:
        index = self.__dict__.setdefault("_roster_index", {})
        if year not in index:
            by_team: dict[int, list[Player]] = {}
            for p in self.players.values():
                s = p.stint_in(year)
                if s is not None:
                    by_team.setdefault(s.team, []).append(p)
            for players in by_team.values():
                players.sort(key=lambda p: (p.position, p.last, p.first, p.id))
            index[year] = by_team
        return list(index[year].get(team_id, []))

    def team(self, key: int | str | None) -> Team | None:
        if isinstance(key, int):
            return self.by_id.get(key)
        if isinstance(key, str):
            return self.by_school.get(key) or self.by_school.get(key.strip())
        return None

    @property
    def fbs(self) -> list[Team]:
        return [t for t in self.teams if t.is_fbs]

    # -- schedules -------------------------------------------------------------------------
    def _schedule(self, year: int) -> list[GameSlot]:
        """Weeks 1 to 14: each FBS team plays 12. Conference games run as round-robin rounds in
        weeks 5 to 14; non-conference games fill each team's open weeks, against FBS teams
        from other conferences when a partner is free, otherwise an FCS team."""
        rng = random.Random(self.seed * 31 + year)
        fbs = self.fbs
        fcs = [t for t in self.teams if not t.is_fbs]
        busy: dict[int, set[int]] = {t.id: set() for t in fbs}
        pairs: list[tuple[int, int, int, bool]] = []  # week, home, away, conference game
        conf_games: dict[int, int] = {}
        by_conf: dict[str, list[Team]] = {}
        for t in fbs:
            by_conf.setdefault(t.conference, []).append(t)
        for conference, members in by_conf.items():
            if conference == "FBS Independents":
                for t in members:
                    conf_games[t.id] = 0
                continue
            order = members[:]
            rng.shuffle(order)
            n = len(order)
            rounds_needed = 9 if n >= 16 else 8
            weeks = list(range(5, 15))
            rng.shuffle(weeks)
            weeks = sorted(weeks[:rounds_needed])
            # circle method
            ring = order[1:]
            for r in range(rounds_needed):
                week = weeks[r]
                current = [order[0]] + ring
                for i in range(n // 2):
                    a, b = current[i], current[n - 1 - i]
                    home, away = (a, b) if (r + i) % 2 == 0 else (b, a)
                    pairs.append((week, home.id, away.id, True))
                    busy[a.id].add(week)
                    busy[b.id].add(week)
                ring = ring[-1:] + ring[:-1]
            for t in members:
                conf_games[t.id] = rounds_needed
        need = {t.id: 12 - conf_games[t.id] for t in fbs}
        played: set[frozenset[int]] = set()
        conf_of = {t.id: t.conference for t in fbs}
        fcs_games: list[tuple[int, int, int]] = []
        for week in range(1, 15):
            open_teams = [t.id for t in fbs if week not in busy[t.id] and need[t.id] > 0]
            rng.shuffle(open_teams)
            weeks_left = {tid: sum(1 for w in range(week, 15) if w not in busy[tid]) for tid in open_teams}
            # teams that can skip this week (more open weeks than games needed) may take a bye
            want = [tid for tid in open_teams if need[tid] >= weeks_left[tid] or rng.random() < need[tid] / max(1, weeks_left[tid]) + 0.15]
            unpaired = want[:]
            matched: set[int] = set()
            for i, a in enumerate(unpaired):
                if a in matched:
                    continue
                for b in unpaired[i + 1:]:
                    if b in matched or conf_of[a] == conf_of[b] and conf_of[a] != "FBS Independents":
                        continue
                    if frozenset((a, b)) in played:
                        continue
                    matched.update((a, b))
                    played.add(frozenset((a, b)))
                    home, away = (a, b) if rng.random() < 0.5 else (b, a)
                    pairs.append((week, home, away, False))
                    break
            for tid in want:
                if tid in matched:
                    busy[tid].add(week)
                    need[tid] -= 1
                elif need[tid] >= weeks_left[tid] or (week <= 4 and rng.random() < 0.35):
                    opponent = rng.choice(fcs)
                    fcs_games.append((week, tid, opponent.id))
                    busy[tid].add(week)
                    need[tid] -= 1
        for week, home, away in fcs_games:
            pairs.append((week, home, away, False))
        pairs.sort(key=lambda p: (p[0], p[1]))
        ours = self.by_school[N.OUR_SCHOOL].id
        slots: list[GameSlot] = []
        base = 500_000_000 + (year % 100) * 1_000_000
        counter = 0
        for week, home, away, conf in pairs:
            counter += rng.randint(3, 9)
            ht = self.by_id[home]
            neutral = not conf and week == 1 and rng.random() < 0.06
            start = self._kickoff(rng, year, week)
            if ours in (home, away):
                # The demo team keeps a steady TV window: 3:30 ET at home, 7 ET on the road (Saturdays).
                start = datetime.combine(saturday(year, week), datetime.min.time(), timezone.utc) + (timedelta(hours=19, minutes=30) if home == ours else timedelta(hours=23))
                neutral = False
            slots.append(GameSlot(
                id=base + counter, season=year, week=week, season_type="regular", start=start, tbd=False, home=home,
                away=away, neutral=neutral, conference_game=conf, venue=ht.venue if not neutral else self.rng.choice(self.venues[:20]),
                outlet=self._outlet(rng, ht),
            ))
        return slots

    def _kickoff(self, rng: random.Random, year: int, week: int) -> datetime:
        sat = saturday(year, week)
        roll = rng.random()
        if roll < 0.05:
            day = sat - timedelta(days=2)  # Thursday
        elif roll < 0.1:
            day = sat - timedelta(days=1)  # Friday
        else:
            day = sat
        hour, minute = rng.choice(((16, 0), (16, 0), (19, 30), (19, 30), (20, 0), (23, 0), (23, 30), (24, 0), (26, 30)))
        return datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=hour, minutes=minute)

    def _outlet(self, rng: random.Random, home: Team) -> str:
        if home.conference in N.POWER_CONFERENCES:
            return rng.choice(N.NETWORKS[:6])
        return rng.choice(N.NETWORKS)

    def next_game_id(self, year: int) -> int:
        base = 500_000_000 + (year % 100) * 1_000_000 + 900_000
        while base in self._used_ids:
            base += 1
        self._used_ids.add(base)
        return base


def as_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def round_half(x: float) -> float:
    return math.floor(x * 2 + 0.5) / 2
