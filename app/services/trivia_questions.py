"""Trivia questions from the schools' facts (the trivia, owner 2026-10-21).

Every question is built from one school's facts (app/services/season_notes.py, the shipped file under the install's own)
with three choices, one right: the stadium, the year it opened, who founded the school when, the seats, the mascot's
name, the fight song, the trophy of a rivalry, a Heisman winner, a national title year, the winningest coach, the
longest win streak, the record crowd, a retired number, a dated event, the first season, the year the school joined its
conference. The wrong choices are other schools' facts of the same kind (a stadium, a mascot, a trophy) or nearby
numbers (a year, a crowd), so they read as real. A fact the school lacks builds no question of that kind; a school with
no usable fact builds none, and the caller moves on.

    pick_question(rows, schools, asked, rng, qid)   one new question for one of the schools, or None
    make_question(rows, school, avoid, rng, qid)    one for that school, kinds in `avoid` skipped, or None
    KINDS                                           every kind, in the order a fresh day tries them

Nothing here guesses: a fact that does not parse (a Heisman line without a year, a streak without a number) is skipped.
Deterministic for a seeded Random, so every tablet gets the same question the server stored."""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

KINDS = ("trophy", "stadium", "mascotName", "fightSong", "stadiumOpened", "founded", "capacity", "heisman", "nationalTitle", "winningestCoach", "longestWinStreak", "recordCrowd", "retiredNumber", "date", "firstSeason", "conferenceSince")
MIN_YEAR = 1600
YEAR_OFFSETS = (3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 17, 21, 24)
_NUMBER = re.compile(r"\d[\d,]*")
_CAP = [date.today().year]  # the latest year a choice may name; pick_question and make_question set it from `today`
_YEAR = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")


@dataclass
class Question:
    id: str
    kind: str
    school: str
    text: str
    choices: list[str]
    answer: int
    fact: str
    checkedAt: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _first_number(value: Any) -> int | None:
    """The first number in a line ("90,916 vs Rival U, 2015-11-28" -> 90916; "22 games (2008 to 2009)" -> 22)."""
    text = _str(value)
    if not text:
        return None
    found = _NUMBER.search(text)
    try:
        return int(found.group(0).replace(",", "")) if found else None
    except ValueError:
        return None


def _name_before_comma(value: Any) -> str | None:
    """"Steve Spurrier, 122 wins (1990 to 2001)" -> "Steve Spurrier"; "Tim Tebow (2007)" -> "Tim Tebow"."""
    text = _str(value)
    if not text:
        return None
    name = re.split(r"[,(]", text, maxsplit=1)[0].strip()
    return name if 2 <= len(name) <= 60 else None


def _year_in(value: Any) -> int | None:
    text = _str(value)
    found = _YEAR.search(text) if text else None
    return int(found.group(1)) if found else None


def _year_choices(right: int, rng: random.Random, taken: set[int] | None = None, cap: int | None = None) -> list[int] | None:
    """Two other years near the right one, never one the school could also claim (`taken`), never one still to come."""
    cap = cap or _CAP[0]
    out: list[int] = []
    offsets = list(YEAR_OFFSETS)
    rng.shuffle(offsets)
    for offset in offsets:
        for sign in rng.sample((1, -1), 2):
            year = right + sign * offset
            if MIN_YEAR <= year <= cap and year != right and year not in out and year not in (taken or set()):
                out.append(year)
                if len(out) == 2:
                    return out
    return None


def _count_choices(right: int, rng: random.Random, low: float = 0.06, high: float = 0.3, step: int = 100) -> list[int] | None:
    """Two other counts within a few percent either side, rounded the way a stadium's seats are."""
    out: list[int] = []
    for _ in range(40):
        factor = 1 + rng.choice((1, -1)) * rng.uniform(low, high)
        value = int(round(right * factor / step) * step)
        if value > 0 and value != right and value not in out and abs(value - right) >= step:
            out.append(value)
            if len(out) == 2:
                return out
    return None


