"""The paper's funny headlines (queue items 10 to 12, mock approved 2026-10-13).

One line written from a ranked game's own facts, before kickoff and after the final only (owner: "Funny headline only
for the pregame and postgame articles"); a game under way gets none, and the page shows its score, quarter and clock.
No betting talk: never the line, odds or picks. Our own team is kept kind (owner: "keep us kind"): every game of ours
uses its own templates, and no joke in them is at our expense.

  write(game, *, us, tz, used=None)  -> {"kind", "kicker", "text"} or None (a live game, or one without both teams)
  write_all(games, *, us, tz)        -> the same for a page of games in their order; a template already used on the
                                        page is skipped where the kind has another, so two boxes rarely read alike
  kind_of(game, *, us, tz)           -> the template kind a game falls in, or None
  TEMPLATES, KICKERS                 the wording by kind

A game always starts from the same template of its kind (picked by its id), so its headline never flickers between
refreshes; the newspaper keeps a final's headline in the week's edition once it is written (app/services/editions.py).

The game is the ranked week's shape (app/services/rankedweek.py): gameId, status ("pre", "live", "final"), kickoff (ISO),
startTimeTbd, neutralSite, isUs, and home and away blocks with school, mascot, rank, record {wins, losses}, points and
lineScores. Anything missing or of the wrong type reads as unknown, never as an error.
"""

from __future__ import annotations

import re
import zlib
from datetime import datetime, tzinfo
from typing import Any

NBSP = " "  # "No. 12" never breaks across two lines

TEMPLATES: dict[str, tuple[str, ...]] = {
    # our own games: kind in every outcome
    "usPre": (
        "{US} gets its shot at {OPP} {WHEN}; the {USM} have heard enough about the {OPPM}",
        "Game day: {US} and {OPP} {WHEN}, and the {USM} are ready",
        "{US} takes on {OPP} {WHEN}; the {USM} like their chances",
    ),
    "usWin": (
        "{US} takes down {OPP}, {A}-{B}! Somebody call the pollsters",
        "{US} beats {OPP}, {A}-{B}; a good night to be a {USM} fan",
        "{US} {A}, {OPP} {B}: the {USM} roll on",
    ),
    "usLose": (
        "{OPP} tops {US}, {B}-{A}; the {USM} get back to work Monday",
        "A tough night for {US}: {OPP} wins, {B}-{A}; the {USM} regroup for next week",
        "{US} comes up short against {OPP}, {B}-{A}; heads up, {USM}",
    ),
    # before kickoff
    "preTop": (
        "{AW} {VISITS} {HM} {WHEN}; one of these rankings is about to take a dent",
        "{AW} and {HM} meet {WHEN}; the pollsters have their pencils out",
        "{AW} {VISITS} {HM} {WHEN}; somebody's ranking won't survive the night",
    ),
    "preUnbeaten": (
        "Unbeaten {X} puts its {XW}-0 record at stake {Y} {WHEN}",
        "{X} is {XW}-0 and wants to stay that way; {Y} {WHEN}",
    ),
    "preLate": (
        "{AW} {VISITS} {HM}, {TIME} kickoff; brew the coffee",
        "Night owls only: {AW} {VISITS} {HM}, {TIME} kickoff",
    ),
    "pre": (
        "{R} puts its Top 25 spot at stake {Y} {WHEN}",
        "{AW} {VISITS} {HM} {WHEN} with a Top 25 spot to protect",
        "{R} looks to stay in the Top 25 {Y} {WHEN}",
    ),
    # after the final
    "finalUpset": (
        "{W} stuns {L}, {A}-{B}; an anonymous {LS} fan says, \"Our team stinks!\"",
        "{W} {A}, {L} {B}: somebody tell the pollsters",
        "{W} sends {L} home grumbling, {A}-{B}",
    ),
    "finalShakeup": (
        "{W} knocks off {L}, {A}-{B}; the pollsters reach for their erasers",
        "{W} topples {L}, {A}-{B}; the Top 25 gets a rewrite",
    ),
    "overtime": (
        "{W} outlasts {L}, {A}-{B}, in {OT}; nobody's fingernails survived",
        "{W} takes {L} to {OT} and wins it, {A}-{B}",
    ),
    "shootout": (
        "{W} outlasts {L}, {A}-{B}; defense was strictly optional",
        "{W} outscores {L}, {A}-{B}; the scoreboard needs a nap",
    ),
    "winless": ("{LS} stays winless as {W} cruises, {A}-{B}; the search for win No.{NB}1 goes on",),
    "bigNumber": (
        "{W} hangs {A} on {L}; the scoreboard operator asks for overtime pay",
        "{W} puts up {A} on {L}; somebody check the scoreboard's batteries",
    ),
    "rout": (
        "{W} rolls past {L}, {A}-{B}; {LS} fans spotted checking the basketball schedule",
        "{W} routs {L}, {A}-{B}; the backups got plenty of snaps",
    ),
    "escape": (
        "{W} survives {L}, {A}-{B}; {WS} fans may now unclench",
        "{W} escapes {L}, {A}-{B}; {WS} fans can exhale",
    ),
    "handles": (
        "{W} handles {L}, {A}-{B}; no drama, no complaints",
        "{W} takes care of business against {L}, {A}-{B}",
        "{W} beats {L}, {A}-{B}, and moves on",
    ),
}

