"""Phase 10 stat helpers shared by the player, program, roster and ratings answers: the blue-chip
ratio from recruiting classes, player PPA per play and usage shares, team talent, returning
production, and the all-team ratings table. Every helper guards nulls and wrong types and drops
what it cannot read; nothing here raises on a bad record."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.cfbd.models import PlayerGamePpa, PlayerSeasonPpa, PlayerUsage, Recruit, ReturningProduction, TeamElo, TeamFPI, TeamSP, TeamTalent
from app.services.profiles import rank_teams, ranked_list

PPA_KEYS = ("all", "pass", "rush", "firstDown", "secondDown", "thirdDown", "standardDowns", "passingDowns")
USAGE_KEYS = ("overall", "pass", "rush", "firstDown", "secondDown", "thirdDown", "standardDowns", "passingDowns")
BLUE_CHIP_STARS = 4
BLUE_CHIP_CLASSES = 4
# Below this average (either sign) total / average stops being a reliable play count: CFBD rounds the
# average to three places, so a tiny divisor turns the rounding into whole plays of error.
PPA_PLAYS_MIN_AVERAGE = 0.01


def num(value: Any) -> float | None:
    """A finite number, else None. The JSON reader accepts NaN and Infinity, and neither survives
    arithmetic, rounding or the JSON answer to the browser."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _pick(block: Any, keys: tuple[str, ...]) -> dict[str, float | None]:
    source = block if isinstance(block, dict) else {}
    return {key: num(source.get(key)) for key in keys}


# --- recruiting -------------------------------------------------------------------------------------


def blue_chip(classes: dict[int, list[Recruit]]) -> dict[str, Any]:
    """Bud Elliott's blue-chip ratio: four- and five-star signees over all signees in the last four
    classes. Each class is reported too. `ratio` is None when no class has a signee."""
    per_class = []
    blue = signees = 0
    for year in sorted(classes)[-BLUE_CHIP_CLASSES:]:
        records = [r for r in classes.get(year, []) if isinstance(r, Recruit)]
        stars = [r.stars for r in records if isinstance(r.stars, int) and not isinstance(r.stars, bool)]
        class_blue = sum(1 for s in stars if s >= BLUE_CHIP_STARS)
        per_class.append({"year": year, "signees": len(records), "rated": len(stars), "blueChips": class_blue, "ratio": round(class_blue / len(records), 3) if records else None})
        blue += class_blue
        signees += len(records)
    return {"ratio": round(blue / signees, 3) if signees else None, "blueChips": blue, "signees": signees, "classes": per_class, "threshold": 0.5}


def star_counts(classes: dict[int, list[Recruit]]) -> dict[str, Any]:
    """Phase 17 #36: the signees of the same last four classes as the blue-chip ratio, counted by stars (5 to 1),
    with the average of the rated ones. A signee with no star rating counts in `unrated`."""
    counts = {str(n): 0 for n in range(5, 0, -1)}
    rated: list[int] = []
    unrated = 0
    for year in sorted(classes)[-BLUE_CHIP_CLASSES:]:
        for r in classes.get(year, []):
            if not isinstance(r, Recruit):
                continue
            stars = r.stars if isinstance(r.stars, int) and not isinstance(r.stars, bool) else None
            if stars is None or not 1 <= stars <= 5:
                unrated += 1
                continue
            counts[str(stars)] += 1
            rated.append(stars)
    return {"counts": counts, "average": round(sum(rated) / len(rated), 2) if rated else None, "rated": len(rated), "unrated": unrated}


# Phase 17 #24: recruiting by side of the ball, from the position each signee was recruited at (247's codes as
# CFBD sends them). ATH (an athlete with no position yet) and the specialists are counted apart.
OFFENSE_POSITIONS = frozenset({"QB", "PRO", "DUAL", "RB", "APB", "FB", "WR", "TE", "OT", "IOL", "OL", "OG", "C"})
DEFENSE_POSITIONS = frozenset({"DL", "DT", "SDE", "WDE", "DE", "EDGE", "LB", "ILB", "OLB", "CB", "S", "SAF", "DB"})
SPECIALIST_POSITIONS = frozenset({"K", "P", "LS"})


def side_of(position: Any) -> str | None:
    """"offense", "defense", "specialist", "athlete" (ATH), or None for a position the app doesn't know."""
    code = position.strip().upper() if isinstance(position, str) else ""
    if code in OFFENSE_POSITIONS:
        return "offense"
    if code in DEFENSE_POSITIONS:
        return "defense"
    if code in SPECIALIST_POSITIONS:
        return "specialist"
    if code == "ATH":
        return "athlete"
    return None