def _small_choices(right: int, rng: random.Random, span: tuple[int, int] = (2, 9)) -> list[int] | None:
    out: list[int] = []
    for _ in range(40):
        value = right + rng.choice((1, -1)) * rng.randint(*span)
        if value > 0 and value != right and value not in out:
            out.append(value)
            if len(out) == 2:
                return out
    return None


def _others(rows: dict[str, dict[str, Any]], school: str, take: Any, rng: random.Random, own: set[str]) -> list[str] | None:
    """Two other schools' values of the same kind, distinct from the school's own and from each other."""
    pool: list[str] = []
    for other, row in rows.items():
        if other == school or not isinstance(row, dict):
            continue
        for value in take(row):
            if value and value not in own and value not in pool:
                pool.append(value)
    if len(pool) < 2:
        return None
    return rng.sample(pool, 2)


def _fmt(n: int) -> str:
    return f"{n:,}"


# --- one builder per kind: (text, right answer, decoys, the fact line) or None ----------------------------------------


def _b_stadium(rows, school, row, rng):
    stadium = _str(row.get("stadium"))
    if not stadium:
        return None
    decoys = _others(rows, school, lambda r: [_str(r.get("stadium"))], rng, {stadium})
    if not decoys:
        return None
    opened = _int(row.get("stadiumOpened"))
    seats = _int(row.get("capacity"))
    nick = _str(row.get("stadiumNickname"))
    fact = f"{school} plays at {stadium}" + (f", {nick}," if nick else "") + (f" opened {opened}" if opened else "") + (f", {_fmt(seats)} seats" if seats else "") + "."
    return f"Where does {school} play its home games?", stadium, decoys, fact


def _b_mascot(rows, school, row, rng):
    name = _str(row.get("mascotName"))
    if not name:
        return None
    decoys = _others(rows, school, lambda r: [_str(r.get("mascotName"))], rng, {name})
    if not decoys:
        return None
    origin = _str(row.get("mascotOrigin"))
    return f"What is {school}'s mascot called?", name, decoys, f"{name}." + (f" {origin}" if origin else "")


def _b_fight_song(rows, school, row, rng):
    song = _str(row.get("fightSong"))
    if not song:
        return None
    decoys = _others(rows, school, lambda r: [_str(r.get("fightSong"))], rng, {song})
    if not decoys:
        return None
    return f"What is {school}'s fight song?", song, decoys, f"{school}'s fight song is {song}."


def _b_trophy(rows, school, row, rng):
    rivalries = [r for r in (row.get("rivalries") or []) if isinstance(r, dict) and _str(r.get("rival")) and _str(r.get("trophy"))] if isinstance(row.get("rivalries"), list) else []
    if not rivalries:
        return None
    rivalry = rng.choice(rivalries)
    trophy, rival = rivalry["trophy"].strip(), rivalry["rival"].strip()
    own = {r["trophy"].strip() for r in rivalries}

    def take(r):
        return [x.get("trophy").strip() for x in (r.get("rivalries") or []) if isinstance(x, dict) and _str(x.get("trophy"))] if isinstance(r.get("rivalries"), list) else []

    decoys = _others(rows, school, take, rng, own)
    if not decoys:
        return None
    since = _int(rivalry.get("firstMeeting"))
    record = _str(rivalry.get("record"))
    fact = f"{trophy}" + (f", since {since}" if since else "") + (f"; the series stands {record}" if record else "") + "."
    return f"Which trophy do {school} and {rival} play for?", trophy, decoys, fact


def _b_stadium_opened(rows, school, row, rng):
    stadium, opened = _str(row.get("stadium")), _int(row.get("stadiumOpened"))
    if not stadium or not opened or opened < MIN_YEAR:
        return None
    decoys = _year_choices(opened, rng)
    if not decoys:
        return None
    seats = _int(row.get("capacity"))
    return f"In what year did {stadium}, {school}'s stadium, open?", str(opened), [str(d) for d in decoys], f"{stadium} opened in {opened}" + (f"; it seats {_fmt(seats)} today" if seats else "") + "."


