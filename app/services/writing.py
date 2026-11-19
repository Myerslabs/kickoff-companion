"""Claude Code writing for the app (P4, owner 2026-10-25: "I want claude cli to improve on itself every week, use the past
notes to improve the current notes", and Claude-written post-game pieces "Yes"). Each kind is one run of Claude Code on the
server, the same locked-down way as the notes (app/services/notes_task.py): the prompt arrives on stdin, web search is the
only tool, the tool answers with one JSON object, and the app reads it leniently and writes the file. The app never calls
an AI itself.

    KINDS                         review, recap, scout, paper, datacheck, trivia, editor, art, trip, picks: what each asks and how its answer reads
    build_prompt(kind, team, packet, so_far=None) -> str   so_far: the piece as it stands, for a refresh (batch 4)
    read(kind, text) -> (dict | None, warnings, error)
    WritingStore(data_dir, season)          data/season/<year>/writing/<kind>-<key>.json
    Lessons(data_dir)                       data/claude/lessons.json: what the weekly review learned, and the prompt's additions
    WritingRunner(data_dir, log_dir)        one run at a time; .start(job, command), .status(), .stop()

The weekly loop (FEAT-6): after our game the review run reads the notes it wrote against what happened (computed by the
app: who was listed out and played, who started on the chart and has no line, which parts came back empty) and answers with
a few lessons and, when a change to the notes prompt would fix a repeated miss, one addition with its reason. Lessons and
active additions go into every notes prompt after it (app/services/notes_paste.py learning_text); every addition is kept
with its reason and can be switched off (undone) or on again.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict

from app.cfbd.models import DropBad
from app.services import claude_signin
from app.services.answers import atomic_write, keys_score, read_json
from app.services.notes_task import ALLOWED_TOOLS, MAX_RUN_SECONDS, PROMPT_LEAD, NotesRunner, lockdown_args, scratch_dir

log = logging.getLogger("kickoff.writing")

MAX_ANSWER = 200_000
MAX_LESSONS = 12  # the newest lessons the notes prompt carries
MAX_LESSON_CHARS = 300
MAX_ADDITION_CHARS = 800
MAX_PACKET_CHARS = 60_000


# --- the answers ---------------------------------------------------------------------------------------------------


Strings = Annotated[list[str], DropBad]  # a list of lines: one that is not text is dropped, never the whole list


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Source(Model):
    label: str
    url: str | None = None


class ReviewAnswer(Model):
    lessons: Strings = []
    promptAddition: str | None = None
    reason: str | None = None


class RecapAnswer(Model):
    headline: str | None = None
    decidedBy: Strings = []
    paragraphs: Strings = []
    sources: Annotated[list[Source], DropBad] = []


class ScoutAnswer(Model):
    summary: str | None = None
    strengths: Strings = []
    weaknesses: Strings = []
    keys: Strings = []
    sources: Annotated[list[Source], DropBad] = []


class Story(Model):
    headline: str
    dek: str | None = None
    paragraphs: Strings = []


class Pick(Model):
    gameId: int
    pick: str
    reason: str | None = None


class PaperAnswer(Model):
    stories: Annotated[list[Story], DropBad] = []
    picks: Annotated[list[Pick], DropBad] = []
    sources: Annotated[list[Source], DropBad] = []


class ArticleAnswer(Model):
    """Wave 6: the paper's own article (By the numbers)."""

    headline: str | None = None
    dek: str | None = None
    paragraphs: Strings = []


class Finding(Model):
    subject: str
    appSays: str | None = None
    webSays: str | None = None
    source: str | None = None


class DataCheckAnswer(Model):
    findings: Annotated[list[Finding], DropBad] = []
    checked: Strings = []


class TriviaQuestion(Model):
    team: str | None = None
    question: str
    choices: Strings = []
    answer: str
    source: str | None = None


class TriviaAnswer(Model):
    questions: Annotated[list[TriviaQuestion], DropBad] = []


class EditorSection(Model):
    name: str
    stories: Strings = []


class EditorNumber(Model):
    big: str
    words: str
    storyId: str | None = None