def recruit_sides(classes: dict[int, list[Recruit]]) -> dict[str, Any]:
    """Phase 17 #24: the last four classes (the blue-chip window) split into offense and defense: star counts,
    average stars, blue-chip ratio and average rating for each side, with the athletes, specialists and
    unknown positions counted apart."""
    by_side: dict[str, list[Recruit]] = {"offense": [], "defense": []}
    apart = {"athlete": 0, "specialist": 0, "unknown": 0}
    for year in sorted(classes)[-BLUE_CHIP_CLASSES:]:
        for r in classes.get(year, []):
            if not isinstance(r, Recruit):
                continue
            side = side_of(r.position)
            if side in by_side:
                by_side[side].append(r)
            else:
                apart[side or "unknown"] += 1
    out: dict[str, Any] = {}
    for side, signees in by_side.items():
        counts = star_counts({0: signees})
        stars = [r.stars for r in signees if isinstance(r.stars, int) and not isinstance(r.stars, bool) and 1 <= r.stars <= 5]
        ratings = [x for x in (num(r.rating) for r in signees) if x is not None and 0 < x <= 1]
        out[side] = {
            **counts,
            "signees": len(signees),
            "blueChipRatio": round(sum(1 for s in stars if s >= BLUE_CHIP_STARS) / len(signees), 3) if signees else None,
            "averageRating": round(sum(ratings) / len(ratings), 4) if ratings else None,
        }
    out["apart"] = apart
    return out


def recruit_block(recruit: Recruit | None) -> dict[str, Any] | None:
    if recruit is None:
        return None
    return {
        "year": recruit.year,
        "stars": recruit.stars if isinstance(recruit.stars, int) else None,
        "rating": num(recruit.rating),
        "nationalRank": recruit.ranking if isinstance(recruit.ranking, int) else None,
        "position": recruit.position,
        "type": recruit.recruit_type,
        "highSchool": recruit.school,
        "hometown": ", ".join(part for part in (recruit.city, recruit.state_province) if part) or None,
        "committedTo": recruit.committed_to,
    }


# --- players ---------------------------------------------------------------------------------------------


def ppa_plays(record: PlayerSeasonPpa) -> int | None:
    """Plays behind one season PPA line. The season answer never sends countablePlays (spec 5.30.0,
    verified 2026-09-23), but total over average gives the count back: a quarterback's 52.566 / 0.649
    is 81. Falls back to countablePlays should CFBD start sending it, else None. A count under one
    (the two figures disagree in sign, or the total is zero) is not a count."""
    total = num(record.total_ppa.get("all")) if isinstance(record.total_ppa, dict) else None
    average = num(record.average_ppa.get("all")) if isinstance(record.average_ppa, dict) else None
    if total is not None and average is not None and abs(average) >= PPA_PLAYS_MIN_AVERAGE:
        quotient = total / average
        if math.isfinite(quotient):  # a huge total over a small average overflows to inf
            plays = round(quotient)
            if plays >= 1:
                return plays
    countable = record.countable_plays
    if isinstance(countable, int) and not isinstance(countable, bool) and countable >= 0:
        return countable
    return None


def ppa_season_rows(records: list[PlayerSeasonPpa], team: str | None = None, min_plays: int = 0) -> list[dict[str, Any]]:
    """One row per player, best average first. min_plays drops a player whose play count is known
    and under it; a row whose count cannot be derived stays, since nothing says it is small."""
    rows: list[dict[str, Any]] = []
    for r in records:
        if team and r.team != team:
            continue
        plays = ppa_plays(r)
        if min_plays and plays is not None and plays < min_plays:
            continue
        average = _pick(r.average_ppa, PPA_KEYS)
        total = _pick(r.total_ppa, PPA_KEYS)
        rows.append({"playerId": r.id, "name": r.name, "position": r.position, "team": r.team, "plays": plays, "average": average, "total": total, "all": average["all"], "pass": average["pass"], "rush": average["rush"], "totalAll": total["all"]})
    rows.sort(key=lambda p: (p["all"] is None, -(p["all"] or 0.0)))
    return rows