def _b_founded(rows, school, row, rng):
    founded = _int(row.get("founded"))
    if not founded or founded < MIN_YEAR:
        return None
    decoys = _year_choices(founded, rng)
    if not decoys:
        return None
    first = _int(row.get("firstSeason"))
    return f"In what year was {school} founded?", str(founded), [str(d) for d in decoys], f"{school} was founded in {founded}" + (f"; its first football season came in {first}" if first else "") + "."


def _b_capacity(rows, school, row, rng):
    stadium, seats = _str(row.get("stadium")), _int(row.get("capacity"))
    if not stadium or not seats or seats < 1000:
        return None
    decoys = _count_choices(seats, rng)
    if not decoys:
        return None
    return f"How many does {stadium}, {school}'s stadium, seat?", _fmt(seats), [_fmt(d) for d in decoys], f"{stadium} seats {_fmt(seats)}."


def _b_heisman(rows, school, row, rng):
    lines = [h for h in (row.get("heismans") or []) if _name_before_comma(h) and _year_in(h)] if isinstance(row.get("heismans"), list) else []
    if not lines:
        return None
    line = rng.choice(lines)
    name, year = _name_before_comma(line), _year_in(line)
    own = {_name_before_comma(h) for h in lines}

    def take(r):
        return [_name_before_comma(h) for h in (r.get("heismans") or []) if _name_before_comma(h)] if isinstance(r.get("heismans"), list) else []

    decoys = _others(rows, school, take, rng, own)
    if not decoys:
        return None
    return f"Who won the Heisman Trophy for {school} in {year}?", name, decoys, f"{name}, {school}'s Heisman winner of {year}."


def _b_national_title(rows, school, row, rng):
    years = sorted({y for y in (row.get("nationalTitles") or []) if _int(y) and _int(y) >= MIN_YEAR}) if isinstance(row.get("nationalTitles"), list) else []
    if not years:
        return None
    year = rng.choice(years)
    decoys = _year_choices(year, rng, taken=set(years))
    if not decoys:
        return None
    listed = ", ".join(str(y) for y in years)
    return f"In which of these years did {school} win a national title?", str(year), [str(d) for d in decoys], f"{school}'s national titles: {listed}."


def _b_winningest(rows, school, row, rng):
    name = _name_before_comma(row.get("winningestCoach"))
    if not name:
        return None
    decoys = _others(rows, school, lambda r: [_name_before_comma(r.get("winningestCoach"))], rng, {name})
    if not decoys:
        return None
    return f"Who is {school}'s winningest coach?", name, decoys, f"{row['winningestCoach'].strip()}."


def _b_streak(rows, school, row, rng):
    games = _first_number(row.get("longestWinStreak"))
    if not games or games < 3:
        return None
    decoys = _small_choices(games, rng)
    if not decoys:
        return None
    return f"How long is {school}'s longest win streak?", f"{games} games", [f"{d} games" for d in decoys], f"{row['longestWinStreak'].strip()}."


def _b_record_crowd(rows, school, row, rng):
    crowd = _first_number(row.get("recordCrowd"))
    stadium = _str(row.get("stadium"))
    if not crowd or crowd < 1000 or not stadium:
        return None
    decoys = _count_choices(crowd, rng, low=0.03, high=0.12, step=1)
    if not decoys:
        return None
    return f"What is the record crowd at {stadium}?", _fmt(crowd), [_fmt(d) for d in decoys], f"{row['recordCrowd'].strip()}."


def _b_retired(rows, school, row, rng):
    pairs = []
    for line in row.get("retiredNumbers") or [] if isinstance(row.get("retiredNumbers"), list) else []:
        text = _str(line)
        found = re.search(r"\(?\s*No\.?\s*(\d{1,2})\s*\)?", text) if text else None
        name = _name_before_comma(text) if text else None
        if found and name:
            pairs.append((name, int(found.group(1))))
    if not pairs:
        return None
    name, number = rng.choice(pairs)
    own = {n for _, n in pairs}
    pool = sorted({n for n in range(0, 100) if n not in own and n != number})
    decoys = rng.sample(pool, 2)
    return f"Which number did {school} retire for {name}?", str(number), [str(d) for d in decoys], f"{school} retired No. {number} for {name}."