class EditorQuote(Model):
    text: str
    storyId: str


class EditorAnswer(Model):
    """FEAT-14 wave 4: the paper as Claude lays it out; every id is checked against the week's before it is used."""

    lead: str | None = None
    front: Strings = []
    page2Lead: str | None = None
    sections: Annotated[list[EditorSection], DropBad] = []
    kickers: dict[str, str] = {}
    numbers: Annotated[list[EditorNumber], DropBad] = []
    quote: EditorQuote | None = None
    drawings: Strings = []


class Drawing(Model):
    storyId: str
    svg: str
    caption: str | None = None


class ArtAnswer(Model):
    drawings: Annotated[list[Drawing], DropBad] = []


class PicksAnswer(Model):
    """Picks of the week (FEAT-2): a pick for every game by its gameId, one line of reason each."""

    picks: Annotated[list[Pick], DropBad] = []
    sources: Annotated[list[Source], DropBad] = []


class Lot(Model):
    name: str
    detail: str | None = None


class TripAnswer(Model):
    """Getting there (ENH-15): one stadium's game-day sheet, kept a season (the store is the season's)."""

    address: str | None = None
    parking: Annotated[list[Lot], DropBad] = []
    tailgating: Strings = []
    gates: str | None = None
    bagPolicy: str | None = None
    entry: Strings = []
    transit: Strings = []
    accessibility: Strings = []
    gameDay: Strings = []
    sources: Annotated[list[Source], DropBad] = []


@dataclass(frozen=True)
class Kind:
    model: type[Model]
    keys: tuple[str, ...]  # an answer must have one of these
    task: str
    shape: dict[str, Any]
    search: bool = True


