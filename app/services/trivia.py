"""Game-day trivia: the session, the master file and the scores (owner 2026-10-21, the two things).

Only the tablets that joined see any of it. A tablet joins with a team name (case sensitive: "Couch Coordinators" and
"couch coordinators" are two teams), once per game day, from the note at the top of the page or the Trivia page. The host
keeps the master file, data/trivia.json, with every team's name, the days it played and every answer, so a team that
joins again in a later week gets its season score back.

A day runs from the first join until the host ends it, until no tablet has answered the last three questions (the room
went home), or until it is eighteen hours old. Before our kickoff and after the final a question every `triviaPace`
minutes (15 or 30; "game" asks only during the game) about the teams in the games on then, from the ticker, and ours;
during our game one a quarter, at the first look after the quarter's eight-minute mark, never in the last two minutes of
a half, about the two schools playing. A question stays open forty seconds; the answer never shows in the popup, only on
the Trivia page. Every tablet gets the same question at the same moment, because the server builds and stores it.

    TriviaService(data_dir, season, tz, clock, prefs, facts, live, our_team)
      .join(name, now) / .leave(name) / .rename(name, new_name) / .answer(name, question_id, choice, now)
      .end_day(now, by) / .mark(question_id, note, now)
      await .tick(now, games_on)      opens the next question when one is due (games_on: the ticker's games, awaited
                                      only when a question outside our game needs the teams on)
      .now_for(name, now)             what the popups show: the open question (no answer), the standings, the welcome
      .page_for(name, now, is_host)   the Trivia page

The file is written whole on every change (atomic). A damaged file is set aside and the trivia starts fresh; nothing
here raises past a TriviaError for a bad request."""

from __future__ import annotations

import json
import logging
import random
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write
from app.services.trivia_questions import pick_question

log = logging.getLogger("kickoff.trivia")

FORMAT = 1
OPEN_SECONDS = 40
QUIET_AFTER = 3  # unanswered questions in a row that end the day: the room went home
DAY_HOURS = 18  # a day started this long ago is over
QUARTER_MARK = 8 * 60
HALF_END = 2 * 60
NAME_MAX = 40
PACE_MINUTES = {"15": 15, "30": 30, "game": None}
STANDINGS_ROWS = 6
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class TriviaError(ValueError):
    """A bad request: an empty or taken name, a question that is closed, a team that never joined."""


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def clean_name(value: Any) -> str:
    """A team name as typed, ends trimmed, inner runs of spaces kept to one; case kept. Empty, too long or with control
    characters is refused."""
    if not isinstance(value, str):
        raise TriviaError("A team name is text.")
    name = re.sub(r"\s+", " ", _CONTROL.sub("", value)).strip()
    if not name:
        raise TriviaError("Type a team name.")
    if len(name) > NAME_MAX:
        raise TriviaError(f"A team name is {NAME_MAX} characters at most.")
    return name


