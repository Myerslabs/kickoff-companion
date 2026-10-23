"""Feedback with the logs (owner 2026-10-23, the testers' Friday: "The logs should come with the feedback. I want to be
able to see what was done when feedback was submitted."). Any device, guests too, sends a report from the menu; the
server keeps it with what was around it, one folder a report under data/feedback/, so the host (and the intake on
Saturday) reads exactly what happened. Nothing leaves the house: a report becomes a GitHub issue only when the host
opens GitHub's own form from the Feedback list, with the text filled in and the logs left at home.

    data/feedback/<YYYYMMDD-HHMMSS>-<id>/
        report.json      the kind (bug, enhancement, feature), the words, the name, the page, the device, when, host or guest
        trail.json       what that tablet did in the WINDOW before: pages opened, taps by their label, sheets, errors
        server-log.txt   the server log's lines from the same window (the key is redacted by the log formatter already)
        status.json      the status snapshot: version, plan, quota, feeds, housekeeping, the settings (no secrets live there)

    FeedbackStore(data_dir, log_dir, clock=wall clock)   the wall clock, never the demo's: the log's stamps are real time
        save(report, status, host) -> summary     one folder written, the summary returned
        list() -> [summary]                        newest first; a damaged folder is skipped and counted
        get(id) -> report with its trail and log, or None
        mail(report) -> {to, subject, body, full}  the report as an email from the sender's own mail app: the words, the
                                                   version, the last steps and the log's warnings and errors, with home
                                                   addresses, computer names and user names taken out
        zip_bytes(id) -> bytes or None             the folder as a zip, for the download
        logs_zip(status) -> bytes                  every log file and the status snapshot, for About and help
        tail(lines) -> str                          the log's last lines, for Copy
"""

from __future__ import annotations

import io
import json
import logging
import re
import secrets
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.logging_setup import DATE_FORMAT, LOG_FILE_NAME

log = logging.getLogger("kickoff.feedback")

FOLDER = "feedback"
WINDOW = timedelta(minutes=15)
MAX_TRAIL = 300
MAX_LOG_LINES = 4000
TAIL_DEFAULT = 200
ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
LINE_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ")
# belt and braces: the log formatter already redacts the CFBD key; anything that still looks like a credential goes too
CREDENTIAL = re.compile(r"(?i)(authorization:\s*bearer\s+|api[_-]?key[=:]\s*|pin[=:]\s*)\S+")

Kind = Literal["bug", "enhancement", "feature"]


class TrailStep(BaseModel):
    """One thing the tablet did: when, what kind, and what (a page's address, a button's label, an error's message)."""

    at: str = Field(max_length=40)
    kind: Literal["page", "tap", "sheet", "error", "note"] = "note"
    what: str = Field(default="", max_length=300)
    route: str | None = Field(default=None, max_length=200)