KINDS: dict[str, Kind] = {
    "review": Kind(
        ReviewAnswer, ("lessons", "promptAddition"),
        "You wrote the pre-game notes for {team}'s last game (they are in the data below, with what actually happened, as the app"
        " computed it from the box score). Review them: what did the notes get right, what did they miss, and why. Answer with"
        " three to eight short lessons for next week's notes run, each one sentence, concrete (which source to trust, which"
        " report comes out when, what to check twice). When the same kind of miss would come back unless the instructions"
        " change, write ONE short addition to the notes instructions in \"promptAddition\" and say why in \"reason\"; otherwise"
        " leave both out. Do not repeat a lesson already listed under \"earlierLessons\".",
        {"lessons": ["One sentence, concrete."], "promptAddition": "One or two sentences to add to the notes instructions, or leave this out.", "reason": "Why the instructions should change."},
        search=False,
    ),
    "recap": Kind(
        RecapAnswer, ("headline", "decidedBy", "paragraphs"),
        "Write the post-game piece for {team}'s game in the data below: what decided it. Start from the data (the score by"
        " quarter, the box, the biggest swings in the win probability); search the web for the coaches' and players' words"
        " after the game and quote only what a source printed. A headline, two to four short bullets on what decided it, and"
        " three short paragraphs.",
        {"headline": "A headline.", "decidedBy": ["What decided it, one line."], "paragraphs": ["A short paragraph."], "sources": [{"label": "Source name", "url": "https://..."}]},
    ),
    "scout": Kind(
        ScoutAnswer, ("summary", "strengths", "weaknesses"),
        "Write a scouting report on {opponent}, {team}'s next opponent, for {team}'s fans. Start from the app's own numbers in"
        " the data below (success rate by down and distance, explosive plays, havoc, red-zone finishing, with national ranks)"
        " and the opponent's season so far; search the web for its schemes, its key players and what its last opponents said."
        " A two-sentence summary, three to five strengths, three to five weaknesses, and three keys for {team}.",
        {"summary": "Two sentences.", "strengths": ["One line."], "weaknesses": ["One line."], "keys": ["One line."], "sources": [{"label": "Source name", "url": "https://..."}]},
    ),
    "paper": Kind(
        PaperAnswer, ("stories", "picks"),
        "Write this week's college football stories for the app's Newspaper (a newspaper's sports section, written for {team}'s"
        " fans) and the Picks of the week. The week's games are in the data below. Search the web for the week's news. Three"
        " stories: the lead (the biggest game or story of the week), {team}'s week, and one more worth a read; each a headline,"
        " a one-line dek and two to four short paragraphs. Then a pick for every game in the data, by its gameId: the team you"
        " pick to win and one sentence of reason. No betting odds or moneylines; a spread may be named as the market's view.",
        {"stories": [{"headline": "A headline.", "dek": "One line.", "paragraphs": ["A short paragraph."]}], "picks": [{"gameId": 0, "pick": "School", "reason": "One sentence."}], "sources": [{"label": "Source name", "url": "https://..."}]},
    ),
    "datacheck": Kind(
        DataCheckAnswer, ("findings", "checked"),
        "Check the facts the app holds (in the data below) against the web: the coaches, the stadiums, records and anything"
        " else listed. Answer with every fact the web says is wrong or out of date, what the app says, what the web says and"
        " the source; list in \"checked\" the subjects you checked. Report only a difference a reliable source shows.",
        {"findings": [{"subject": "What the fact is about", "appSays": "What the app holds", "webSays": "What the source says", "source": "https://..."}], "checked": ["Subject"]},
    ),
    "editor": Kind(
        EditorAnswer, ("lead", "front", "sections"),
        "You are the editor of {team}'s newspaper in the app. This week's stories are in the data below: each with its id, its"
        " headline, the source, the date, its subject, whether the server holds the whole story (\"copied\"), whether it has a"
        " photo, and its first paragraph. Lay out the paper the way a newspaper's editor would. The lead: the week's biggest news"
        " for {team}, a copied story with a photo when there is one. The front page's three stories under it: the two outside"
        " ones with photos when there are, a headline-only one in the middle when there is. Page 2's lead: the next best copied"
        " story. Then the stories for page 3 in sections under short names (\"The Georgia game\", \"Recruiting\"). The paper is"
        " three pages and page 3 holds 24 stories at most: put the copied stories in first and a headline-only story only where"
        " the copied ones run out; a story you leave out of every page is out of the paper. When the data says \"sunday\": true,"
        " this is the Sunday paper after the game, and every story in it is about the game just played: lead with the game."
        " A kicker of one to three words for each placed story. Up to four numbers for By the numbers, each taken from a"
        " story's text with that story's id. One short quote by {team}'s head coach, word for word from a copied story's first"
        " paragraph, with that story's id. The stories that need a drawing: front-page or page 2 stories with no photo. Use only"
        " the ids in the data.",
        {"lead": "id", "front": ["id", "id", "id"], "page2Lead": "id", "sections": [{"name": "Short name", "stories": ["id"]}], "kickers": {"id": "One to three words"}, "numbers": [{"big": "17", "words": "A few words", "storyId": "id"}], "quote": {"text": "Word for word.", "storyId": "id"}, "drawings": ["id"]},
        search=False,
    ),
    "art": Kind(
        ArtAnswer, ("drawings",),
        "Draw one simple editorial illustration for each story in the data below, for {team}'s newspaper: a flat, modern graphic"
        " about the story's subject in the colors given, as an SVG. Rules for each drawing: viewBox \"0 0 600 400\"; only svg,"
        " g, path, rect, circle, ellipse, line, polyline, polygon and gradients; no text, no letters or numbers, no faces of real"
        " people, no team logos or trademarks, no images, no scripts, no styles; under 20 KB. A one-line caption saying what it"
        " shows.",
        {"drawings": [{"storyId": "id", "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 600 400\">...</svg>", "caption": "What the drawing shows."}]},
        search=False,
    ),
    # Wave 6, second half (owner 2026-11-15): the paper's own article from the app's numbers; every figure is checked
    # against the data before the article can print (app/services/paper_articles.py)
    "numbers": Kind(
        ArticleAnswer, ("headline", "paragraphs"),
        "Write By the numbers for {team}'s newspaper in the app: a short article on {team}'s coming game told through the"
        " figures in the data below, the app's own numbers for both teams, each with its national rank among the FBS teams."
        " A headline, a one-line dek and three to five short paragraphs on the matchups the numbers point to. Every number"
        " you write must appear in the data, as it is written there or as its rank; never work out a number of your own (no"
        " differences, sums, averages or new percentages) and never add one from memory. An article with a number that is"
        " not in the data is refused. Name both teams; no betting advice.",
        {"headline": "A headline.", "dek": "One line.", "paragraphs": ["A short paragraph."]},
        search=False,
    ),
    "trivia": Kind(
        TriviaAnswer, ("questions",),
        "Write ten game-day trivia questions about the two schools in the data below ({home} and {away}): their history, their"
        " stadiums, traditions, famous players and games, the series. Search the web to check every answer. Each question has"
        " four choices, the answer word for word one of them, and the source. Nothing about this season's games still to come.",
        {"questions": [{"team": "School", "question": "The question?", "choices": ["A", "B", "C", "D"], "answer": "A", "source": "https://..."}]},
    ),
    "picks": Kind(
        PicksAnswer, ("picks",),
        "Pick the winner of every game in the data below, this week's college football games with an FBS team, for {team}'s"
        " fans: the Picks of the week. Search the web for the week's previews, injuries and news, and read the market's line"
        " given with each game (a spread may be named as the market's view; no betting odds or moneylines). For each game by"
        " its gameId: the school you pick to win, exactly as the data names it, and ONE short sentence of reason (under 140"
        " characters). Pick every game, the upsets you believe in too; never invent an injury or a quote.",
        {"picks": [{"gameId": 0, "pick": "School", "reason": "One short sentence."}], "sources": [{"label": "Source name", "url": "https://..."}]},
    ),
    "trip": Kind(
        TripAnswer, ("address", "parking", "bagPolicy", "gates"),
        "Write the Getting there sheet for {venue} (in the data below) for fans driving to a game there: the street address;"
        " the parking lots and garages with their prices, when they open and how to pay (pre-paid only, cash, an app); the"
        " tailgating rules and hours; when the gates open and which gates to use; the bag policy; how to get in (mobile tickets,"
        " re-entry, what is not allowed); shuttles, public transit and the rideshare drop-off and pick-up spots; accessible"
        " parking and drop-off. When the data names a game, also what is different for that game (lot and gate times, road"
        " closures, the kickoff time and TV) under \"gameDay\"; otherwise leave it out. Search the web, the school's and the"
        " stadium's own game-day pages first, then the city's; prefer this season's pages and say \"(last season)\" in a line"
        " when only last season's is found. Never guess a price, a time or a lot name. Short lines, at most eight lots and six"
        " lines a list.",
        {"address": "Street, city, state ZIP", "parking": [{"name": "Lot or garage", "detail": "Price, when it opens, how to pay, one line"}], "tailgating": ["One line."], "gates": "When the gates open and which to use.",
         "bagPolicy": "One or two sentences.", "entry": ["One line."], "transit": ["One line."], "accessibility": ["One line."], "gameDay": ["One line, only for the game named."], "sources": [{"label": "Source name", "url": "https://..."}]},
    ),
}