def usage_rows(records: list[PlayerUsage], team: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in records:
        if team and r.team != team:
            continue
        shares = _pick(r.usage, USAGE_KEYS)
        rows.append({"playerId": r.id, "name": r.name, "position": r.position, "team": r.team, **shares})
    rows.sort(key=lambda p: (p["overall"] is None, -(p["overall"] or 0.0)))
    return rows


def ppa_game_rows(by_week: dict[int, list[PlayerGamePpa]] | list[tuple[int | None, list[PlayerGamePpa]]], player_id: str) -> list[dict[str, Any]]:
    """One row per graded game for a player, week order. Phase 15: also takes [(week, records)] already
    in game order, so a bowl (postseason "week 1") follows the regular season."""
    rows: list[dict[str, Any]] = []
    ordered = list(by_week) if isinstance(by_week, list) else [(week, by_week[week]) for week in sorted(by_week)]
    for week, records in ordered:
        for r in records:
            if r.id != player_id:
                continue
            avg = r.average_ppa
            rows.append({"week": week, "opponent": r.opponent, "all": num(avg.all) if avg else None, "pass": num(avg.pass_) if avg else None, "rush": num(avg.rush) if avg else None})
    return rows


# --- teams -------------------------------------------------------------------------------------------------


def rank_desc(values: dict[str, float]) -> dict[str, int]:
    """Higher is better, ties sharing a rank: the Season page's rule (profiles.rank_teams), so a team
    reads the same Elo, FPI or talent rank on the Ratings page as everywhere else."""
    ranks, _ = rank_teams(values, True)
    return ranks


# --- the rating tables (Phase 16): one source for every rating chip and its national list ----------

# CFBD's SP+ answer carries a "nationalAverages" row that validates as a team (verified against the
# 2026 recording). It is never a team: it showed as #70 on the Ratings page and made SP+ "of 139".
PSEUDO_TEAMS = frozenset({"nationalAverages"})


def real_teams(records: list[Any], fbs: set[str] | None) -> list[Any]:
    """Rows of real teams: never a pseudo-team, and only /teams/fbs schools when that list loaded."""
    return [r for r in records if isinstance(getattr(r, "team", None), str) and r.team and r.team not in PSEUDO_TEAMS and (fbs is None or r.team in fbs)]


def _cfbd_rank(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


@dataclass
class RankTable:
    """One rating across its population: each team's value and rank. `source` is "cfbd" when CFBD's
    own ranking is used (SP+, FPI, SRS), "local" when the tie rule ranks the values here."""

    values: dict[str, float | None]
    ranks: dict[str, int]
    higher: bool
    source: str
    conference: dict[str, str] = field(default_factory=dict)

    @property
    def of(self) -> int:
        return len(self.ranks)

    def rank(self, team: str | None) -> int | None:
        return self.ranks.get(team or "")

    def value(self, team: str | None) -> float | None:
        return self.values.get(team or "")

    def listing(self) -> list[tuple[str, float | None, int, bool]]:
        """[(team, value, rank, tied)] in rank then name order."""
        return ranked_list({t: v for t, v in self.values.items() if t in self.ranks}, self.higher, self.ranks)  # type: ignore[arg-type]


def rank_table(values: dict[str, float | None], higher: bool, cfbd: dict[str, int] | None = None, conference: dict[str, str] | None = None) -> RankTable:
    """CFBD's ranking when it ranked anyone in the population (only those teams are ranked), else the
    tie rule over the values here."""
    cfbd = {t: r for t, r in (cfbd or {}).items() if t in values}
    if cfbd:
        return RankTable(values, cfbd, higher, "cfbd", conference or {})
    numeric = {t: v for t, v in values.items() if v is not None}
    ranks, _ = rank_teams(numeric, higher)
    return RankTable(values, ranks, higher, "local", conference or {})


def sp_tables(sp: list[TeamSP], fbs: set[str] | None) -> dict[str, RankTable]:
    """SP+ overall, offense, defense (lower is better: points allowed) and special teams."""
    rows = real_teams(sp, fbs)
    conf = {r.team: r.conference for r in rows if isinstance(r.conference, str) and r.conference}

    def unit(read_value: Any, read_rank: Any, higher: bool) -> RankTable:
        values: dict[str, float | None] = {}
        ranks: dict[str, int] = {}
        for r in rows:
            value = num(read_value(r))
            if value is None:
                continue
            values[r.team] = value
            if (rank := _cfbd_rank(read_rank(r))) is not None:
                ranks[r.team] = rank
        return rank_table(values, higher, ranks, conf)

    return {
        "sp": unit(lambda r: r.rating, lambda r: r.ranking, True),
        "spOffense": unit(lambda r: r.offense.rating if r.offense else None, lambda r: r.offense.ranking if r.offense else None, True),
        "spDefense": unit(lambda r: r.defense.rating if r.defense else None, lambda r: r.defense.ranking if r.defense else None, False),
        "spSpecial": unit(lambda r: r.special_teams.rating if r.special_teams else None, lambda r: r.special_teams.ranking if r.special_teams else None, True),
    }


def elo_table(elo: list[TeamElo], fbs: set[str] | None) -> RankTable:
    rows = real_teams(elo, fbs)
    return rank_table({r.team: v for r in rows if (v := num(r.elo)) is not None}, True, None, {r.team: r.conference for r in rows if r.conference})


def fpi_tables(fpi: list[TeamFPI], fbs: set[str] | None) -> dict[str, RankTable]:
    """FPI (CFBD's rank, else the tie rule) and its résumé ranks: strength of schedule and of record
    are CFBD's ranks only, with no value behind them."""
    rows = real_teams(fpi, fbs)
    conf = {r.team: r.conference for r in rows if r.conference}
    values = {r.team: v for r in rows if (v := num(r.fpi)) is not None}
    resume = {r.team: r.resume_ranks for r in rows if r.resume_ranks is not None}
    fpi_ranks = {t: rank for t, block in resume.items() if t in values and (rank := _cfbd_rank(block.fpi)) is not None}

    def ranks_only(read: Any) -> RankTable:
        ranks = {t: rank for t, block in resume.items() if (rank := _cfbd_rank(read(block))) is not None}
        return RankTable({t: None for t in ranks}, ranks, False, "cfbd", conf)

    return {
        "fpi": rank_table(values, True, fpi_ranks, conf),
        "fpiSos": ranks_only(lambda b: b.strength_of_schedule),
        "fpiSor": ranks_only(lambda b: b.strength_of_record),
    }


def talent_table(talent: list[TeamTalent], fbs: set[str] | None) -> RankTable:
    rows = real_teams(talent, fbs)
    return rank_table({r.team: v for r in rows if (v := num(r.talent)) is not None}, True)


def talent_lookup(records: list[TeamTalent], fbs: set[str] | None = None) -> dict[str, dict[str, Any]]:
    table = talent_table(records, fbs)
    return {team: {"talent": round(value, 2), "rank": table.ranks[team], "of": table.of, "metric": "rating:talent"} for team, value in table.values.items() if team in table.ranks and value is not None}


def returning_block(records: list[ReturningProduction], team: str) -> dict[str, Any] | None:
    r = next((x for x in records if x.team == team), None)
    if r is None:
        return None
    return {
        "percentPPA": num(r.percent_ppa),
        "percentPassing": num(r.percent_passing_ppa),
        "percentReceiving": num(r.percent_receiving_ppa),
        "percentRushing": num(r.percent_rushing_ppa),
        "usage": num(r.usage),
        "passingUsage": num(r.passing_usage),
        "receivingUsage": num(r.receiving_usage),
        "rushingUsage": num(r.rushing_usage),
        "totalPPA": num(r.total_ppa),
    }


def ratings_rows(sp: list[TeamSP], elo: list[TeamElo], fpi: list[TeamFPI], talent: list[TeamTalent], conferences: dict[str, str] | None = None, fbs: set[str] | None = None) -> list[dict[str, Any]]:
    """Every FBS team with an SP+ rating, with Elo, FPI and talent beside it and a rank for each.
    Phase 16: every rank comes from the rating tables the chips and the national lists read, and the
    nationalAverages pseudo-team is gone (it was #70 on this page)."""
    sps, e, f, t = sp_tables(sp, fbs), elo_table(elo, fbs), fpi_tables(fpi, fbs), talent_table(talent, fbs)
    rows = []
    for r in real_teams(sp, fbs):
        team = r.team
        if num(r.rating) is None:
            continue

        def unit(key: str, team: str = team) -> dict[str, Any]:
            return {"rating": sps[key].value(team), "rank": sps[key].rank(team)}

        talent_value = t.value(team)
        rows.append(
            {
                "team": team,
                "conference": r.conference or (conferences or {}).get(team),
                "sp": {"rating": num(r.rating), "rank": sps["sp"].rank(team), "sos": num(r.sos), "secondOrderWins": num(r.second_order_wins)},
                "spOffense": unit("spOffense"),
                "spDefense": unit("spDefense"),
                "spSpecial": unit("spSpecial"),
                "elo": {"rating": e.value(team), "rank": e.rank(team)},
                "fpi": {"rating": f["fpi"].value(team), "rank": f["fpi"].rank(team), "strengthOfSchedule": f["fpiSos"].rank(team), "strengthOfRecord": f["fpiSor"].rank(team)},
                "talent": {"talent": round(talent_value, 2) if talent_value is not None else None, "rank": t.rank(team), "of": t.of},
            }
        )
    rows.sort(key=lambda row: (row["sp"]["rank"] is None, row["sp"]["rank"] or 0, row["team"]))
    return rows
