"""Updates from GitHub (FEAT-13). A host that runs from a clone of the repository asks GitHub for new commits on main and,
only when someone taps Update, brings them in and restarts the server with the new code. Never by itself. The packaged
program is not a clone: it says where the newest download is.

    GitUpdater(root, data_dir, runner=None, clock=None, enabled=None, git=None, environ=None)
      await status(force=False) -> {enabled, available, branch, head, behind, ahead, changes, packagesChange,
                                    canUpdate, blocked, checkedAt, error, updating, lastUpdate, syncPending, relaunch, current}
      await apply() -> {updated, from, to, count, syncNeeded, relaunch}   (raises UpdateRefused with a code and words)

Asking: `git fetch origin main` in the project folder, at most once an hour (FETCH_SECONDS) unless asked (Check now),
with git told never to ask for a password in a window (GIT_TERMINAL_PROMPT=0, GCM_INTERACTIVE=never). The sign-in to
GitHub is done once by hand on that computer (a `git clone` or `git fetch` in PowerShell); a fetch without it is an error
that says so. Keyless for the app and outside the CFBD quota. Nothing asks without a viewer: a page's look asks.

Updating, on a tap: the copy must be on main, with no tracked file changed by hand and nothing local that GitHub lacks.
Then `git merge --ff-only origin/main`. When pyproject.toml, uv.lock or requirements.txt changed, data/update-sync.json
asks the launcher to run `uv sync` before the server starts again (Windows locks the packages a running server loaded).
The caller then asks for a restart, which under the tray or start.ps1's window is a fresh process (app/restart.py)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import __version__
from app.paths import is_frozen
from app.restart import relaunch_available
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.updates")

REMOTE = "origin"
BRANCH = "main"
FETCH_SECONDS = 3600  # a page's look asks GitHub at most once an hour; Check now asks at once
ANSWER_SECONDS = 30  # the local answer (branch, counts) is kept this long between looks
GIT_TIMEOUT = 20.0
FETCH_TIMEOUT = 60.0
MERGE_TIMEOUT = 120.0
PACKAGE_FILES = ("pyproject.toml", "uv.lock", "requirements.txt")
SYNC_MARKER = "update-sync.json"
SEP = "\x1f"
NOT_A_CLONE = "This copy isn't a git clone, so it can't update itself. The newest download is on github.com/Myerslabs/kickoff-companion/releases."
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: no console flashes on the host's screen

Runner = Callable[[list[str], float], tuple[int, str, str]]


class UpdateRefused(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def find_git(environ: Mapping[str, str] | None = None) -> str | None:
    """git on the path, else where Git for Windows installs it (Claude Code on Windows brings it)."""
    found = shutil.which("git")
    if found:
        return found
    env = os.environ if environ is None else environ
    for base in (env.get("ProgramFiles", r"C:\Program Files"), env.get("LOCALAPPDATA", "")):
        if not base:
            continue
        for candidate in (Path(base) / "Git" / "cmd" / "git.exe", Path(base) / "Programs" / "Git" / "cmd" / "git.exe"):
            if candidate.is_file():
                return str(candidate)
    return None


def fetch_trouble(stderr: str) -> str:
    """Git's refusal in plain words."""
    text = " ".join(str(stderr or "").split())
    low = text.lower()
    if any(word in low for word in ("authentication failed", "could not read username", "terminal prompts disabled", "repository not found", "permission denied", "403")):
        return ("GitHub asked for a sign-in. Once on this computer, open PowerShell in the project folder and run git fetch; "
                "sign in to GitHub when the window asks. The app does the rest after that.")
    if any(word in low for word in ("could not resolve host", "unable to access", "timed out", "connection")):
        return "GitHub didn't answer (no internet?). The app asks again later; Check now asks at once."
    return f"git fetch failed: {text[:200] or 'no message'}"