REFRESH_RULES = (
    "This is a refresh (Run with Claude, owner 2026-11-19: \"Each run should see what is in the current page and refresh it"
    " with updated info, or additional info\"). What the page shows now is below. Start from it: keep what still holds,"
    " correct what has changed, remove what is out of date (a player back from injury, a line that moved), and add what is"
    " new since it was written. Never empty a part that has content unless all of it is out of date; answer the whole piece"
    " in the same shape, not only the changes."
)


def refresh_text(so_far: Any, *, limit: int = 12_000) -> str:
    """The refresh block for any prompt: the rules and the piece as it stands (cut short past `limit` characters)."""
    data = json.dumps(so_far, indent=1, ensure_ascii=False, default=str)
    if len(data) > limit:
        data = data[:limit] + "\n... (cut short)"
    return f"\n\n{REFRESH_RULES}\n\nWhat the page shows now:\n```json\n{data}\n```\n"


def build_prompt(kind: str, team: str, packet: dict[str, Any], *, so_far: dict[str, Any] | None = None) -> str:
    """The prompt for one run: the task, the answer's shape, the rules, and the data the app holds; with `so_far` (batch 4)
    the piece as it stands and the refresh rules."""
    spec = KINDS[kind]
    words = {"team": team, "opponent": str(packet.get("opponent") or "the opponent"), "home": str(packet.get("home") or "the home team"), "away": str(packet.get("away") or "the away team"), "venue": str(packet.get("venue") or "the stadium")}
    task = spec.task.format(**words)
    data = json.dumps(packet, indent=1, ensure_ascii=False, default=str)
    if len(data) > MAX_PACKET_CHARS:
        data = data[:MAX_PACKET_CHARS] + "\n... (cut short)"
    search = "Search the web as the task says." if spec.search else "You need no web search for this; the data below is what to work from."
    return (
        f"You are writing for a private second-screen app that follows {team}, for its owner and his friends.\n\n"
        f"{task}\n\n{search} Answer with ONE JSON object in a single ```json code block, nothing else, in exactly this shape"
        " (every field is optional, so leave out what you cannot find, but keep these keys and types):\n\n"
        f"{json.dumps(spec.shape, indent=2)}\n\n"
        "Rules: never invent a fact, a quote, a name, a number or a source; leave a list empty when nothing reliable is found."
        " Plain football language. Valid JSON only: no comments, no trailing commas.\n\n"
        f"The data the app holds (from CollegeFootballData.com and the app's own files):\n```json\n{data}\n```\n"
        + (refresh_text({k: v for k, v in so_far.items() if k not in ("writtenAt", "kind", "key", "season", "model")}) if isinstance(so_far, dict) and so_far else "")
    )