class FeedbackIn(BaseModel):
    kind: Kind = "bug"
    text: str = Field(min_length=1, max_length=4000)
    name: str = Field(default="", max_length=40)
    route: str = Field(default="", max_length=200)
    device: dict[str, Any] = Field(default_factory=dict)
    trail: list[TrailStep] = Field(default_factory=list)

    @field_validator("text", "name", "route", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("trail", mode="before")
    @classmethod
    def _good_steps(cls, value: Any) -> list[Any]:
        """A damaged step is dropped, never the report; at most MAX_TRAIL, the latest kept."""
        steps = value if isinstance(value, list) else []
        good = []
        for step in steps[-MAX_TRAIL:]:
            try:
                good.append(TrailStep.model_validate(step))
            except ValidationError:
                continue
        return good

    @field_validator("device", mode="before")
    @classmethod
    def _small_device(cls, value: Any) -> dict[str, Any]:
        """The screen, the browser and the app's version: plain values only, a handful of them."""
        if not isinstance(value, dict):
            return {}
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            if isinstance(key, str) and len(key) <= 40 and (isinstance(item, (int, float, bool)) or (isinstance(item, str) and len(item) <= 300)):
                out[key] = item
        return out


def scrub(text: str) -> str:
    return CREDENTIAL.sub(lambda m: m.group(1) + "[redacted]", text)


PRIVATE_IP = re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")
HOST_NAME = re.compile(r"\b[\w-]+\.(?:local|localdomain|lan|home|internal)\b", re.IGNORECASE)
USER_DIR = re.compile(r"(?i)(\b[a-z]:\\users\\|(?<![\w/])/home/|(?<![\w/])/users/)[^\\/\s\"']+")
MAIL_SHORT = 1200  # the body a mail link carries (some mail apps cut a longer link)
MAIL_FULL = 6000  # Copy the report


def share_safe(text: str) -> str:
    """A report's words fit to email: credentials, home-network addresses, computer names and user names taken out."""
    text = scrub(text)
    text = PRIVATE_IP.sub("[a home address]", text)
    text = HOST_NAME.sub("[a computer]", text)
    return USER_DIR.sub(lambda m: m.group(1) + "[user]", text)


class FeedbackStore:
    def __init__(self, data_dir: Path, log_dir: Path, clock: Callable[[], datetime] | None = None) -> None:
        self.folder = Path(data_dir) / FOLDER
        self.log_dir = Path(log_dir)
        self.clock = clock or (lambda: datetime.now().astimezone())

    # --- the server log -------------------------------------------------------------------------------

    def _log_files(self) -> list[Path]:
        """app.log first, then its rotated copies (app.log.1 is the newest of those)."""
        main = self.log_dir / LOG_FILE_NAME
        rotated = sorted(self.log_dir.glob(f"{LOG_FILE_NAME}.*"), key=lambda p: int(p.suffix[1:]) if p.suffix[1:].isdigit() else 99)
        return [p for p in [main, *rotated] if p.is_file()]

    def _lines(self, limit: int = MAX_LOG_LINES) -> list[str]:
        """The log's last `limit` lines in order, across the rotation."""
        out: list[str] = []
        for path in self._log_files():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                log.warning("Could not read %s for a feedback report: %s", path.name, exc)
                continue
            out = lines + out
            if len(out) >= limit:
                break
        return out[-limit:]

    def window_log(self, now: datetime) -> str:
        """The log lines of the last WINDOW (a line without its own time belongs to the line above, a traceback)."""
        start = now - WINDOW
        since = start.astimezone().replace(tzinfo=None) if start.tzinfo else start  # the log writes the server's local time
        kept: list[str] = []
        keep = False
        for line in self._lines():
            match = LINE_TIME.match(line)
            if match:
                try:
                    keep = datetime.strptime(match.group(1), DATE_FORMAT) >= since
                except ValueError:
                    keep = False
            if keep:
                kept.append(line)
        return scrub("\n".join(kept)) + ("\n" if kept else "")

    def tail(self, lines: int = TAIL_DEFAULT) -> str:
        count = max(1, min(int(lines), 2000))
        return scrub("\n".join(self._lines(count)))

    # --- reports --------------------------------------------------------------------------------------

    def save(self, report: FeedbackIn, status: dict[str, Any], *, host: bool) -> dict[str, Any]:
        now = self.clock()
        local = now.astimezone() if now.tzinfo else now
        report_id = f"{local:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        folder = self.folder / report_id
        folder.mkdir(parents=True, exist_ok=False)
        body = {
            "id": report_id,
            "kind": report.kind,
            "text": report.text,
            "name": report.name,
            "route": report.route,
            "device": report.device,
            "submittedAt": now.isoformat(),
            "from": "host" if host else "guest",
            "trailSteps": len(report.trail),
        }
        (folder / "report.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / "trail.json").write_text(json.dumps([step.model_dump() for step in report.trail], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / "server-log.txt").write_text(self.window_log(now), encoding="utf-8")
        (folder / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        log.info("Feedback %s saved: a %s from %s (%s, %d trail steps)", report_id, report.kind, body["from"], report.route or "no page", len(report.trail))
        return self._summary(body)

    @staticmethod
    def _summary(body: dict[str, Any]) -> dict[str, Any]:
        text = body.get("text") if isinstance(body.get("text"), str) else ""
        return {
            "id": body.get("id"),
            "kind": body.get("kind"),
            "name": body.get("name") or "",
            "route": body.get("route") or "",
            "submittedAt": body.get("submittedAt"),
            "from": body.get("from"),
            "first": text.splitlines()[0][:160] if text else "",
            "trailSteps": body.get("trailSteps"),
        }

    def _folder(self, report_id: str) -> Path | None:
        if not isinstance(report_id, str) or not ID_PATTERN.match(report_id):
            return None  # never a path from the address bar
        folder = self.folder / report_id
        return folder if (folder / "report.json").is_file() else None

    def list(self) -> dict[str, Any]:
        reports: list[dict[str, Any]] = []
        skipped = 0
        if self.folder.is_dir():
            for folder in sorted(self.folder.iterdir(), reverse=True):
                if not folder.is_dir() or not ID_PATTERN.match(folder.name):
                    continue
                try:
                    body = json.loads((folder / "report.json").read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    skipped += 1
                    log.warning("Feedback %s could not be read: %s", folder.name, exc)
                    continue
                if isinstance(body, dict):
                    reports.append(self._summary({**body, "id": folder.name}))
                else:
                    skipped += 1
        return {"reports": reports, "skipped": skipped, "folder": str(self.folder)}

    def get(self, report_id: str) -> dict[str, Any] | None:
        folder = self._folder(report_id)
        if folder is None:
            return None

        def read(name: str, default: Any) -> Any:
            try:
                text = (folder / name).read_text(encoding="utf-8")
                return json.loads(text) if name.endswith(".json") else text
            except (OSError, ValueError):
                return default

        body = read("report.json", {})
        return {**(body if isinstance(body, dict) else {}), "id": report_id, "trail": read("trail.json", []), "serverLog": read("server-log.txt", ""), "folder": str(folder)}

    def mail(self, report: dict[str, Any], version: str, to: str, app_name: str) -> dict[str, str]:
        """The report as an email the sender's own mail app sends (owner 2026-10-23: "a crash report comes up. It seems to
        email it to the developers, and can attach logs if necessary"): `body` short enough for a mail link, `full` for
        Copy the report; the full report stays a download to attach."""
        kind = {"bug": "Bug", "enhancement": "Enhancement", "feature": "Feature"}.get(report.get("kind"), "Bug")
        words = report.get("text") if isinstance(report.get("text"), str) else ""
        first = words.splitlines()[0][:70] if words else "Feedback"
        device = report.get("device") if isinstance(report.get("device"), dict) else {}
        screen = f"{device.get('width')}x{device.get('height')}" if device.get("width") else "unknown"
        steps = [s for s in (report.get("trail") or []) if isinstance(s, dict)]
        log_text = report.get("serverLog") if isinstance(report.get("serverLog"), str) else ""
        trouble = [line for line in log_text.splitlines() if " WARNING " in line or " ERROR " in line or " CRITICAL " in line]

        def step_line(s: dict[str, Any]) -> str:
            at = str(s.get("at") or "")[11:19]
            return f"{at} {s.get('kind')}: {s.get('what')}"

        def build(step_count: int, line_count: int) -> str:
            parts = [
                words,
                "",
                f"-- {app_name} {version}, a {kind.lower()} report ({report.get('id')})",
                f"Page {report.get('route') or 'not recorded'}, screen {screen}, sent {str(report.get('submittedAt') or '')[:16].replace('T', ' ')}",
            ]
            if step_count and steps:
                parts += ["", f"The last {min(step_count, len(steps))} steps on the device:", *[step_line(s) for s in steps[-step_count:]]]
            if line_count and trouble:
                parts += ["", "The log's last warnings and errors:", *trouble[-line_count:]]
            parts += ["", f"The full report, every log line included, is in {app_name}: Profile, Feedback. Attach it if asked."]
            return share_safe("\n".join(parts))

        body = build(8, 5)
        for steps_kept, lines_kept in ((6, 3), (4, 2), (2, 1), (0, 0)):
            if len(body) <= MAIL_SHORT:
                break
            body = build(steps_kept, lines_kept)
        body = body[:MAIL_SHORT]
        full = build(40, 30)[:MAIL_FULL]
        return {"to": to, "subject": f"{app_name} {version} {kind.lower()}: {share_safe(first)}", "body": body, "full": full}

    def zip_bytes(self, report_id: str) -> bytes | None:
        folder = self._folder(report_id)
        if folder is None:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.iterdir()):
                if path.is_file():
                    archive.write(path, f"{report_id}/{path.name}")
        return buffer.getvalue()

    def logs_zip(self, status: dict[str, Any]) -> bytes:
        """Every log file (redacted again on the way out) and the status snapshot: the download in About and help."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in self._log_files():
                try:
                    archive.writestr(f"logs/{path.name}", scrub(path.read_text(encoding="utf-8", errors="replace")))
                except OSError as exc:
                    archive.writestr(f"logs/{path.name}.unreadable.txt", f"{exc}\n")
            archive.writestr("status.json", json.dumps(status, indent=1, ensure_ascii=False, default=str) + "\n")
        return buffer.getvalue()
