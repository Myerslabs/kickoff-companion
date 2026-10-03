"""Pydantic models for CFBD payloads, one per endpoint the app uses.

Tolerance rules (docs/CLAUDE.md, defensive coding):
- Unknown fields are ignored. Everything except an identity field is optional with a safe
  default, so one odd value never kills a record.
- Lists are parsed record by record with parse_records(): a bad record is skipped, counted,
  and reported once per response. Nested lists (a game's teams, a poll's ranks) drop bad
  items the same way instead of failing the parent.
- Shapes come from the live OpenAPI spec (v5.27.1) and the recorded samples in
  tests/fixtures/cfbd/. Never from memory.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, WrapValidator, field_validator
from pydantic.alias_generators import to_camel

from app.cache import DataKind

log = logging.getLogger("kickoff.models")

Number = int | float
Scalar = int | float | str | bool

_dropped: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar("cfbd_dropped", default=None)


def _summarise(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    return f"{loc or 'record'}: {first.get('msg', 'invalid')}"


def _drop_bad_items(value: Any, handler: Any, info: Any) -> list[Any]:
    """Validate a list item by item; bad items are dropped and noted, never fatal."""
    if value is None:
        return []
    if not isinstance(value, list):
        return handler(value)
    field = getattr(info, "field_name", None) or "list"
    good: list[Any] = []
    for index, item in enumerate(value):
        try:
            good.extend(handler([item]))
        except ValidationError as exc:
            notes = _dropped.get()
            if notes is not None:
                first = exc.errors()[0] if exc.errors() else {}
                inner = ".".join(str(part) for part in list(first.get("loc", ()))[1:])
                notes.append(f"{field}[{index}]{'.' + inner if inner else ''}: {first.get('msg', 'invalid')}")
    return good


DropBad = WrapValidator(_drop_bad_items)


def _none_if_bad(value: Any, handler: Any, info: Any) -> Any:
    """An optional nested object that fails validation becomes None and is noted (Phase 15), so one
    odd bracket block never drops the game it belongs to."""
    try:
        return handler(value)
    except ValidationError as exc:
        notes = _dropped.get()
        if notes is not None:
            notes.append(f"{getattr(info, 'field_name', None) or 'field'}: {_summarise(exc)} (read as empty)")
        return None


NoneIfBad = WrapValidator(_none_if_bad)


class CfbdModel(BaseModel):
    model_config = ConfigDict(extra="ignore", alias_generator=to_camel, populate_by_name=True)


class LenientModel(CfbdModel):
    """A record where one optional field of the wrong type becomes its default (null) and is noted,
    instead of failing the whole record (Phase 11). For the live feed, where one odd value used to
    drop a whole drive with every play in it. Required fields (the ids) still fail the record."""

    @field_validator("*", mode="wrap")
    @classmethod
    def _lenient_field(cls, value: Any, handler: Any, info: Any) -> Any:
        try:
            return handler(value)
        except ValidationError as exc:
            name = getattr(info, "field_name", None)
            spec = cls.model_fields.get(name) if name else None
            if spec is None or spec.is_required():
                raise
            notes = _dropped.get()
            if notes is not None:
                first = exc.errors()[0] if exc.errors() else {}
                notes.append(f"{cls.__name__}.{name}: {first.get('msg', 'invalid')} (read as empty)")
            return spec.get_default(call_default_factory=True)


# --- parsing ------------------------------------------------------------------------------

T = TypeVar("T", bound=CfbdModel)


@dataclass
class ParseResult(Generic[T]):
    records: list[T]
    total: int
    skipped: int
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.skipped == 0


def parse_records(model: type[T], payload: Any, *, context: str) -> ParseResult[T]:
    """Parse a list payload one record at a time. Never raises for bad data."""
    if payload is None:
        return ParseResult([], 0, 0)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        log.warning("%s: expected a list, got %s; treating as empty", context, type(payload).__name__)
        return ParseResult([], 0, 1, [f"payload is {type(payload).__name__}, not a list"])

    records: list[T] = []
    problems: list[str] = []
    token = _dropped.set(problems)
    try:
        for item in payload:
            try:
                records.append(model.model_validate(item))
            except ValidationError as exc:
                problems.append(_summarise(exc))
    finally:
        _dropped.reset(token)
    skipped = len(payload) - len(records)
    if problems:
        nested = len(problems) - skipped
        log.warning(
            "%s: skipped %d of %d records%s. First problem: %s",
            context,
            skipped,
            len(payload),
            f" and dropped {nested} nested items" if nested > 0 else "",
            problems[0],
        )
    return ParseResult(records, len(payload), skipped, problems[:20])


def parse_one(model: type[T], payload: Any, *, context: str) -> T | None:
    """Parse a single-object payload. Returns None (and logs) when it is unusable."""
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        log.warning("%s: expected an object, got %s", context, type(payload).__name__)
        return None
    problems: list[str] = []
    token = _dropped.set(problems)
    try:
        record = model.model_validate(payload)
    except ValidationError as exc:
        log.warning("%s: unusable payload: %s", context, _summarise(exc))
        return None
    finally:
        _dropped.reset(token)
    if problems:
        log.warning("%s: %d nested problems (bad items dropped, bad fields read as empty). First problem: %s", context, len(problems), problems[0])
    return record


# --- shared pieces ------------------------------------------------------------------------


class Clock(CfbdModel):
    minutes: int | None = None
    seconds: int | None = None


# --- /info ---------------------------------------------------------------------------------


class Info(CfbdModel):
    """The shape is not in the spec; keep every field and read what we recognise."""

    model_config = ConfigDict(extra="allow", alias_generator=to_camel, populate_by_name=True)

    patron_level: int | None = None
    remaining_calls: int | None = None


# --- /games ---------------------------------------------------------------------------------


class GamePlayoff(CfbdModel):
    """A playoff game's place in the bracket (seen in the 2025 postseason, recorded 2026-09-27):
    competition "cfp", format "twelve_team_2025", round "first_round".."championship", roundName,
    bracketSlot "FR1".."CH", homeSeed, awaySeed, bowlName."""

    competition: str | None = None
    format: str | None = None
    round: str | None = None
    round_name: str | None = None
    bracket_slot: str | None = None
    home_seed: int | None = None
    away_seed: int | None = None
    bowl_name: str | None = None


class Game(CfbdModel):
    id: int
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    start_date: str | None = None
    start_time_tbd: bool | None = Field(default=None, alias="startTimeTBD")
    completed: bool | None = None
    neutral_site: bool | None = None
    conference_game: bool | None = None
    attendance: int | None = None
    venue_id: int | None = None
    venue: str | None = None
    home_id: int | None = None
    home_team: str | None = None
    home_conference: str | None = None
    home_classification: str | None = None
    home_points: int | None = None
    home_line_scores: list[Number | None] | None = None
    home_postgame_win_probability: float | None = None
    home_pregame_elo: int | None = None
    home_postgame_elo: int | None = None
    away_id: int | None = None
    away_team: str | None = None
    away_conference: str | None = None
    away_classification: str | None = None
    away_points: int | None = None
    away_line_scores: list[Number | None] | None = None
    away_postgame_win_probability: float | None = None
    away_pregame_elo: int | None = None
    away_postgame_elo: int | None = None
    excitement_index: float | None = None
    highlights: str | None = None
    notes: str | None = None
    playoff: Annotated[GamePlayoff | None, NoneIfBad] = None  # Phase 15


# --- /games/teams (team box score) -----------------------------------------------------------


class GameTeamStat(CfbdModel):
    category: str
    stat: Scalar | None = None


class GameTeamSide(CfbdModel):
    team_id: int | None = None
    team: str | None = None
    conference: str | None = None
    home_away: str | None = None
    points: int | None = None
    stats: Annotated[list[GameTeamStat], DropBad] = []


class GameTeamStats(CfbdModel):
    id: int
    teams: Annotated[list[GameTeamSide], DropBad] = []


# --- /games/players (player box score) ------------------------------------------------------


class GamePlayerLine(CfbdModel):
    id: str
    name: str | None = None
    stat: Scalar | None = None


class GamePlayerStatType(CfbdModel):
    name: str
    athletes: Annotated[list[GamePlayerLine], DropBad] = []


class GamePlayerCategory(CfbdModel):
    name: str
    types: Annotated[list[GamePlayerStatType], DropBad] = []


class GamePlayerSide(CfbdModel):
    team: str | None = None
    conference: str | None = None
    home_away: str | None = None
    points: int | None = None
    categories: Annotated[list[GamePlayerCategory], DropBad] = []


class GamePlayerStats(CfbdModel):
    id: int
    teams: Annotated[list[GamePlayerSide], DropBad] = []


# --- /records -------------------------------------------------------------------------------


class RecordLine(CfbdModel):
    games: int | None = None
    wins: int | None = None
    losses: int | None = None
    ties: int | None = None


class TeamRecords(CfbdModel):
    team: str
    year: int | None = None
    team_id: int | None = None
    classification: str | None = None
    conference: str | None = None
    division: str | None = None
    expected_wins: float | None = None
    total: RecordLine | None = None
    conference_games: RecordLine | None = None
    home_games: RecordLine | None = None
    away_games: RecordLine | None = None
    neutral_site_games: RecordLine | None = None
    regular_season: RecordLine | None = None
    postseason: RecordLine | None = None


# --- /rankings ------------------------------------------------------------------------------


class PollRank(CfbdModel):
    school: str
    rank: int | None = None
    team_id: int | None = None
    conference: str | None = None
    first_place_votes: int | None = None
    points: int | None = None


class Poll(CfbdModel):
    poll: str
    is_final: bool | None = None
    ranks: Annotated[list[PollRank], DropBad] = []


class PollWeek(CfbdModel):
    week: int
    season: int | None = None
    season_type: str | None = None
    polls: Annotated[list[Poll], DropBad] = []


# --- /stats/season ---------------------------------------------------------------------------


class TeamStat(CfbdModel):
    team: str
    stat_name: str
    season: int | None = None
    conference: str | None = None
    stat_value: Scalar | None = None


# --- /stats/season/advanced ------------------------------------------------------------------


class AdvancedPlays(CfbdModel):
    rate: float | None = None
    ppa: float | None = None
    total_ppa: float | None = Field(default=None, alias="totalPPA")
    success_rate: float | None = None
    explosiveness: float | None = None


class AdvancedHavoc(CfbdModel):
    total: float | None = None
    front_seven: float | None = None
    db: float | None = None


class AdvancedFieldPosition(CfbdModel):
    average_start: float | None = None
    average_predicted_points: float | None = None


class AdvancedSide(CfbdModel):
    plays: int | None = None
    drives: int | None = None
    ppa: float | None = None
    total_ppa: float | None = Field(default=None, alias="totalPPA")
    success_rate: float | None = None
    explosiveness: float | None = None
    power_success: float | None = None
    stuff_rate: float | None = None
    line_yards: float | None = None
    line_yards_total: float | None = None
    second_level_yards: float | None = None
    second_level_yards_total: float | None = None
    open_field_yards: float | None = None
    open_field_yards_total: float | None = None
    total_opportunities: int | None = Field(default=None, alias="totalOpportunies")
    points_per_opportunity: float | None = None
    field_position: AdvancedFieldPosition | None = None
    havoc: AdvancedHavoc | None = None
    standard_downs: AdvancedPlays | None = None
    passing_downs: AdvancedPlays | None = None
    rushing_plays: AdvancedPlays | None = None
    passing_plays: AdvancedPlays | None = None


class AdvancedSeasonStat(CfbdModel):
    team: str
    season: int | None = None
    conference: str | None = None
    offense: AdvancedSide | None = None
    defense: AdvancedSide | None = None


# --- /stats/player/season --------------------------------------------------------------------


class PlayerStat(CfbdModel):
    player_id: str
    player: str | None = None
    season: int | None = None
    position: str | None = None
    team: str | None = None
    conference: str | None = None
    category: str | None = None
    stat_type: str | None = None
    stat: Scalar | None = None


# --- /roster ---------------------------------------------------------------------------------


class RosterPlayer(CfbdModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    team: str | None = None
    height: float | None = None
    weight: int | None = None
    jersey: int | None = None
    year: int | None = None
    position: str | None = None
    home_city: str | None = None
    home_state: str | None = None
    home_country: str | None = None
    home_latitude: float | None = None
    home_longitude: float | None = None
    home_county_fips: str | None = Field(default=None, alias="homeCountyFIPS")
    recruit_ids: list[str] | None = None


# --- /drives and /plays ----------------------------------------------------------------------


class Drive(CfbdModel):
    id: str
    game_id: int | None = None
    offense: str | None = None
    offense_conference: str | None = None
    defense: str | None = None
    defense_conference: str | None = None
    drive_number: int | None = None
    scoring: bool | None = None
    start_period: int | None = None
    start_yardline: int | None = None
    start_yards_to_goal: int | None = None
    start_time: Clock | None = None
    end_period: int | None = None
    end_yardline: int | None = None
    end_yards_to_goal: int | None = None
    end_time: Clock | None = None
    elapsed: Clock | None = None
    plays: int | None = None
    yards: int | None = None
    drive_result: str | None = None
    is_home_offense: bool | None = None
    start_offense_score: int | None = None
    start_defense_score: int | None = None
    end_offense_score: int | None = None
    end_defense_score: int | None = None


class Play(CfbdModel):
    id: str
    drive_id: str | None = None
    game_id: int | None = None
    drive_number: int | None = None
    play_number: int | None = None
    offense: str | None = None
    offense_conference: str | None = None
    offense_score: int | None = None
    defense: str | None = None
    home: str | None = None
    away: str | None = None
    defense_conference: str | None = None
    defense_score: int | None = None
    period: int | None = None
    clock: Clock | None = None
    offense_timeouts: int | None = None
    defense_timeouts: int | None = None
    yardline: int | None = None
    yards_to_goal: int | None = None
    down: int | None = None
    distance: int | None = None
    yards_gained: int | None = None
    scoring: bool | None = None
    play_type: str | None = None
    play_text: str | None = None
    ppa: float | None = None
    wallclock: str | None = None


# --- expected points tables (Phase 12, fourth-down break-even) ------------------------------


class PredictedPoints(CfbdModel):
    """/ppa/predicted?down=&distance= row (verified 2026-09-26): yardLine counts from the offense's
    own goal line (97 is the opponent's 3); the 1st-and-10 table ends at 90."""

    yard_line: int  # the row's identity: a row without it is skipped
    predicted_points: float | None = None


class FieldGoalEp(CfbdModel):
    """/metrics/fg/ep row (verified 2026-09-26): expectedPoints is 3 x the make chance only."""

    yards_to_goal: int  # the row's identity
    distance: int | None = None
    expected_points: float | None = None


# --- Phase 13 (stats depth II), every shape from a real answer recorded 2026-09-26 ----------------
# (the 2025 samples for the opponent-adjusted metrics and SRS, which CFBD had not filled for 2026)


class PlayerTransfer(LenientModel):
    """/player/portal?year= (4,472 rows for 2026). No player id: joined to rosters by name and school."""

    first_name: str  # with last_name, the record's identity (the portal has no player id)
    last_name: str
    season: int | None = None
    position: str | None = None
    origin: str | None = None
    destination: str | None = None
    transfer_date: str | None = None
    rating: float | None = None
    stars: int | None = None
    eligibility: str | None = None


class TeamRecruitingRanking(LenientModel):
    """/recruiting/teams?year= (221 teams for 2026; empty for 2027 so far)."""

    team: str
    year: int | None = None
    rank: int | None = None
    points: float | None = None


class AdjustedSplit(LenientModel):
    total: float | None = None
    passing: float | None = None
    rushing: float | None = None
    standard_downs: float | None = None
    passing_downs: float | None = None


class AdjustedRushing(LenientModel):
    line_yards: float | None = None
    second_level_yards: float | None = None
    open_field_yards: float | None = None
    highlight_yards: float | None = None


class AdjustedTeamMetrics(LenientModel):
    """/wepa/team/season?year= (opponent-adjusted EPA and success; empty for 2026 as of 2026-09-26)."""

    team: str
    team_id: int | None = None
    year: int | None = None
    conference: str | None = None
    epa: AdjustedSplit | None = None
    epa_allowed: AdjustedSplit | None = None
    success_rate: AdjustedSplit | None = None
    success_rate_allowed: AdjustedSplit | None = None
    rushing: AdjustedRushing | None = None
    rushing_allowed: AdjustedRushing | None = None
    explosiveness: float | None = None
    explosiveness_allowed: float | None = None


class PlayerWeightedEPA(LenientModel):
    """/wepa/players/passing and /rushing?year=."""

    athlete_id: str
    athlete_name: str | None = None
    year: int | None = None
    position: str | None = None
    team: str | None = None
    conference: str | None = None
    wepa: float | None = None
    plays: int | None = None


class KickerPAAR(LenientModel):
    """/wepa/players/kicking?year= (points added above replacement, 154 kickers for 2026)."""

    athlete_id: str
    athlete_name: str | None = None
    year: int | None = None
    team: str | None = None
    conference: str | None = None
    paar: float | None = None
    attempts: int | None = None


class TeamCoreRating(LenientModel):
    """/ratings/core?year= (CFBD's own rating: 138 teams through week 3 of 2026)."""

    team: str
    year: int | None = None
    conference: str | None = None
    overall: float | None = None
    offense: float | None = None
    defense: float | None = None
    offense_plays: int | None = None
    defense_plays: int | None = None
    through_week: int | None = None
    model_version: str | None = None


class TeamSRS(LenientModel):
    """/ratings/srs?year= (empty for 2026 as of 2026-09-26)."""

    team: str
    year: int | None = None
    conference: str | None = None
    rating: float | None = None
    ranking: int | None = None


class ConferenceSPUnit(LenientModel):
    rating: float | None = None


class ConferenceSP(LenientModel):
    """/ratings/sp/conferences?year= (11 conferences; sos and second-order wins null early)."""

    conference: str
    year: int | None = None
    rating: float | None = None
    second_order_wins: float | None = None
    sos: float | None = None
    offense: ConferenceSPUnit | None = None
    defense: ConferenceSPUnit | None = None
    special_teams: ConferenceSPUnit | None = None


class RushingPlay(LenientModel):
    """/rushing/plays?year=&team= (both sides of the team's games; filter on offense)."""

    play_id: str
    game_id: int | None = None
    week: int | None = None
    offense: str | None = None
    defense: str | None = None
    period: int | None = None
    down: int | None = None
    distance: int | None = None
    start_yards_to_goal: int | None = None
    rusher: str | None = None
    rusher_id: str | None = None
    rush_direction: str | None = None
    rushing_yards: int | None = None
    is_rushing_touchdown: bool | None = None
    is_sack: bool | None = None
    is_kneel: bool | None = None
    success: bool | None = None
    ppa: float | None = None


class PassingPlay(LenientModel):
    """/passing/plays?year=&team= (both sides of the team's games; filter on offense)."""

    play_id: str
    game_id: int | None = None
    week: int | None = None
    offense: str | None = None
    defense: str | None = None
    period: int | None = None
    down: int | None = None
    distance: int | None = None
    start_yards_to_goal: int | None = None
    passer: str | None = None
    target: str | None = None
    outcome: str | None = None
    air_yards: int | None = None
    pass_depth: str | None = None
    pass_direction: str | None = None
    total_yards: int | None = None
    is_spike: bool | None = None
    is_throwaway: bool | None = None
    success: bool | None = None
    ppa: float | None = None


# --- /live/plays --------------------------------------------------------------------------


class LiveGamePlay(LenientModel):
    id: str
    home_score: int | None = None
    away_score: int | None = None
    period: int | None = None
    clock: str | None = None
    wall_clock: str | None = None
    team_id: int | None = None
    team: str | None = None
    down: int | None = None
    distance: int | None = None
    yards_to_goal: int | None = None
    yards_gained: int | None = None
    play_type_id: int | None = None
    play_type: str | None = None
    epa: float | None = None
    garbage_time: bool | None = None
    success: bool | None = None
    rush_pass: str | None = None
    down_type: str | None = None
    play_text: str | None = None


class LiveGameDrive(LenientModel):
    id: str
    offense_id: int | None = None
    offense: str | None = None
    defense_id: int | None = None
    defense: str | None = None
    play_count: int | None = None
    yards: int | None = None
    start_period: int | None = None
    start_clock: str | None = None
    start_yards_to_goal: int | None = None
    end_period: int | None = None
    end_clock: str | None = None
    end_yards_to_goal: int | None = None
    duration: str | None = None
    scoring_opportunity: bool | None = None
    result: str | None = None
    points_gained: int | None = None
    plays: Annotated[list[LiveGamePlay], DropBad] = []


class LiveGameTeam(LenientModel):
    team_id: int | None = None
    team: str | None = None
    home_away: str | None = None
    line_scores: list[Number | None] | None = None
    points: int | None = None
    drives: int | None = None
    scoring_opportunities: int | None = None
    points_per_opportunity: float | None = None
    average_start_yard_line: float | None = None
    plays: int | None = None
    line_yards: float | None = None
    line_yards_per_rush: float | None = None
    second_level_yards: float | None = None
    second_level_yards_per_rush: float | None = None
    open_field_yards: float | None = None
    open_field_yards_per_rush: float | None = None
    epa_per_play: float | None = None
    total_epa: float | None = None
    passing_epa: float | None = None
    epa_per_pass: float | None = None
    rushing_epa: float | None = None
    epa_per_rush: float | None = None
    success_rate: float | None = None
    standard_down_success_rate: float | None = None
    passing_down_success_rate: float | None = None
    explosiveness: float | None = None
    deserve_to_win: float | None = None


class LiveGame(LenientModel):
    id: int
    status: str | None = None
    period: int | None = None
    clock: str | None = None
    possession: str | None = None
    down: int | None = None
    distance: int | None = None
    yards_to_goal: int | None = None
    teams: Annotated[list[LiveGameTeam], DropBad] = []
    drives: Annotated[list[LiveGameDrive], DropBad] = []


# --- /scoreboard --------------------------------------------------------------------------


class ScoreboardVenue(LenientModel):
    name: str | None = None
    city: str | None = None
    state: str | None = None


class ScoreboardTeam(LenientModel):
    id: int | None = None
    name: str | None = None
    conference: str | None = None
    classification: str | None = None
    points: int | None = None
    line_scores: list[Number | None] | None = None
    win_probability: float | None = None


class ScoreboardWeather(LenientModel):
    temperature: float | None = None
    description: str | None = None
    wind_speed: float | None = None
    wind_direction: float | None = None


class ScoreboardBetting(LenientModel):
    spread: float | None = None
    over_under: float | None = None
    home_moneyline: float | None = None
    away_moneyline: float | None = None


class ScoreboardGame(LenientModel):
    id: int
    start_date: str | None = None
    start_time_tbd: bool | None = Field(default=None, alias="startTimeTBD")
    tv: str | None = None
    neutral_site: bool | None = None
    conference_game: bool | None = None
    status: str | None = None
    period: int | None = None
    clock: str | None = None
    situation: str | None = None
    possession: str | None = None
    last_play: str | None = None
    venue: ScoreboardVenue | None = None
    home_team: ScoreboardTeam | None = None
    away_team: ScoreboardTeam | None = None
    weather: ScoreboardWeather | None = None
    betting: ScoreboardBetting | None = None


# --- /lines --------------------------------------------------------------------------------


class GameLine(CfbdModel):
    provider: str | None = None
    spread: float | None = None
    formatted_spread: str | None = None
    spread_open: float | None = None
    over_under: float | None = None
    over_under_open: float | None = None
    home_moneyline: float | None = None
    away_moneyline: float | None = None


class BettingGame(CfbdModel):
    id: int
    season: int | None = None
    season_type: str | None = None
    week: int | None = None
    start_date: str | None = None
    home_team_id: int | None = None
    home_team: str | None = None
    home_conference: str | None = None
    home_classification: str | None = None
    home_score: int | None = None
    away_team_id: int | None = None
    away_team: str | None = None
    away_conference: str | None = None
    away_classification: str | None = None
    away_score: int | None = None
    lines: Annotated[list[GameLine], DropBad] = []


# --- /games/weather --------------------------------------------------------------------------


class GameWeather(CfbdModel):
    id: int
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    start_time: str | None = None
    game_indoors: bool | None = None
    home_team: str | None = None
    home_conference: str | None = None
    away_team: str | None = None
    away_conference: str | None = None
    venue_id: int | None = None
    venue: str | None = None
    temperature: float | None = None
    dew_point: float | None = None
    humidity: float | None = None
    precipitation: float | None = None
    snowfall: float | None = None
    wind_direction: float | None = None
    wind_speed: float | None = None
    pressure: float | None = None
    weather_condition_code: int | None = None
    weather_condition: str | None = None


# --- /games/media ------------------------------------------------------------------------------


class GameMedia(CfbdModel):
    id: int
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    start_time: str | None = None
    is_start_time_tbd: bool | None = Field(default=None, alias="isStartTimeTBD")
    home_team: str | None = None
    home_conference: str | None = None
    away_team: str | None = None
    away_conference: str | None = None
    media_type: str | None = None
    outlet: str | None = None


# --- /teams/matchup ----------------------------------------------------------------------------


class MatchupGame(CfbdModel):
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    date: str | None = None
    neutral_site: bool | None = None
    venue: str | None = None
    home_team: str | None = None
    home_score: int | None = None
    away_team: str | None = None
    away_score: int | None = None
    winner: str | None = None


class Matchup(CfbdModel):
    team1: str | None = None
    team2: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    team1_wins: int | None = None
    team2_wins: int | None = None
    ties: int | None = None
    games: Annotated[list[MatchupGame], DropBad] = []


# --- /metrics/wp and /metrics/wp/pregame -----------------------------------------------------


class PlayWinProbability(CfbdModel):
    play_id: str
    game_id: int | None = None
    play_text: str | None = None
    home_id: int | None = None
    home: str | None = None
    away_id: int | None = None
    away: str | None = None
    spread: float | None = None
    home_ball: bool | None = None
    home_score: int | None = None
    away_score: int | None = None
    yard_line: int | None = None
    down: int | None = None
    distance: int | None = None
    home_win_probability: float | None = None
    play_number: int | None = None


class PregameWinProbability(CfbdModel):
    game_id: int
    season: int | None = None
    season_type: str | None = None
    week: int | None = None
    home_team: str | None = None
    away_team: str | None = None
    spread: float | None = None
    home_win_probability: float | None = None


# --- /ppa/games and /ppa/players/games -----------------------------------------------------------


class PpaSide(CfbdModel):
    overall: float | None = None
    passing: float | None = None
    rushing: float | None = None
    first_down: float | None = None
    second_down: float | None = None
    third_down: float | None = None


class TeamGamePpa(CfbdModel):
    game_id: int
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    team: str | None = None
    conference: str | None = None
    opponent: str | None = None
    offense: PpaSide | None = None
    defense: PpaSide | None = None


class PlayerPpaAverage(CfbdModel):
    all: float | None = None
    pass_: float | None = Field(default=None, alias="pass")
    rush: float | None = None


class PlayerGamePpa(CfbdModel):
    id: str
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    name: str | None = None
    position: str | None = None
    team: str | None = None
    opponent: str | None = None
    average_ppa: PlayerPpaAverage | None = Field(default=None, alias="averagePPA")


# --- /ppa/players/season, /player/usage, /talent, /player/returning (Phase 10, spec-checked 2026-09-23) ----


class PlayerSeasonPpa(CfbdModel):
    """averagePPA and totalPPA are objects the spec leaves open; the keys seen are all, pass, rush,
    firstDown, secondDown, thirdDown, standardDowns, passingDowns. Read them defensively."""

    id: str
    season: int | None = None
    name: str | None = None
    position: str | None = None
    team: str | None = None
    conference: str | None = None
    countable_plays: int | None = None
    average_ppa: dict[str, Any] | None = Field(default=None, alias="averagePPA")
    total_ppa: dict[str, Any] | None = Field(default=None, alias="totalPPA")


class PlayerUsage(CfbdModel):
    """usage is an object of shares (0 to 1): overall, pass, rush, firstDown, secondDown, thirdDown,
    standardDowns, passingDowns."""

    id: str
    season: int | None = None
    name: str | None = None
    position: str | None = None
    team: str | None = None
    conference: str | None = None
    usage: dict[str, Any] | None = None


class TeamTalent(CfbdModel):
    team: str
    year: int | None = None
    talent: float | None = None


class ReturningProduction(CfbdModel):
    team: str
    season: int | None = None
    conference: str | None = None
    total_ppa: float | None = Field(default=None, alias="totalPPA")
    total_passing_ppa: float | None = Field(default=None, alias="totalPassingPPA")
    total_receiving_ppa: float | None = Field(default=None, alias="totalReceivingPPA")
    total_rushing_ppa: float | None = Field(default=None, alias="totalRushingPPA")
    percent_ppa: float | None = Field(default=None, alias="percentPPA")
    percent_passing_ppa: float | None = Field(default=None, alias="percentPassingPPA")
    percent_receiving_ppa: float | None = Field(default=None, alias="percentReceivingPPA")
    percent_rushing_ppa: float | None = Field(default=None, alias="percentRushingPPA")
    usage: float | None = None
    passing_usage: float | None = None
    receiving_usage: float | None = None
    rushing_usage: float | None = None


# --- /ratings/sp, /ratings/elo, /ratings/fpi ----------------------------------------------------


class SpUnit(CfbdModel):
    rating: float | None = None
    ranking: int | None = None
    success: float | None = None
    explosiveness: float | None = None
    rushing: float | None = None
    passing: float | None = None
    standard_downs: float | None = None
    passing_downs: float | None = None
    run_rate: float | None = None
    pace: float | None = None
    havoc: AdvancedHavoc | None = None


class TeamSP(CfbdModel):
    team: str
    year: int | None = None
    conference: str | None = None
    rating: float | None = None
    ranking: int | None = None
    second_order_wins: float | None = None
    sos: float | None = None
    offense: SpUnit | None = None
    defense: SpUnit | None = None
    special_teams: SpUnit | None = None


class TeamElo(CfbdModel):
    team: str
    year: int | None = None
    conference: str | None = None
    elo: int | None = None


class FpiResumeRanks(CfbdModel):
    strength_of_record: int | None = None
    fpi: int | None = None
    average_win_probability: int | None = None
    strength_of_schedule: int | None = None
    remaining_strength_of_schedule: int | None = None
    game_control: int | None = None


class FpiEfficiencies(CfbdModel):
    overall: float | None = None
    offense: float | None = None
    defense: float | None = None
    special_teams: float | None = None


class TeamFPI(CfbdModel):
    team: str
    year: int | None = None
    conference: str | None = None
    fpi: float | None = None
    resume_ranks: FpiResumeRanks | None = None
    efficiencies: FpiEfficiencies | None = None


# --- /recruiting/players -----------------------------------------------------------------------


class RecruitHometown(CfbdModel):
    fips_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class Recruit(CfbdModel):
    id: str
    athlete_id: str | None = None
    recruit_type: str | None = None
    year: int | None = None
    ranking: int | None = None
    name: str | None = None
    school: str | None = None
    committed_to: str | None = None
    position: str | None = None
    height: float | None = None
    weight: int | None = None
    stars: int | None = None
    rating: float | None = None
    city: str | None = None
    state_province: str | None = None
    country: str | None = None
    hometown_info: RecruitHometown | None = None


# --- /teams and /calendar -----------------------------------------------------------------------


class Team(CfbdModel):
    id: int
    school: str | None = None
    mascot: str | None = None
    abbreviation: str | None = None
    alternate_names: list[str] | None = None
    conference: str | None = None
    division: str | None = None
    classification: str | None = None
    color: str | None = None
    alternate_color: str | None = None
    logos: list[str] | None = None
    twitter: str | None = None
    location: dict[str, Any] | None = None


class CalendarWeek(CfbdModel):
    week: int
    season: int | None = None
    season_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    first_game_start: str | None = None
    last_game_start: str | None = None


# --- /venues and /coaches (added 2026-09-23 for the program) ---------------------------------------


class Venue(CfbdModel):
    id: int
    name: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation: str | None = None
    capacity: int | None = None
    construction_year: int | None = None
    grass: bool | None = None
    dome: bool | None = None


class CoachSeason(CfbdModel):
    team_id: int | None = None
    school: str | None = None
    conference: str | None = None
    year: int | None = None
    games: int | None = None
    wins: int | None = None
    losses: int | None = None
    ties: int | None = None
    win_percentage: float | None = None
    preseason_rank: int | None = None
    postseason_rank: int | None = None
    srs: float | None = None
    sp_overall: float | None = None
    sp_offense: float | None = None
    sp_defense: float | None = None


class Coach(CfbdModel):
    id: int  # required in the spec; an empty object is not a coach
    first_name: str | None = None
    last_name: str | None = None
    hire_date: str | None = None
    seasons: Annotated[list[CoachSeason], DropBad] = []


# --- /player/search (Phase 15, spec v5.31.1; up to 100 players whose names match) --------------------


class PlayerSearchResult(CfbdModel):
    id: str
    name: str
    team: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    weight: int | None = None
    height: float | None = None
    jersey: int | None = None
    position: str | None = None
    hometown: str | None = None
    team_color: str | None = None
    active_start_year: int | None = None
    active_end_year: int | None = None


# --- endpoint registry ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Endpoint:
    path: str
    model: type[CfbdModel] | None  # None: plain JSON (a list of strings for /stats/categories)
    many: bool
    kind: DataKind
    required: tuple[str, ...] = ()


ENDPOINTS: dict[str, Endpoint] = {
    e.path: e
    for e in [
        Endpoint("/info", Info, False, DataKind.INFO),
        Endpoint("/calendar", CalendarWeek, True, DataKind.REFERENCE, ("year",)),
        Endpoint("/stats/categories", None, True, DataKind.REFERENCE),
        Endpoint("/teams", Team, True, DataKind.TEAMS),
        Endpoint("/teams/fbs", Team, True, DataKind.TEAMS),
        Endpoint("/venues", Venue, True, DataKind.TEAMS),
        Endpoint("/coaches", Coach, True, DataKind.TEAMS),
        Endpoint("/roster", RosterPlayer, True, DataKind.ROSTER),
        Endpoint("/recruiting/players", Recruit, True, DataKind.RECRUITING),
        Endpoint("/teams/matchup", Matchup, False, DataKind.HISTORY, ("team1", "team2")),
        Endpoint("/games", Game, True, DataKind.SCHEDULE),
        Endpoint("/records", TeamRecords, True, DataKind.SCHEDULE),
        Endpoint("/rankings", PollWeek, True, DataKind.SCHEDULE, ("year",)),
        Endpoint("/games/media", GameMedia, True, DataKind.SCHEDULE, ("year",)),
        Endpoint("/stats/season", TeamStat, True, DataKind.SEASON_STATS),
        Endpoint("/stats/season/advanced", AdvancedSeasonStat, True, DataKind.SEASON_STATS),
        Endpoint("/stats/player/season", PlayerStat, True, DataKind.SEASON_STATS, ("year",)),
        Endpoint("/ratings/sp", TeamSP, True, DataKind.SEASON_STATS),
        Endpoint("/ratings/elo", TeamElo, True, DataKind.SEASON_STATS),
        Endpoint("/ratings/fpi", TeamFPI, True, DataKind.SEASON_STATS),
        Endpoint("/ppa/games", TeamGamePpa, True, DataKind.SEASON_STATS, ("year",)),
        Endpoint("/ppa/players/games", PlayerGamePpa, True, DataKind.SEASON_STATS, ("year",)),
        Endpoint("/ppa/players/season", PlayerSeasonPpa, True, DataKind.SEASON_STATS),
        Endpoint("/player/usage", PlayerUsage, True, DataKind.SEASON_STATS, ("year",)),
        Endpoint("/talent", TeamTalent, True, DataKind.SEASON_STATS, ("year",)),
        Endpoint("/player/returning", ReturningProduction, True, DataKind.SEASON_STATS),
        Endpoint("/metrics/wp/pregame", PregameWinProbability, True, DataKind.SEASON_STATS),
        Endpoint("/lines", BettingGame, True, DataKind.LINES),
        Endpoint("/games/weather", GameWeather, True, DataKind.WEATHER),
        Endpoint("/games/teams", GameTeamStats, True, DataKind.FINISHED_GAME),
        Endpoint("/games/players", GamePlayerStats, True, DataKind.FINISHED_GAME),
        Endpoint("/drives", Drive, True, DataKind.FINISHED_GAME, ("year",)),
        Endpoint("/plays", Play, True, DataKind.FINISHED_GAME, ("year", "week")),
        Endpoint("/metrics/wp", PlayWinProbability, True, DataKind.FINISHED_GAME, ("gameId",)),
        Endpoint("/scoreboard", ScoreboardGame, True, DataKind.SCOREBOARD),
        Endpoint("/ppa/predicted", PredictedPoints, True, DataKind.REFERENCE, ("down", "distance")),
        Endpoint("/metrics/fg/ep", FieldGoalEp, True, DataKind.REFERENCE),
        # Phase 13 (stats depth II); the advanced box score stays plain JSON, normalized with guards in app/services/depth2.py
        Endpoint("/game/box/advanced", None, False, DataKind.FINISHED_GAME, ("id",)),
        Endpoint("/player/portal", PlayerTransfer, True, DataKind.SEASON_STATS, ("year",)),
        Endpoint("/recruiting/teams", TeamRecruitingRanking, True, DataKind.RECRUITING),
        Endpoint("/wepa/team/season", AdjustedTeamMetrics, True, DataKind.SEASON_STATS),
        Endpoint("/wepa/players/passing", PlayerWeightedEPA, True, DataKind.SEASON_STATS),
        Endpoint("/wepa/players/rushing", PlayerWeightedEPA, True, DataKind.SEASON_STATS),
        Endpoint("/wepa/players/kicking", KickerPAAR, True, DataKind.SEASON_STATS),
        Endpoint("/ratings/core", TeamCoreRating, True, DataKind.SEASON_STATS),
        Endpoint("/ratings/srs", TeamSRS, True, DataKind.SEASON_STATS),
        Endpoint("/ratings/sp/conferences", ConferenceSP, True, DataKind.SEASON_STATS),
        Endpoint("/rushing/plays", RushingPlay, True, DataKind.SEASON_STATS),
        Endpoint("/passing/plays", PassingPlay, True, DataKind.SEASON_STATS),
        Endpoint("/player/search", PlayerSearchResult, True, DataKind.ROSTER, ("searchTerm",)),  # Phase 15
        Endpoint("/live/plays", LiveGame, False, DataKind.LIVE, ("gameId",)),
    ]
}


def normalize_endpoint(value: str) -> str:
    """Accept 'records', '/records', or a Git Bash mangled 'C:/Program Files/Git/records'."""
    value = value.strip().replace("\\", "/")
    if value in ENDPOINTS:
        return value
    matches = [path for path in ENDPOINTS if value.endswith(path)]
    if matches:
        return max(matches, key=len)
    return "/" + value.lstrip("/")


def parse_endpoint(path: str, payload: Any, *, context: str | None = None) -> ParseResult[Any] | Any:
    """Parse a payload with the model registered for its endpoint.

    Lists return a ParseResult; single objects return the model or None; endpoints without a
    model return the payload as is.
    """
    spec = ENDPOINTS[path]
    label = context or path
    if spec.model is None:
        return payload
    if spec.many:
        return parse_records(spec.model, payload, context=label)
    return parse_one(spec.model, payload, context=label)