def read(kind: str, text: Any) -> tuple[dict[str, Any] | None, list[str], str | None]:
    """(answer, warnings, error) for one kind's answer. Never raises."""
    spec = KINDS.get(kind)
    if spec is None:
        return None, [], f"no such kind of writing: {kind}"
    parsed = read_json(text, spec.model, keys_score(spec.keys), max_chars=MAX_ANSWER, what=f"a {kind} answer", keys_text=", ".join(spec.keys))
    if parsed.value is None:
        return None, list(parsed.warnings or []), parsed.error
    value = parsed.value.model_dump(exclude_none=True)
    warnings = list(parsed.warnings or [])
    if parsed.problems:
        warnings.append(f"{len(parsed.problems)} damaged rows were left out.")
    if not any(value.get(k) for k in spec.keys):
        return None, warnings, f"The answer had none of {', '.join(spec.keys)}."
    return value, warnings, None


def _iso(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- what was written ----------------------------------------------------------------------------------------------


class WritingStore:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.folder = Path(data_dir) / "season" / str(season) / "writing"

    def path(self, kind: str, key: str) -> Path:
        safe = "".join(c for c in str(key) if c.isalnum() or c in "-_")[:40] or "none"
        return self.folder / f"{kind}-{safe}.json"

    def load(self, kind: str, key: str) -> dict[str, Any] | None:
        try:
            raw = json.loads(self.path(kind, key).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            log.warning("The %s for %s could not be read: %s", kind, key, exc)
            return None
        return raw if isinstance(raw, dict) else None

    def latest(self, kind: str) -> dict[str, Any] | None:
        """The newest piece of a kind (the weekly data check's last run)."""
        try:
            files = sorted(self.folder.glob(f"{kind}-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return None
        for path in files:
            record = self.load(kind, path.stem.removeprefix(f"{kind}-"))
            if record is not None:
                return record
        return None

    def save(self, kind: str, key: str, answer: dict[str, Any]) -> bool:
        """Write the answer; True when it differs from what was there."""
        before = self.load(kind, key)
        record = {**answer, "kind": kind, "key": str(key), "writtenAt": _iso(), "author": "Claude Code on the server"}
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path(kind, key), json.dumps(record, indent=1, ensure_ascii=False) + "\n")
        return before is None or {k: v for k, v in before.items() if k != "writtenAt"} != {k: v for k, v in record.items() if k != "writtenAt"}


LEGACY_SEASON = 2026  # the lessons written before they carried their season were all 2026's


class Lessons:
    """data/claude/lessons.json: {"lessons": [{text, gameId, at, season}], "additions": [{id, text, reason, gameId, at, active}]}.
    Rollover R1 (2026-11-15): a lesson keeps its season and the prompts read the season's own (a player-specific lesson never
    follows him into the next year); the additions are rules the owner can switch off, so they carry over."""

    def __init__(self, data_dir: Path, season: int | None = None) -> None:
        self.path = Path(data_dir) / "claude" / "lessons.json"
        self.season = season

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        except (OSError, ValueError) as exc:
            log.warning("The lessons file could not be read (%s); starting with none", exc)
            raw = {}
        lessons = [r for r in (raw.get("lessons") if isinstance(raw, dict) else None) or [] if isinstance(r, dict) and isinstance(r.get("text"), str)]
        additions = [r for r in (raw.get("additions") if isinstance(raw, dict) else None) or [] if isinstance(r, dict) and isinstance(r.get("text"), str) and isinstance(r.get("id"), str)]
        return {"lessons": lessons, "additions": additions}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")

    def add_review(self, game_id: Any, answer: dict[str, Any]) -> bool:
        data = self.load()
        known = {r["text"].strip().lower() for r in data["lessons"]}
        fresh = [t.strip()[:MAX_LESSON_CHARS] for t in answer.get("lessons", []) if isinstance(t, str) and t.strip() and t.strip().lower() not in known]
        stamp = {"season": self.season} if isinstance(self.season, int) else {}
        data["lessons"] = [*data["lessons"], *({"text": t, "gameId": game_id, "at": _iso(), **stamp} for t in fresh)][-MAX_LESSONS * 3:]
        addition = answer.get("promptAddition")
        added = False
        if isinstance(addition, str) and addition.strip() and addition.strip() not in {a["text"] for a in data["additions"]}:
            data["additions"].append({"id": uuid.uuid4().hex[:10], "text": addition.strip()[:MAX_ADDITION_CHARS], "reason": str(answer.get("reason") or "")[:MAX_ADDITION_CHARS] or None, "gameId": game_id, "at": _iso(), "active": True})
            added = True
        self._save(data)
        return bool(fresh) or added

    def set_active(self, addition_id: str, active: bool) -> dict[str, Any] | None:
        data = self.load()
        row = next((a for a in data["additions"] if a["id"] == addition_id), None)
        if row is None:
            return None
        row["active"] = bool(active)
        row["changedAt"] = _iso()
        self._save(data)
        return row

    def for_prompt(self) -> tuple[list[str], list[str]]:
        """(the newest lessons, the active additions) for the notes prompt."""
        data = self.load()
        rows = data["lessons"]
        if isinstance(self.season, int):
            rows = [r for r in rows if (r.get("season") if isinstance(r.get("season"), int) else LEGACY_SEASON) == self.season]
        return [r["text"] for r in rows[-MAX_LESSONS:]], [a["text"] for a in data["additions"] if a.get("active") is not False]


# --- the runner ----------------------------------------------------------------------------------------------------


@dataclass
class Job:
    kind: str
    key: str
    team: str
    packet: dict[str, Any]
    save: Callable[[dict[str, Any]], bool]  # writes the answer where it goes; True when something changed
    label: str = ""
    check: Callable[[dict[str, Any]], str | None] | None = None  # Wave 6: why the answer may not print (a figure not in the data), or None
    so_far: dict[str, Any] | None = None  # batch 4: the piece as it stands, for a refresh (Run with Claude)


class WritingRunner:
    """One run at a time, the notes runner's way: the tool in an empty scratch folder, the prompt on stdin, the answer read
    from its log. `logs/writing-<kind>-<key>.log` holds the last run of each."""

    def __init__(self, data_dir: Path, log_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.log_dir = Path(log_dir)
        self.task: asyncio.Task[Any] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.job: Job | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.error: str | None = None
        self.warnings: Strings = []
        self.saved = False
        self.changed: bool | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def log_path(self, job: Job) -> Path:
        safe = "".join(c for c in job.key if c.isalnum() or c in "-_")[:40]
        return self.log_dir / f"writing-{job.kind}-{safe}.log"

    def status(self) -> dict[str, Any]:
        job = self.job
        return {
            "running": self.running,
            "kind": job.kind if job else None,
            "key": job.key if job else None,
            "label": job.label if job else None,
            "startedAt": _iso(self.started_at) if self.started_at else None,
            "finishedAt": _iso(self.finished_at) if self.finished_at else None,
            "error": self.error,
            "warnings": list(self.warnings),
            "saved": self.saved,
            "changed": self.changed,
        }

    async def start(self, job: Job, command: str, model: str | None = None) -> dict[str, Any]:
        if job.kind not in KINDS:
            return {**self.status(), "error": f"no such kind of writing: {job.kind}"}
        if self.running:
            return {**self.status(), "error": f"a {self.job.kind if self.job else ''} run is still going"}
        resolved = NotesRunner.resolve_command(command)
        if resolved is None:
            return {**self.status(), "error": f"{command!r} was not found. Install Claude Code's command-line tool, or set its full path in .env."}
        self.job, self.started_at, self.finished_at = job, datetime.now(timezone.utc), None
        self.error, self.warnings, self.saved, self.changed = None, [], False, None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        prompt = build_prompt(job.kind, job.team, job.packet, so_far=job.so_far)
        self.task = asyncio.create_task(self._run(resolved, prompt, job, model))
        return self.status()

    async def _run(self, executable: str, prompt: str, job: Job, model: str | None) -> None:
        prefix = NotesRunner.command_args(executable)
        args = [*prefix, "-p", PROMPT_LEAD, "--allowedTools", ALLOWED_TOOLS, "--output-format", "text", *await lockdown_args(prefix)]
        if model:
            args += ["--model", model]
        header = f"# {job.kind} for {job.key}, started {_iso(self.started_at)}\n"
        path = self.log_path(job)
        exit_code: int | None = None
        log.info("Claude writing started: %s %s", job.kind, job.key)
        try:
            with path.open("w", encoding="utf-8") as handle:
                handle.write(header)
                handle.flush()
                self.process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=handle, stderr=asyncio.subprocess.STDOUT, cwd=str(scratch_dir(self.data_dir)))
                try:
                    await asyncio.wait_for(self.process.communicate(prompt.encode("utf-8")), timeout=MAX_RUN_SECONDS)
                    exit_code = self.process.returncode
                except TimeoutError:
                    self.process.kill()
                    self.error = f"stopped after {MAX_RUN_SECONDS // 60} minutes without finishing"
                    exit_code = await self.process.wait()
        except (OSError, ValueError) as exc:
            self.error = f"could not start {executable}: {exc}"
        finally:
            self.process = None
            if exit_code == 0:
                claude_signin.succeeded()
            elif self.error is None and exit_code is not None:
                self.error = claude_signin.from_log(path) or f"the tool exited with code {exit_code}"  # 2026-11-15: signed out, said so
            if self.error is None:
                self._save(path, header, job)
            self.finished_at = datetime.now(timezone.utc)
            log.info("Claude writing %s %s finished: %s", job.kind, job.key, "saved" if self.saved else f"not saved ({self.error})")

    def _save(self, path: Path, header: str, job: Job) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").removeprefix(header)
        except OSError as exc:
            self.error = f"the tool's answer could not be read: {exc}"
            return
        answer, warnings, error = read(job.kind, text)
        self.warnings = warnings
        if answer is None:
            self.error = f"the tool finished but its answer could not be used: {error} See the log."
            return
        if job.check is not None:
            refused = job.check(answer)
            if refused:  # Wave 6: a figure the data does not hold never prints; the run says why
                self.error = f"the answer was refused, {refused}. Nothing was kept."
                log.warning("Claude writing %s %s refused: %s", job.kind, job.key, refused)
                return
        try:
            self.changed = bool(job.save(answer))
        except OSError as exc:
            self.error = f"the answer could not be saved: {exc}"
            return
        self.saved = True

    async def stop(self) -> None:
        if self.process is not None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown must not raise
                pass