def _b_date(rows, school, row, rng):
    events = []
    for item in row.get("dates") or [] if isinstance(row.get("dates"), list) else []:
        if not isinstance(item, dict):
            continue
        year, event = _year_in(item.get("date")), _str(item.get("event"))
        if year and event and not _YEAR.search(event) and len(event) <= 200:
            events.append((year, event))
    if not events:
        return None
    year, event = rng.choice(events)
    decoys = _year_choices(year, rng)
    if not decoys:
        return None
    return f"In what year: {event}", str(year), [str(d) for d in decoys], f"{year}: {event}"


def _b_first_season(rows, school, row, rng):
    first = _int(row.get("firstSeason"))
    if not first or first < MIN_YEAR:
        return None
    decoys = _year_choices(first, rng)
    if not decoys:
        return None
    return f"In what year did {school} play its first football season?", str(first), [str(d) for d in decoys], f"{school}'s first season was {first}."


def _b_conference_since(rows, school, row, rng):
    since, conference = _int(row.get("conferenceSince")), _str(row.get("conference"))
    if not since or since < MIN_YEAR or not conference:
        return None
    decoys = _year_choices(since, rng)
    if not decoys:
        return None
    return f"Since what year has {school} been in the {conference}?", str(since), [str(d) for d in decoys], f"{school} joined the {conference} in {since}."


BUILDERS = {
    "trophy": _b_trophy, "stadium": _b_stadium, "mascotName": _b_mascot, "fightSong": _b_fight_song, "stadiumOpened": _b_stadium_opened,
    "founded": _b_founded, "capacity": _b_capacity, "heisman": _b_heisman, "nationalTitle": _b_national_title, "winningestCoach": _b_winningest,
    "longestWinStreak": _b_streak, "recordCrowd": _b_record_crowd, "retiredNumber": _b_retired, "date": _b_date, "firstSeason": _b_first_season,
    "conferenceSince": _b_conference_since,
}


def make_question(rows: dict[str, dict[str, Any]], school: str, avoid: set[str], rng: random.Random, qid: str, today: date | None = None) -> Question | None:
    """One question about `school`, of a kind not in `avoid`, the kinds tried in a shuffled order; None when its facts
    build nothing new. No choice names a year after `today`'s."""
    _CAP[0] = (today or date.today()).year
    row = rows.get(school) if isinstance(rows, dict) else None
    if not isinstance(row, dict):
        return None
    kinds = [k for k in KINDS if k not in avoid]
    rng.shuffle(kinds)
    for kind in kinds:
        try:
            built = BUILDERS[kind](rows, school, row, rng)
        except (AttributeError, TypeError, ValueError, KeyError):  # a malformed fact builds nothing; the next kind is tried
            built = None
        if not built:
            continue
        text, right, decoys, fact = built
        choices = [right, *decoys]
        if len(set(choices)) != 3:
            continue
        rng.shuffle(choices)
        checked = row.get("checkedAt") if isinstance(row.get("checkedAt"), str) else None
        return Question(id=qid, kind=kind, school=school, text=text, choices=choices, answer=choices.index(right), fact=fact, checkedAt=checked)
    return None


def pick_question(rows: dict[str, dict[str, Any]], schools: list[str], asked: list[dict[str, Any]], rng: random.Random, qid: str, today: date | None = None) -> Question | None:
    """A new question about one of `schools` (a shuffled order; the school asked about least today first), skipping the
    kinds already asked about that school today. None when every school is used up."""
    counts = {s: sum(1 for q in asked if isinstance(q, dict) and q.get("school") == s) for s in schools}
    order = [s for s in schools if isinstance(s, str) and s in rows]
    rng.shuffle(order)
    order.sort(key=lambda s: counts.get(s, 0))
    for school in order:
        avoid = {q.get("kind") for q in asked if isinstance(q, dict) and q.get("school") == school and isinstance(q.get("kind"), str)}
        question = make_question(rows, school, avoid, rng, qid, today)
        if question is not None:
            return question
    return None