class TriviaService:
    def __init__(
        self,
        data_dir: Path,
        season: int,
        tz: tzinfo,
        clock: Callable[[], datetime],
        prefs: Any,
        facts: Callable[[], dict[str, dict[str, Any]]],
        live: Any = None,
        our_team: str = "",
        on_mark: Callable[[str, str, str, str, str], None] | None = None,
    ) -> None:
        self.path = Path(data_dir) / "trivia.json"
        self.season = int(season)
        self.tz = tz
        self.clock = clock
        self.prefs = prefs
        self.facts = facts
        self.live = live
        self.our_team = our_team
        self.on_mark = on_mark
        self._data: dict[str, Any] | None = None

    # --- the file -------------------------------------------------------------------------------------------------

    def _fresh(self) -> dict[str, Any]:
        return {"format": FORMAT, "season": self.season, "teams": {}, "days": {}, "marks": []}

    @property
    def data(self) -> dict[str, Any]:
        if self._data is None:
            self._data = self._load()
        return self._data

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._fresh()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            aside = self.path.with_name(f"trivia.bad-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
            log.error("The trivia file could not be read (%s); it is set aside as %s and the trivia starts fresh", exc, aside.name)
            try:
                self.path.replace(aside)
            except OSError:
                log.warning("The damaged trivia file could not be moved", exc_info=True)
            return self._fresh()
        if not isinstance(raw, dict):
            log.error("The trivia file is not an object; the trivia starts fresh")
            return self._fresh()
        if _int(raw.get("season")) != self.season:
            aside = self.path.with_name(f"trivia-{raw.get('season')}.json")
            log.info("The trivia file is from season %s; kept as %s, a new one starts", raw.get("season"), aside.name)
            try:
                self.path.replace(aside)
            except OSError:
                log.warning("Last season's trivia file could not be moved", exc_info=True)
            return self._fresh()
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        days = raw.get("days") if isinstance(raw.get("days"), dict) else {}
        marks = raw.get("marks") if isinstance(raw.get("marks"), list) else []
        return {
            "format": FORMAT,
            "season": self.season,
            "teams": {k: v for k, v in teams.items() if isinstance(k, str) and isinstance(v, dict)},
            "days": {k: v for k, v in days.items() if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("questions"), list)},
            "marks": [m for m in marks if isinstance(m, dict)],
        }

    def _save(self) -> None:
        try:
            atomic_write(self.path, json.dumps(self.data, indent=1, ensure_ascii=False) + "\n")
        except OSError:
            log.error("The trivia file could not be written to %s", self.path, exc_info=True)

    # --- settings, the day, our game ------------------------------------------------------------------------------

    def settings(self) -> dict[str, Any]:
        p = getattr(self.prefs, "prefs", None)
        return {"on": bool(getattr(p, "trivia", True)), "board": bool(getattr(p, "triviaBoard", True)), "pace": str(getattr(p, "triviaPace", "15"))}

    def _delay(self) -> float:
        p = getattr(self.prefs, "prefs", None)
        try:
            return float(getattr(p, "delaySeconds", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def today(self, now: datetime) -> date:
        return now.astimezone(self.tz).date()

    def our_game(self, now: datetime) -> dict[str, Any] | None:
        """Our game of this day from the live engine's window: {gameId, home, away, kickoff, opponent} or None."""
        window = getattr(self.live, "window", None)
        kickoff = getattr(window, "kickoff", None)
        if window is None or not isinstance(kickoff, datetime):
            return None
        if kickoff.astimezone(self.tz).date() != self.today(now):
            return None
        home, away = getattr(window, "home", None), getattr(window, "away", None)
        opponent = away if home == self.our_team else home if away == self.our_team else None
        return {"gameId": getattr(window, "game_id", None), "home": home, "away": away, "kickoff": _iso(kickoff), "opponent": opponent}

    def game_day(self, now: datetime) -> bool:
        return self.our_game(now) is not None

    def _live_state(self) -> dict[str, Any] | None:
        state = getattr(self.live, "state", None)
        if not callable(state):
            return None
        try:
            out = state(self._delay())
        except Exception:  # noqa: BLE001 - the live engine's trouble is logged there; the trivia asks outside the game then
            log.warning("The live state could not be read for the trivia", exc_info=True)
            return None
        return out if isinstance(out, dict) else None

    def current_day(self, now: datetime) -> tuple[str, dict[str, Any]] | None:
        """The day running now: the newest without an end, started within DAY_HOURS. An older one left open is closed."""
        changed = False
        found = None
        for key, day in sorted(self.data["days"].items()):
            if day.get("endedAt"):
                continue
            started = _when(day.get("startedAt"))
            if started is None or now - started > timedelta(hours=DAY_HOURS):
                day["endedAt"] = _iso((started or now) + timedelta(hours=DAY_HOURS)) if started else _iso(now)
                day["endedBy"] = "night"
                changed = True
                continue
            found = (key, day)
        if changed:
            self._save()
        return found

    def _start_day(self, now: datetime) -> tuple[str, dict[str, Any]]:
        key = self.today(now).isoformat()
        day = self.data["days"].get(key)
        if day is None or not isinstance(day.get("questions"), list):
            day = {"startedAt": _iso(now), "endedAt": None, "endedBy": None, "our": self.our_game(now), "questions": [], "periods": [], "quiet": 0}
            self.data["days"][key] = day
        else:  # the host ended it and a tablet joins again: the day goes on
            day["endedAt"], day["endedBy"] = None, None
        return key, day

    # --- teams -------------------------------------------------------------------------------------------------------

    def _team(self, name: str) -> dict[str, Any]:
        team = self.data["teams"].get(name)
        if not isinstance(team, dict):
            raise TriviaError("That team has not joined.")
        team.setdefault("days", {})
        team.setdefault("answers", {})
        return team

    def _season_score(self, team: dict[str, Any], now: datetime, before: str | None = None) -> tuple[int, int]:
        right = asked = 0
        for key, day in self.data["days"].items():
            if before and key >= before:
                continue
            r, a = self._day_score(key, day, team, now)
            right, asked = right + r, asked + a
        return right, asked

    def _day_score(self, key: str, day: dict[str, Any], team: dict[str, Any], now: datetime) -> tuple[int, int]:
        """(right, asked) for one day: the questions that closed after the team joined that day."""
        joined = _when((team.get("days") or {}).get(key, {}).get("joinedAt")) if isinstance(team.get("days"), dict) else None
        if joined is None:
            return 0, 0
        answers = team.get("answers") if isinstance(team.get("answers"), dict) else {}
        right = asked = 0
        for q in day.get("questions") or []:
            asked_at, closes = _when(q.get("askedAt")), _when(q.get("closesAt"))
            if asked_at is None or closes is None or asked_at < joined or closes > now:
                continue
            asked += 1
            if answers.get(q.get("id")) == q.get("answer"):
                right += 1
        return right, asked

    def _best_day(self, team: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        best = None
        for key, day in self.data["days"].items():
            r, a = self._day_score(key, day, team, now)
            if a and (best is None or (r, -a) > (best["right"], -best["asked"])):
                best = {"date": key, "right": r, "asked": a, "our": day.get("our")}
        return best

    def join(self, name: Any, now: datetime) -> dict[str, Any]:
        """Join today (starting the day if none runs) as `name`; a team that played before gets its season score back."""
        name = clean_name(name)
        teams = self.data["teams"]
        team = teams.get(name)
        new = not isinstance(team, dict)
        if new:
            team = {"firstDay": self.today(now).isoformat(), "hidden": False, "days": {}, "answers": {}}
            teams[name] = team
        team.setdefault("days", {})
        team.setdefault("answers", {})
        team["hidden"] = False
        key, day = self.current_day(now) or self._start_day(now)
        if key not in team["days"]:
            team["days"][key] = {"joinedAt": _iso(now)}
        before = self._season_score(team, now, before=key)
        self._save()
        welcome = f"Welcome back, {name}: {before[0]} of {before[1]} this season before today" if not new and before[1] else None
        return {"name": name, "new": new, "day": key, "welcome": welcome, "seasonBefore": list(before)}

    def leave(self, name: Any) -> dict[str, Any]:
        """Leave the board: the team's answers stay, its name stops showing until it joins again."""
        team = self._team(clean_name(name))
        team["hidden"] = True
        self._save()
        return {"name": clean_name(name), "hidden": True}

    def rename(self, name: Any, new_name: Any) -> dict[str, Any]:
        old, new = clean_name(name), clean_name(new_name)
        team = self._team(old)
        if new != old and new in self.data["teams"]:
            raise TriviaError("That team name is taken.")
        if new != old:
            del self.data["teams"][old]
            self.data["teams"][new] = team
            self._save()
        return {"name": new, "was": old}

    def answer(self, name: Any, question_id: Any, choice: Any, now: datetime) -> dict[str, Any]:
        """A pick on the open question; a later pick while it is open replaces the first. The answer is not revealed."""
        team = self._team(clean_name(name))
        found = self.current_day(now)
        if found is None:
            raise TriviaError("No trivia is running.")
        key, day = found
        if key not in team["days"]:
            raise TriviaError("That team has not joined today.")
        question = next((q for q in day["questions"] if q.get("id") == question_id), None)
        if question is None:
            raise TriviaError("That question is not today's.")
        closes = _when(question.get("closesAt"))
        if closes is None or now > closes:
            raise TriviaError("That question has closed.")
        index = _int(choice)
        if index is None or not 0 <= index < len(question.get("choices") or []):
            raise TriviaError("Pick A, B or C.")
        team["answers"][question_id] = index
        self._save()
        return {"questionId": question_id, "choice": index, "closesAt": question["closesAt"]}

    def end_day(self, now: datetime, by: str = "host") -> dict[str, Any] | None:
        found = self.current_day(now)
        if found is None:
            return None
        key, day = found
        day["endedAt"], day["endedBy"] = _iso(now), by
        self._save()
        return {"date": key, "endedAt": day["endedAt"], "endedBy": by}

    def mark(self, question_id: Any, note: Any, now: datetime) -> dict[str, Any]:
        """"Wrong? mark it": a note against the question's fact, kept here and handed to the facts file."""
        question = None
        for day in self.data["days"].values():
            question = next((q for q in day.get("questions") or [] if q.get("id") == question_id), None)
            if question:
                break
        if question is None:
            raise TriviaError("That question is not known.")
        text = re.sub(r"\s+", " ", _CONTROL.sub("", note)).strip()[:300] if isinstance(note, str) else ""
        mark = {"questionId": question_id, "school": question.get("school"), "kind": question.get("kind"), "question": question.get("text"), "fact": question.get("fact"), "note": text, "at": _iso(now)}
        self.data["marks"] = [m for m in self.data["marks"] if m.get("questionId") != question_id] + [mark]
        question["marked"] = True
        self._save()
        if self.on_mark is not None:
            try:
                self.on_mark(str(question.get("school") or ""), str(question.get("kind") or ""), text, str(question.get("text") or ""), mark["at"])
            except Exception:  # noqa: BLE001 - the facts file's trouble is its own; the mark is kept here regardless
                log.warning("The trivia mark could not be written to the facts file", exc_info=True)
        return mark

    # --- the clock: when the next question comes ---------------------------------------------------------------------

    def _open_question(self, day: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        last = day["questions"][-1] if day.get("questions") else None
        closes = _when(last.get("closesAt")) if last else None
        return last if last and closes and now <= closes else None

    def _tally_closed(self, day: dict[str, Any], now: datetime) -> bool:
        """Count a closed question's answers once: three in a row with none end the day."""
        changed = False
        for q in day.get("questions") or []:
            closes = _when(q.get("closesAt"))
            if q.get("tallied") or closes is None or now <= closes:
                continue
            answered = sum(1 for t in self.data["teams"].values() if isinstance(t.get("answers"), dict) and q.get("id") in t["answers"])
            q["tallied"], q["answered"] = True, answered
            day["quiet"] = 0 if answered else int(day.get("quiet") or 0) + 1
            changed = True
            if day["quiet"] >= QUIET_AFTER and not day.get("endedAt"):
                day["endedAt"], day["endedBy"] = _iso(now), "quiet"
                log.info("The trivia day ended on its own: %d questions in a row went unanswered", QUIET_AFTER)
        return changed

    def _game_context(self, now: datetime) -> tuple[str, dict[str, Any] | None]:
        """("game", state) while our game is in progress today, else ("pre"|"post"|"off", state or None)."""
        our = self.our_game(now)
        if our is None:
            return "off", None
        state = self._live_state()
        status = state.get("status") if state else None
        if status == "in_progress":
            return "game", state
        if status == "final":
            return "post", state
        kickoff = _when(our.get("kickoff"))
        return ("post" if kickoff and now > kickoff + timedelta(hours=5) else "pre"), state

    @staticmethod
    def _clock_left(state: dict[str, Any] | None) -> tuple[int | None, int | None]:
        if not state:
            return None, None
        period = _int(state.get("period"))
        clock = state.get("clock") if isinstance(state.get("clock"), dict) else {}
        left = (_int(clock.get("minutes")) or 0) * 60 + (_int(clock.get("seconds")) or 0)
        return period, left

    def _game_due(self, day: dict[str, Any], state: dict[str, Any] | None) -> int | None:
        """The quarter a question is due in during our game: once a quarter, after the eight-minute mark, never in
        the last two minutes of a half; None when none is due."""
        period, left = self._clock_left(state)
        if period is None or left is None or not 1 <= period <= 4 or period in (day.get("periods") or []):
            return None
        if left > QUARTER_MARK or (period in (2, 4) and left < HALF_END):
            return None
        return period

    def _pace_due(self, day: dict[str, Any], now: datetime) -> bool:
        minutes = PACE_MINUTES.get(self.settings()["pace"], 15)
        if minutes is None:
            return False
        questions = day.get("questions") or []
        if not questions:
            return True
        last = _when(questions[-1].get("askedAt"))
        return last is None or now - last >= timedelta(minutes=minutes)

    def next_text(self, day: dict[str, Any], now: datetime, context: str, state: dict[str, Any] | None) -> str:
        if day.get("endedAt"):
            return "Ended for today"
        if context == "game":
            period, left = self._clock_left(state)
            if period and 1 <= period <= 4 and period not in (day.get("periods") or []) and left is not None and left > QUARTER_MARK:
                return f"Next at the {['1st', '2nd', '3rd', '4th'][period - 1]} quarter's eight-minute mark"
            if period and period < 4:
                return f"Next in the {['2nd', '3rd', '4th'][period - 1]} quarter"
            return "Next after the game" if PACE_MINUTES.get(self.settings()["pace"], 15) else "No more tonight"
        minutes = PACE_MINUTES.get(self.settings()["pace"], 15)
        if minutes is None:
            return "Next during our game"
        questions = day.get("questions") or []
        last = _when(questions[-1].get("askedAt")) if questions else None
        at = (last + timedelta(minutes=minutes)) if last else now
        return f"Next at {at.astimezone(self.tz).strftime('%I:%M %p').lstrip('0').lower()}" if at > now else "Next any moment"

    def _schools_for(self, context: str, now: datetime, games_on: list[dict[str, Any]] | None) -> list[str]:
        rows = self.facts() or {}
        our = self.our_game(now) or {}
        names: list[str] = []
        for s in (our.get("home"), our.get("away"), self.our_team):
            if isinstance(s, str) and s in rows and s not in names:
                names.append(s)
        if context == "game":
            return names
        for g in games_on or []:
            if not isinstance(g, dict) or g.get("status") not in ("in_progress", "halftime"):
                continue
            for side in ("home", "away"):
                school = (g.get(side) or {}).get("school") if isinstance(g.get(side), dict) else None
                if isinstance(school, str) and school in rows and school not in names:
                    names.append(school)
        if names:
            return names
        ours = rows.get(self.our_team) if isinstance(rows.get(self.our_team), dict) else {}
        conference = ours.get("conference")
        same = [s for s, r in rows.items() if isinstance(s, str) and isinstance(r, dict) and conference and r.get("conference") == conference]
        return same or [s for s in rows if isinstance(s, str)]

    async def tick(self, now: datetime, games_on: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None) -> None:
        """Open the next question when one is due. Cheap when nothing is: a few dictionary looks."""
        found = self.current_day(now)
        if found is None or not self.settings()["on"]:
            return
        key, day = found
        changed = self._tally_closed(day, now)
        if day.get("endedAt") or self._open_question(day, now) is not None:
            if changed:
                self._save()
            return
        context, state = self._game_context(now)
        period = self._game_due(day, state) if context == "game" else None
        due = period is not None if context == "game" else self._pace_due(day, now)
        if not due:
            if changed:
                self._save()
            return
        games: list[dict[str, Any]] | None = None
        if context != "game" and games_on is not None:
            try:
                games = await games_on()
            except Exception:  # noqa: BLE001 - the ticker's trouble is logged there; the question is about our teams then
                log.warning("The ticker could not be read for the trivia's games on", exc_info=True)
        n = len(day["questions"]) + 1
        qid = f"{key}-{n}"
        rng = random.Random(f"{self.season}:{qid}")
        question = pick_question(self.facts() or {}, self._schools_for(context, now, games), day["questions"], rng, qid, self.today(now))
        if question is None:
            if context == "game" and period is not None:
                day.setdefault("periods", []).append(period)  # nothing to ask about these two schools this quarter
            log.info("No trivia question could be built (%s); the facts are used up for today", context)
            self._save()
            return
        record = {**question.as_dict(), "n": n, "askedAt": _iso(now), "closesAt": _iso(now + timedelta(seconds=OPEN_SECONDS)), "context": context, "period": period, "tallied": False, "answered": 0}
        day["questions"].append(record)
        if period is not None:
            day.setdefault("periods", []).append(period)
        self._save()

    # --- what the pages read ------------------------------------------------------------------------------------------

    def _standings(self, key: str, day: dict[str, Any], now: datetime, you: str | None) -> list[dict[str, Any]]:
        rows = []
        for name, team in self.data["teams"].items():
            if team.get("hidden") or not isinstance(team.get("days"), dict) or key not in team["days"]:
                continue
            today = self._day_score(key, day, team, now)
            rows.append({"name": name, "today": list(today), "season": list(self._season_score(team, now)), "you": name == you, "joinedAt": team["days"][key].get("joinedAt")})
        rows.sort(key=lambda r: (-r["today"][0], r["today"][1], -r["season"][0], r["name"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        return rows

    def _question_view(self, q: dict[str, Any], now: datetime, team: dict[str, Any] | None, reveal: bool) -> dict[str, Any]:
        closes = _when(q.get("closesAt"))
        out = {k: q.get(k) for k in ("id", "n", "kind", "school", "text", "choices", "askedAt", "closesAt", "context", "period", "checkedAt")}
        out["secondsLeft"] = max(0, int((closes - now).total_seconds())) if closes else 0
        out["open"] = bool(closes and now <= closes)
        out["yourPick"] = (team.get("answers") or {}).get(q.get("id")) if team else None
        if reveal:
            out["answer"], out["fact"], out["answered"], out["marked"] = q.get("answer"), q.get("fact"), q.get("answered"), bool(q.get("marked"))
        return out

    def now_for(self, name: Any, now: datetime) -> dict[str, Any]:
        """What the popups show on one tablet: the open question without its answer, the standings, the welcome."""
        settings = self.settings()
        you = None
        try:
            you = clean_name(name) if name else None
        except TriviaError:
            you = None
        team = self.data["teams"].get(you) if you else None
        team = team if isinstance(team, dict) else None
        found = self.current_day(now)
        today_key = self.today(now).isoformat()
        key, day = found if found else ((today_key, self.data["days"][today_key]) if today_key in self.data["days"] else (None, None))  # an ended day still shows as today's
        joined = bool(team is not None and isinstance(team.get("days"), dict) and key and key in team["days"] and not team.get("hidden"))
        context, state = self._game_context(now) if day else ("off", None)
        open_q = self._open_question(day, now) if day else None
        out: dict[str, Any] = {
            **settings,
            "gameDay": self.game_day(now),
            "ourGame": self.our_game(now),
            "serverNow": _iso(now),
            "day": {"date": key, "startedAt": day.get("startedAt"), "endedAt": day.get("endedAt"), "endedBy": day.get("endedBy"), "asked": len(day.get("questions") or []), "playing": sum(1 for t in self.data["teams"].values() if not t.get("hidden") and isinstance(t.get("days"), dict) and key in t["days"]), "next": self.next_text(day, now, context, state), "context": context} if day else None,
            "team": {"name": you, "joined": joined, "hidden": bool(team.get("hidden")), "firstDay": team.get("firstDay"), "today": list(self._day_score(key, day, team, now)) if day else [0, 0], "season": list(self._season_score(team, now))} if team is not None and you else None,
            "question": self._question_view(open_q, now, team, reveal=False) if open_q and joined and settings["on"] else None,
            "standings": self._standings(key, day, now, you)[:STANDINGS_ROWS] if day and settings["board"] else [],
        }
        return out

    def page_for(self, name: Any, now: datetime, is_host: bool = False) -> dict[str, Any]:
        """The Trivia page: today's questions with the answers, the scores, the leaderboard, the season table."""
        base = self.now_for(name, now)
        you = base["team"]["name"] if base.get("team") else None
        team = self.data["teams"].get(you) if you else None
        team = team if isinstance(team, dict) else None
        today_key = self.today(now).isoformat()
        found = self.current_day(now)
        shown_key, shown = found if found else ((today_key, self.data["days"][today_key]) if today_key in self.data["days"] else (None, None))
        questions = [self._question_view(q, now, team, reveal=not q.get("open", False) and now > (_when(q.get("closesAt")) or now)) for q in (shown.get("questions") or [])] if shown else []
        board = []
        for n, t in self.data["teams"].items():
            if t.get("hidden") or not isinstance(t.get("days"), dict):
                continue
            today = list(self._day_score(shown_key, shown, t, now)) if shown and shown_key in t["days"] else None
            board.append({"name": n, "today": today, "season": list(self._season_score(t, now)), "you": n == you, "firstDay": t.get("firstDay"), "here": today is not None})
        board.sort(key=lambda r: (not r["here"], -(r["today"][0] if r["today"] else 0), (r["today"][1] if r["today"] else 0), -r["season"][0], r["name"]))
        for i, r in enumerate(board, 1):
            r["rank"] = i
        season_table = []
        if team and isinstance(team.get("days"), dict):
            for k, d in sorted(self.data["days"].items()):
                if k not in team["days"]:
                    continue
                started, ended = _when(d.get("startedAt")), _when(d.get("endedAt"))
                r, a = self._day_score(k, d, team, now)
                season_table.append({"date": k, "our": d.get("our"), "startedAt": d.get("startedAt"), "endedAt": d.get("endedAt"), "span": self._span(started, ended), "right": r, "asked": a, "running": not d.get("endedAt")})
        return {
            **base,
            "isHost": bool(is_host),
            "questions": questions,
            "board": board,
            "best": self._best_day(team, now) if team else None,
            "seasonTable": season_table,
            "marks": [m for m in self.data["marks"] if shown and str(m.get("questionId", "")).startswith(shown_key or "\0")],
            "teamsThisSeason": sum(1 for t in self.data["teams"].values() if not t.get("hidden")),
        }

    def _span(self, started: datetime | None, ended: datetime | None) -> str | None:
        if started is None:
            return None
        fmt = lambda m: m.astimezone(self.tz).strftime("%I:%M %p").lstrip("0").lower()  # noqa: E731
        return f"{fmt(started)} to {fmt(ended)}" if ended else f"since {fmt(started)}"
