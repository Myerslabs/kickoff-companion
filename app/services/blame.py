"""Circle of Blame (FEAT-18, Feature Set v2 Phase C): the weekly report's shape, the checks the
server makes before anything is shown, and the season's reports on disk.

Claude Code writes the report; nothing it says is trusted until these checks pass (spec C.5): 4 to 6 slices, whole-number
shares summing to exactly 100, a known kind and trend, at least two pieces of evidence a slice, and the name of every coach or
player slice found word for word in the evidence pack (the guard against invented names). A failed check is one retry with
the errors attached; a second failure publishes nothing (the job keeps the raw output).

    KINDS, TRENDS, RESULTS, CONFIDENCE
    read_answer(text)                          the JSON object in Claude's reply (fences and stray words around it tolerated)
    check_report(text, pack_text, season, week) -> (report | None, errors)
    week_key(season_type, week)                "week-9", "post-1"
    BlameStore(data_dir, season)               data/season/<year>/blame/<key>.json (published), failed/<key>.json (the last
                                               failure), <key>.pack.json (the evidence pack a report was written from)
    history(records)                           the season strip: each week's slices and its top one
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.blame")

SCHEMA_VERSION = "1"
KINDS = ("coach", "player", "unit", "scheme", "roster", "injuries", "officiating", "schedule", "media", "other")
TRENDS = ("up", "down", "new", "flat")
RESULTS = ("win", "loss", "tie")
CONFIDENCE = ("low", "medium", "high")
MIN_SLICES, MAX_SLICES = 4, 6
MIN_EVIDENCE = 2
NAMED_KINDS = ("coach", "player")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metric: str
    value: str
    context: str = ""

    @field_validator("value", "context", "metric", mode="before")
    @classmethod
    def _words(cls, v: Any) -> Any:
        if isinstance(v, bool):
            return str(v).lower()
        if isinstance(v, int | float):
            return f"{v:g}" if isinstance(v, float) else str(v)
        return "" if v is None else v


class Slice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    kind: str
    share_pct: int
    case: str
    evidence: list[Evidence]
    trend: str

    @field_validator("share_pct", mode="before")
    @classmethod
    def _whole(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("a share is a whole number, not true or false")
        if isinstance(v, float):
            if not v.is_integer():
                raise ValueError(f"a share is a whole number, not {v:g}")
            return int(v)
        return v


class Report(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: str = SCHEMA_VERSION
    season: int
    week: int
    after_result: str
    verdict: str
    slices: list[Slice]
    movement: str = ""
    limitations: list[str] = []
    confidence: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version(cls, v: Any) -> Any:
        return str(v) if isinstance(v, int | float) and not isinstance(v, bool) else v


FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)

# A blank in the pack is JSON's null, and Claude once wrote it into a sentence: "Strength of schedule is null in the SP+ block" in the
# week 11 report's What the pack lacked (owner 2026-11-15, "fix the null in the note"; the rule: never undefined, null or
# NaN on screen). The prompt asks for plain words now (circle_of_blame.system/2), and the words a pack leaks are "missing" in
# every string of a report, when a new one is checked and when a stored one is read, so a report written before the prompt
# changed reads right too, and so does last week's report in the next pack.
RAW_WORDS = re.compile(r"\b(?:null|undefined|NaN)\b")


def plain_words(value: Any) -> Any:
    """Every string in a report with the JSON words a blank leaks into prose ("null", "undefined", "NaN") as "missing"."""
    if isinstance(value, str):
        return RAW_WORDS.sub("missing", value)
    if isinstance(value, list):
        return [plain_words(v) for v in value]
    if isinstance(value, dict):
        return {k: plain_words(v) for k, v in value.items()}
    return value


def read_answer(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """The one JSON object in Claude's reply: (object, None), or (None, why not)."""
    if not isinstance(text, str) or not text.strip():
        return None, "the reply was empty"
    body = FENCE.sub("", text.strip())
    try:
        value = json.loads(body)
    except ValueError:
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            return None, "the reply held no JSON object"
        try:
            value = json.loads(body[start : end + 1])
        except ValueError as exc:
            return None, f"the reply's JSON could not be read ({exc.msg} at character {exc.pos})"
    if not isinstance(value, dict):
        return None, "the reply's JSON was not one object"
    return value, None