class GitUpdater:
    def __init__(
        self,
        root: Path,
        data_dir: Path,
        *,
        runner: Runner | None = None,
        clock: Callable[[], datetime] | None = None,
        enabled: Callable[[], bool] | None = None,
        git: str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "update.json"
        self.marker = self.data_dir / SYNC_MARKER
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._enabled = enabled or (lambda: True)
        self._environ = os.environ if environ is None else environ
        self.git = git if git is not None else find_git(self._environ)
        self._runner = runner or self._run
        self._lock = asyncio.Lock()
        self._answer: tuple[float, dict[str, Any]] | None = None
        self.updating = False

    # -- running git -------------------------------------------------------------------------------------------
    def _run(self, args: list[str], timeout: float) -> tuple[int, str, str]:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASKPASS": "", "LC_ALL": "C"}
        try:
            done = subprocess.run(args, cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env, creationflags=NO_WINDOW, check=False)  # noqa: S603 - git with fixed arguments
        except subprocess.TimeoutExpired:
            return 124, "", f"timed out after {int(timeout)} s"
        except OSError as exc:
            return 127, "", str(exc)
        return done.returncode, done.stdout.rstrip(), done.stderr.strip()  # rstrip: a status line starts with a space

    def _git(self, *args: str, timeout: float = GIT_TIMEOUT) -> tuple[int, str, str]:
        assert self.git is not None
        return self._runner([self.git, *args], timeout)

    def _out(self, *args: str) -> str | None:
        code, out, _err = self._git(*args)
        return out if code == 0 else None

    # -- what is kept between looks ----------------------------------------------------------------------------
    def _stored(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _store(self, **fields: Any) -> None:
        kept = {**self._stored(), **fields}
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(self.path, json.dumps(kept, indent=1) + "\n")
        except OSError as exc:
            log.warning("Could not keep the update check: %s", exc)

    def _fetch_due(self, stored: dict[str, Any]) -> bool:
        try:
            age = (self._clock() - datetime.fromisoformat(str(stored["checkedAt"]).replace("Z", "+00:00"))).total_seconds()
        except (KeyError, TypeError, ValueError):
            return True
        return age >= FETCH_SECONDS or age < 0

    # -- the answer --------------------------------------------------------------------------------------------
    def _base(self) -> dict[str, Any]:
        stored = self._stored()
        last = stored.get("lastUpdate") if isinstance(stored.get("lastUpdate"), dict) else None
        return {
            "enabled": self._enabled(),
            "available": False,
            "current": __version__,
            "branch": None,
            "head": None,
            "remote": f"{REMOTE}/{BRANCH}",
            "behind": 0,
            "ahead": 0,
            "changes": [],
            "packagesChange": False,
            "dirty": [],
            "canUpdate": False,
            "blocked": None,
            "checkedAt": stored.get("checkedAt") if isinstance(stored.get("checkedAt"), str) else None,
            "error": stored.get("fetchError") if isinstance(stored.get("fetchError"), str) else None,
            "updating": self.updating,
            "lastUpdate": last,
            "syncPending": self.marker.is_file(),
            "relaunch": relaunch_available(self._environ),
        }

    def _commit(self, ref: str) -> dict[str, Any] | None:
        out = self._out("log", "-1", f"--format=%H{SEP}%h{SEP}%s{SEP}%cI", ref)
        if not out:
            return None
        parts = out.split(SEP)
        if len(parts) != 4:
            return None
        return {"sha": parts[0], "short": parts[1], "subject": parts[2], "date": parts[3]}

    def _local(self, answer: dict[str, Any]) -> dict[str, Any]:
        """Everything git knows without asking GitHub."""
        if is_frozen() or not (self.root / ".git").exists():
            # the packaged program, or a copy that is not a clone: never git, and never a repository above this folder (2.0 review)
            answer["blocked"] = {"code": "not_a_clone", "message": NOT_A_CLONE}
            return answer
        if self.git is None:
            answer["blocked"] = {"code": "no_git", "message": "git isn't installed on this computer, so the app can't update itself. Install Git for Windows (Claude Code brings it), then start the server again."}
            return answer
        if self._out("rev-parse", "--is-inside-work-tree") != "true":
            answer["blocked"] = {"code": "not_a_clone", "message": NOT_A_CLONE}
            return answer
        answer["available"] = True
        answer["branch"] = self._out("rev-parse", "--abbrev-ref", "HEAD")
        answer["head"] = self._commit("HEAD")
        remote_ref = f"{REMOTE}/{BRANCH}"
        if self._out("rev-parse", "--verify", "--quiet", remote_ref) is None:
            return answer
        behind, ahead = self._out("rev-list", "--count", f"HEAD..{remote_ref}"), self._out("rev-list", "--count", f"{remote_ref}..HEAD")
        answer["behind"] = int(behind) if behind and behind.isdigit() else 0
        answer["ahead"] = int(ahead) if ahead and ahead.isdigit() else 0
        if answer["behind"]:
            listed = self._out("log", "-n", "30", f"--format=%h{SEP}%s{SEP}%cI", f"HEAD..{remote_ref}") or ""
            answer["changes"] = [{"short": p[0], "subject": p[1], "date": p[2]} for p in (line.split(SEP) for line in listed.splitlines()) if len(p) == 3]
            packages = self._out("diff", "--name-only", "HEAD", remote_ref, "--", *PACKAGE_FILES) or ""
            answer["packagesChange"] = bool(packages.strip())
        dirty = self._out("status", "--porcelain", "--untracked-files=no") or ""
        answer["dirty"] = [line[3:] for line in dirty.splitlines() if len(line) > 3][:10]
        answer["blocked"] = self._why_not(answer)
        answer["canUpdate"] = answer["behind"] > 0 and answer["blocked"] is None and not self.updating
        return answer

    @staticmethod
    def _why_not(answer: dict[str, Any]) -> dict[str, str] | None:
        if answer["branch"] != BRANCH:
            return {"code": "branch", "message": f"This copy is on the branch {answer['branch'] or 'none'}; updates come to {BRANCH} only. This is a development copy: git does it here."}
        if answer["dirty"]:
            names = ", ".join(answer["dirty"][:3]) + (" and more" if len(answer["dirty"]) > 3 else "")
            return {"code": "dirty", "message": f"Files in this copy were changed by hand ({names}); an update would clash with them. Undo those changes, or update with git yourself."}
        if answer["ahead"]:
            return {"code": "ahead", "message": f"This copy has {answer['ahead']} commit{'s' if answer['ahead'] != 1 else ''} GitHub doesn't have; push them first."}
        return None

    def _fetch(self) -> str | None:
        """Ask GitHub; the error in plain words, or None."""
        code, _out, err = self._git("fetch", "--quiet", REMOTE, BRANCH, timeout=FETCH_TIMEOUT)
        if code != 0:
            words = fetch_trouble(err)
            log.warning("Update check: git fetch failed (%s): %s", code, " ".join(err.split())[:300])
            return words
        return None

    def _check(self, force: bool) -> dict[str, Any]:
        stored = self._stored()
        answer = self._base()
        if self.git is not None and self._enabled() and (force or self._fetch_due(stored)) and self._out("rev-parse", "--is-inside-work-tree") == "true":
            error = self._fetch()
            self._store(checkedAt=_iso(self._clock()), fetchError=error)
            answer = self._base()
        answer = self._local(answer)
        if answer["behind"] and answer["canUpdate"]:
            log.info("Update check: %s new commit%s on GitHub's %s", answer["behind"], "s" if answer["behind"] != 1 else "", BRANCH)
        return answer

    async def status(self, force: bool = False) -> dict[str, Any]:
        if not force and self._answer is not None and time.monotonic() - self._answer[0] < ANSWER_SECONDS:
            return {**self._answer[1], "updating": self.updating}
        async with self._lock:
            answer = await asyncio.to_thread(self._check, force)
            self._answer = (time.monotonic(), answer)
            return answer

    # -- the update ----------------------------------------------------------------------------------------------
    def _apply(self) -> dict[str, Any]:
        answer = self._check(force=True)
        if not answer["available"] or answer["blocked"]:
            blocked = answer["blocked"] or {"code": "unavailable", "message": "This copy can't update itself."}
            raise UpdateRefused(blocked["code"], blocked["message"])
        if answer["error"]:
            raise UpdateRefused("fetch_failed", answer["error"], 502)
        if answer["behind"] <= 0:
            raise UpdateRefused("up_to_date", "Already up to date: GitHub has nothing newer.")
        before = answer["head"]["sha"] if answer["head"] else None
        code, _out, err = self._git("merge", "--ff-only", f"{REMOTE}/{BRANCH}", timeout=MERGE_TIMEOUT)
        if code != 0:
            log.warning("Update: git merge failed (%s): %s", code, " ".join(err.split())[:300])
            raise UpdateRefused("merge_failed", f"git couldn't bring the update in: {' '.join(err.split())[:200] or 'no message'}. Nothing changed.", 500)
        after = self._commit("HEAD")
        sync = answer["packagesChange"]
        if sync:
            try:
                atomic_write(self.marker, json.dumps({"from": before, "to": after["sha"] if after else None, "at": _iso(self._clock())}) + "\n")
            except OSError as exc:
                log.warning("Could not write %s: %s", self.marker, exc)
        record = {"at": _iso(self._clock()), "from": before, "to": after["sha"] if after else None, "count": answer["behind"], "syncNeeded": sync}
        self._store(lastUpdate=record)
        self._answer = None
        log.warning("Updated from GitHub: %s commit%s, %s -> %s%s", answer["behind"], "s" if answer["behind"] != 1 else "", (before or "?")[:7], (record["to"] or "?")[:7], "; the packages sync at the restart" if sync else "")
        return {"updated": True, **{k: record[k] for k in ("from", "to", "count", "syncNeeded")}, "relaunch": relaunch_available(self._environ)}

    async def apply(self) -> dict[str, Any]:
        if self.updating:
            raise UpdateRefused("updating", "An update is already running.")
        async with self._lock:
            self.updating = True
            try:
                return await asyncio.to_thread(self._apply)
            finally:
                self.updating = False