KICKERS: dict[str, str] = {
    "usPre": "Our game", "usWin": "Our game", "usLose": "Our game",
    "preTop": "Top 25 clash", "preUnbeaten": "Unbeaten", "preLate": "Late show", "pre": "Top 25",
    "finalUpset": "Upset", "finalShakeup": "Shake-up", "overtime": "Overtime", "shootout": "Shootout",
    "winless": "Final", "bigNumber": "Track meet", "rout": "Rout", "escape": "Escape", "handles": "Final",
}

WINLESS_AFTER = 3  # "stays winless" only once a team has lost three (review: every opener's loser is 0-1)
LATE_HOUR = 21  # a kickoff at 9 PM or later (or before 4 AM), the reader's time zone: the late show
EARLY_HOUR = 4


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _word(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _side(game: dict[str, Any], key: str) -> dict[str, Any]:
    block = game.get(key)
    return block if isinstance(block, dict) else {}


def ranked_name(team: dict[str, Any]) -> str:
    """'No. 12 Bluegrass Bottoms' for a ranked team (the number never breaks from 'No.'), else the school."""
    school = _word(team.get("school")) or "TBD"
    rank = _int(team.get("rank"))
    return f"No.{NBSP}{rank} {school}" if rank is not None else school


def _record(team: dict[str, Any]) -> tuple[int | None, int | None]:
    rec = team.get("record") if isinstance(team.get("record"), dict) else {}
    return _int(rec.get("wins")), _int(rec.get("losses"))


def _kickoff(game: dict[str, Any], tz: tzinfo) -> datetime | None:
    raw = _word(game.get("kickoff"))
    if raw is None or game.get("startTimeTbd") is True:
        return None
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.astimezone(tz) if when.tzinfo is not None else None


def _time_text(local: datetime) -> str:
    return f"{local.hour % 12 or 12}:{local.minute:02d}{NBSP}{'AM' if local.hour < 12 else 'PM'}"


def _overtimes(game: dict[str, Any]) -> int:
    """How many overtime periods the final's line scores show (0 for a game decided in four quarters)."""
    periods = max(len(_side(game, "home").get("lineScores") or []), len(_side(game, "away").get("lineScores") or []))
    return max(0, periods - 4)


def _scores(game: dict[str, Any]) -> tuple[int, int] | None:
    home, away = _int(_side(game, "home").get("points")), _int(_side(game, "away").get("points"))
    return (home, away) if home is not None and away is not None else None


def kind_of(game: Any, *, us: str | None, tz: tzinfo) -> str | None:
    """The template kind for a game: one of TEMPLATES' keys, or None for a live game or one that cannot be written."""
    if not isinstance(game, dict):
        return None
    status = game.get("status")
    home, away = _side(game, "home"), _side(game, "away")
    if not _word(home.get("school")) or not _word(away.get("school")) or status not in ("pre", "final"):
        return None
    scores = _scores(game)
    if status == "final" and scores is None:
        return None  # a final without its score: nothing true to say
    ours = game.get("isUs") is True or (us is not None and us in (home.get("school"), away.get("school")))
    if ours:
        if status == "pre":
            return "usPre"
        mine = home if home.get("school") == us else away
        theirs = away if mine is home else home
        return "usWin" if (_int(mine.get("points")) or 0) > (_int(theirs.get("points")) or 0) else "usLose"
    if status == "pre":
        h_rank, a_rank = _int(home.get("rank")), _int(away.get("rank"))
        if h_rank is not None and a_rank is not None:
            return "preTop"
        if any(_int(t.get("rank")) is not None and _record(t)[1] == 0 and (_record(t)[0] or 0) >= 4 for t in (home, away)):
            return "preUnbeaten"
        local = _kickoff(game, tz)
        if local is not None and (local.hour >= LATE_HOUR or local.hour < EARLY_HOUR):
            return "preLate"
        return "pre"
    h_pts, a_pts = scores
    if h_pts == a_pts:
        return "handles"  # college games have no ties; a malformed final still gets a plain line
    winner, loser = (home, away) if h_pts > a_pts else (away, home)
    high, low = max(h_pts, a_pts), min(h_pts, a_pts)
    margin = high - low
    w_rank, l_rank = _int(winner.get("rank")), _int(loser.get("rank"))
    if w_rank is None and l_rank is not None:
        return "finalUpset"
    if w_rank is not None and l_rank is not None and w_rank > l_rank + 5:
        return "finalShakeup"
    if _overtimes(game):
        return "overtime"
    if high + low >= 80 and margin <= 14:
        return "shootout"
    if _record(loser)[0] == 0 and (_record(loser)[1] or 0) >= WINLESS_AFTER:
        return "winless"
    if high >= 60:
        return "bigNumber"
    if margin >= 28:
        return "rout"
    if margin <= 3:
        return "escape"
    return "handles"


def _values(game: dict[str, Any], kind: str, *, us: str | None, tz: tzinfo) -> dict[str, str]:
    home, away = _side(game, "home"), _side(game, "away")
    neutral = game.get("neutralSite") is True
    local = _kickoff(game, tz)
    values: dict[str, str] = {
        "NB": NBSP,
        "AW": ranked_name(away),
        "HM": ranked_name(home),
        "VISITS": "meets" if neutral else "visits",
        "TIME": _time_text(local) if local else "TBD",
        "WHEN": f"at {_time_text(local)}" if local else "this week",
    }
    if kind.startswith("us"):
        mine = home if home.get("school") == us or (us is None and game.get("isUs") is True) else away
        theirs = away if mine is home else home
        values.update(
            US=_word(mine.get("school")) or "TBD",
            USM=_word(mine.get("mascot")) or _word(mine.get("school")) or "team",
            OPP=ranked_name(theirs),
            OPPM=_word(theirs.get("mascot")) or _word(theirs.get("school")) or "visitors",
            A=str(_int(mine.get("points")) if _int(mine.get("points")) is not None else ""),
            B=str(_int(theirs.get("points")) if _int(theirs.get("points")) is not None else ""),
        )
        return values
    if kind.startswith("pre"):
        ranked = [t for t in (away, home) if _int(t.get("rank")) is not None]
        pick = min(ranked, key=lambda t: _int(t.get("rank")) or 99) if ranked else away
        if kind == "preUnbeaten":
            pick = next((t for t in (away, home) if _int(t.get("rank")) is not None and _record(t)[1] == 0), pick)
        other = home if pick is away else away
        if neutral:
            where = f"against {_word(other.get('school')) or 'TBD'}"
        elif pick is away:
            where = f"at {_word(home.get('school')) or 'TBD'}"
        else:
            where = f"at home against {_word(away.get('school')) or 'TBD'}"
        values.update(R=ranked_name(pick), X=ranked_name(pick), XW=str(_record(pick)[0] or 0), Y=where)
        return values
    scores = _scores(game) or (0, 0)
    winner, loser = (home, away) if scores[0] >= scores[1] else (away, home)
    overtimes = _overtimes(game)
    values.update(
        W=ranked_name(winner),
        L=ranked_name(loser),
        WS=_word(winner.get("school")) or "TBD",
        LS=_word(loser.get("school")) or "TBD",
        A=str(max(scores)),
        B=str(min(scores)),
        OT="overtime" if overtimes <= 1 else f"{overtimes} overtimes",
    )
    return values


_SPACES = re.compile(r"\s{2,}")


def _fill(template: str, values: dict[str, str]) -> str:
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), template)
    return _SPACES.sub(" ", text).strip()


def _start(game: dict[str, Any], kind: str) -> int:
    return zlib.crc32(f"{game.get('gameId')}:{kind}".encode()) % len(TEMPLATES[kind])


def write(game: Any, *, us: str | None, tz: tzinfo, used: set[str] | None = None) -> dict[str, str] | None:
    """The headline for one game, or None (a live game, a game without both teams, a final without its score)."""
    kind = kind_of(game, us=us, tz=tz)
    if kind is None:
        return None
    options = TEMPLATES[kind]
    start = _start(game, kind)
    order = [options[(start + i) % len(options)] for i in range(len(options))]
    template = next((t for t in order if used is None or t not in used), order[0])
    if used is not None:
        used.add(template)
    return {"kind": kind, "kicker": KICKERS[kind], "text": _fill(template, _values(game, kind, us=us, tz=tz))}


def write_all(games: list[Any], *, us: str | None, tz: tzinfo) -> list[dict[str, str] | None]:
    """Headlines for a page of games in their order, a template used once per page where its kind has another."""
    used: set[str] = set()
    return [write(g, us=us, tz=tz, used=used) for g in games]