def _where(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "the report"


def check_report(text: str, pack_text: str, season: int, week: int) -> tuple[dict[str, Any] | None, list[str]]:
    """Every C.5 rule, in code: (the report as a plain dict, []) when it passes, else (None, the errors in words)."""
    raw, why = read_answer(text)
    if raw is None:
        return None, [why or "the reply could not be read"]
    try:
        report = Report.model_validate(raw)
    except ValidationError as exc:
        return None, [f"{_where(tuple(e.get('loc') or ()))}: {e.get('msg')}" for e in exc.errors()]
    errors: list[str] = []
    if report.schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must be \"{SCHEMA_VERSION}\", not \"{report.schema_version}\"")
    if report.season != season:
        errors.append(f"season must be {season}, not {report.season}")
    if report.week != week:
        errors.append(f"week must be {week}, not {report.week}")
    if report.after_result not in RESULTS:
        errors.append(f"after_result must be one of {', '.join(RESULTS)}, not \"{report.after_result}\"")
    if report.confidence not in CONFIDENCE:
        errors.append(f"confidence must be one of {', '.join(CONFIDENCE)}, not \"{report.confidence}\"")
    if not report.verdict.strip():
        errors.append("the verdict is empty")
    n = len(report.slices)
    if not MIN_SLICES <= n <= MAX_SLICES:
        errors.append(f"there must be {MIN_SLICES} to {MAX_SLICES} slices, not {n}")
    total = sum(s.share_pct for s in report.slices)
    if total != 100:
        errors.append(f"the shares must sum to exactly 100, not {total}")
    names: set[str] = set()
    for i, s in enumerate(report.slices):
        label = f"slices[{i}] ({s.name or 'no name'})"
        if not s.name.strip():
            errors.append(f"slices[{i}] has no name")
        elif s.name.strip().casefold() in names:
            errors.append(f"{label} is named twice")
        names.add(s.name.strip().casefold())
        if s.kind not in KINDS:
            errors.append(f"{label}: kind must be one of {', '.join(KINDS)}, not \"{s.kind}\"")
        if s.trend not in TRENDS:
            errors.append(f"{label}: trend must be one of {', '.join(TRENDS)}, not \"{s.trend}\"")
        if s.share_pct <= 0:
            errors.append(f"{label}: a share must be more than 0, not {s.share_pct}")
        if not s.case.strip():
            errors.append(f"{label}: the case is empty")
        good = [e for e in s.evidence if e.metric.strip() and e.value.strip()]
        if len(good) < MIN_EVIDENCE:
            errors.append(f"{label}: needs at least {MIN_EVIDENCE} pieces of evidence with a metric and a value, not {len(good)}")
        if s.kind in NAMED_KINDS and s.name.strip() and s.name.strip() not in pack_text:
            errors.append(f"{label}: \"{s.name.strip()}\" does not appear in the evidence pack; name only {s.kind}s the pack names, exactly as written")
    if errors:
        return None, errors
    out = plain_words(report.model_dump())
    out["schema_version"] = SCHEMA_VERSION
    for s in out["slices"]:
        s["name"] = s["name"].strip()
    return out, []


def week_key(season_type: str | None, week: int) -> str:
    return f"post-{week}" if str(season_type or "regular") == "postseason" else f"week-{week}"


def key_order(key: str) -> tuple[int, int]:
    kind, _, n = key.partition("-")
    return (1 if kind == "post" else 0, int(n) if n.isdigit() else 0)


class BlameStore:
    """The season's reports, one file a game week, written whole."""

    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(season) / "blame"
        self.season = season

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def save(self, key: str, record: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path(key), json.dumps(record, ensure_ascii=False, indent=1) + "\n")

    def save_pack(self, key: str, pack: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.dir / f"{key}.pack.json", json.dumps(pack, ensure_ascii=False, indent=1) + "\n")

    def save_failure(self, key: str, record: dict[str, Any]) -> None:
        folder = self.dir / "failed"
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write(folder / f"{key}.json", json.dumps(record, ensure_ascii=False, indent=1) + "\n")

    def load(self, key: str) -> dict[str, Any] | None:
        try:
            value = json.loads(self.path(key).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            log.exception("The Circle of Blame file %s could not be read", self.path(key))
            return None
        if not isinstance(value, dict) or not isinstance(value.get("report"), dict):
            return None
        return {**value, "report": plain_words(value["report"])}  # a report written before the prompt asked for plain words reads right too

    def load_failure(self, key: str) -> dict[str, Any] | None:
        try:
            value = json.loads((self.dir / "failed" / f"{key}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def keys(self) -> list[str]:
        try:
            names = [p.stem for p in self.dir.glob("*.json") if not p.name.endswith(".pack.json")]
        except OSError:
            return []
        return sorted((k for k in names if re.fullmatch(r"(week|post)-\d+", k)), key=key_order)

    def records(self) -> list[tuple[str, dict[str, Any]]]:
        out = []
        for key in self.keys():
            record = self.load(key)
            if record is not None:
                out.append((key, record))
        return out

    def latest(self) -> tuple[str, dict[str, Any]] | None:
        found = self.records()
        return found[-1] if found else None


def history(records: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """The season strip: each week in order, its result, its slices and its top one."""
    out = []
    for key, record in records:
        report = record.get("report") or {}
        slices = [{"name": s.get("name"), "kind": s.get("kind"), "share": s.get("share_pct")} for s in report.get("slices") or [] if isinstance(s, dict)]
        top = max(slices, key=lambda s: s["share"] if isinstance(s["share"], int) else -1) if slices else None
        out.append({"key": key, "week": report.get("week"), "label": record.get("label"), "result": report.get("after_result"), "opponent": record.get("opponent"), "score": record.get("score"), "home": record.get("home"), "neutral": record.get("neutral"), "top": top, "slices": slices})
    return out
