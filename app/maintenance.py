"""The server's housekeeping (Phase 18.2): the jobs that keep a season of game days safe without anyone watching.

    KeepAwake       the PC does not go to sleep while it is plugged in (ENH-32), or during a game window only (Windows)
    backup_data     one zip of what cannot be fetched again (archive, notes, season notes, settings), newest N kept
    tidy_recordings raw live recordings of archived games, packed into one zip each once they are old
    Maintenance     one loop that runs all of the above, plus the archive refresh, on their own schedules

Nothing here polls CFBD except the archive refresh, which asks for one game once, two days after its kickoff.
Every job logs what it did and survives its own failure: a failed backup is a warning and a red line in Settings.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("kickoff.maintenance")

# --- keep the computer awake ---------------------------------------------------------------------------------

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
AWAKE_MODES = ("plugged", "games", "off")  # ENH-32 (owner 2026-10-27): Server Settings, "plugged" by default


def windows_plugged_in() -> bool | None:
    """True on mains power, False on battery, None when Windows cannot say (GetSystemPowerStatus)."""
    import ctypes

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):  # type: ignore[attr-defined]
        return None
    return {0: False, 1: True}.get(status.ACLineStatus)  # 255 is "unknown"


class KeepAwake:
    """Holds the computer awake while `active` is true. The request belongs to the calling thread, so every call comes
    from the server's event-loop thread. Windows only since ENH-26 (owner 2026-10-25); elsewhere it says once that it
    cannot and does nothing.

    ENH-32 (owner 2026-10-27): `wanted(mode, window_open)` says whether to hold. "plugged" holds whenever the computer is
    on mains power and never on battery, even on game day (his answer); "games" holds during a game window only, the
    behavior before; "off" never holds. A computer that cannot say how it is powered (a desktop without a battery
    reports it as plugged in) counts as plugged in."""

    def __init__(self, platform: str | None = None, state_call: Callable[[int], Any] | None = None, power_call: Callable[[], bool | None] | None = None) -> None:
        self.platform = platform or sys.platform
        self._state_call = state_call
        self._power_call = power_call
        self.held = False
        self._said = False
        self.mode = "games"
        self.plugged: bool | None = None
        self.reason = "not checked yet"

    def _windows_call(self, flags: int) -> Any:
        if self._state_call is not None:
            return self._state_call(flags)
        import ctypes

        return ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))  # type: ignore[attr-defined]

    @property
    def supported(self) -> bool:
        return self.platform.startswith("win")

    def plugged_in(self) -> bool | None:
        if not self.supported:
            return None
        try:
            return (self._power_call or windows_plugged_in)()
        except (OSError, AttributeError, ValueError) as exc:
            log.warning("Could not read how the computer is powered: %s", exc)
            return None

    def wanted(self, mode: Any, window_open: bool) -> bool:
        self.mode = mode if mode in AWAKE_MODES else "plugged"
        if self.mode == "off":
            self.reason = "off in Server Settings"
            return False
        if self.mode == "games":
            self.reason = "a game window is open" if window_open else "no game window open"
            return window_open
        self.plugged = self.plugged_in()
        if self.plugged is False:
            self.reason = "on battery"
            return False
        self.reason = "plugged in"
        return True

    def set(self, active: bool) -> None:
        if active == self.held:
            return
        if not self.supported:
            if active and not self._said:
                self._said = True
                log.info("Keeping the computer awake is not supported on %s; turn off its sleep timer.", self.platform)
            return
        try:
            self._windows_call(ES_CONTINUOUS | ES_SYSTEM_REQUIRED if active else ES_CONTINUOUS)
        except (OSError, AttributeError, ValueError) as exc:
            log.warning("Could not %s the computer's sleep hold: %s", "set" if active else "clear", exc)
            return
        self.held = active
        log.info("Computer %s (%s).", "is being kept awake" if active else "may sleep again", self.reason)

    def release(self) -> None:
        self.set(False)

    def status(self) -> dict[str, Any]:
        return {"supported": self.supported, "holding": self.held, "mode": self.mode, "pluggedIn": self.plugged, "reason": self.reason}


# --- backup --------------------------------------------------------------------------------------------------

BACKUP_DIRS = ("archive", "notes", "season", "wiki", "gamenotes", "claude")  # folders of data/ that nothing can fetch again (rollover R1: Claude's lessons and ledger)
BACKUP_FILES = ("settings.json", "startup.json", "facts.json", "jobs.json", "trivia.json")  # rollover R1: the facts, the jobs' runs and the trivia too
BACKUP_PREFIX = "kickoff-data-"


def _backup_members(data_dir: Path) -> list[Path]:
    members: list[Path] = []
    for name in BACKUP_DIRS:
        folder = data_dir / name
        if folder.is_dir():
            members += [p for p in folder.rglob("*") if p.is_file()]
    members += [data_dir / n for n in BACKUP_FILES if (data_dir / n).is_file()]
    feeds = data_dir / "feeds"
    if feeds.is_dir():
        members += [p for p in feeds.glob("season-*.json") if p.is_file()]  # the Newspaper's season of headlines
    members += [p for p in data_dir.glob("trivia-*.json") if p.is_file()]  # rollover R1: a past season's trivia, set aside
    return members


def backup_data(data_dir: Path, backup_dir: Path, keep: int, now: datetime) -> Path:
    """Write kickoff-data-YYYYMMDD.zip into backup_dir (replacing today's), then drop all but the newest `keep`.
    Written to a temporary name and renamed, so a crash never leaves a half zip that looks whole."""
    data_dir, backup_dir = Path(data_dir), Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{BACKUP_PREFIX}{now:%Y%m%d}.zip"
    fd, tmp_name = tempfile.mkstemp(prefix="backup-", suffix=".tmp", dir=str(backup_dir))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in _backup_members(data_dir):
                with contextlib.suppress(OSError):  # a file that vanished mid-run is skipped; the next night catches it
                    bundle.write(path, path.relative_to(data_dir).as_posix())
        tmp.replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    old = sorted(backup_dir.glob(f"{BACKUP_PREFIX}*.zip"))
    for stale in old[: max(0, len(old) - max(1, keep))]:
        with contextlib.suppress(OSError):
            stale.unlink()
    return target


def last_backup(backup_dir: Path) -> tuple[Path, datetime] | None:
    try:
        files = sorted(Path(backup_dir).glob(f"{BACKUP_PREFIX}*.zip"))
        if not files:
            return None
        return files[-1], datetime.fromtimestamp(files[-1].stat().st_mtime).astimezone()
    except OSError:
        return None


# --- raw recordings ------------------------------------------------------------------------------------------


def tidy_recordings(live_dir: Path, archive_dir: Path, now: datetime, older_than: timedelta = timedelta(days=14)) -> list[int]:
    """Pack each recorded game's folder into data/live/<id>.zip once its archive file exists and the folder is older
    than `older_than`, then remove the folder. A game without an archive file is kept as it is: the recordings are
    the only copy of what happened."""
    packed: list[int] = []
    live_dir, archive_dir = Path(live_dir), Path(archive_dir)
    if not live_dir.is_dir():
        return packed
    cutoff = now.timestamp() - older_than.total_seconds()
    for folder in sorted(p for p in live_dir.iterdir() if p.is_dir() and p.name.isdigit()):
        if not (archive_dir / f"{folder.name}.json").is_file():
            continue
        files = [p for p in folder.rglob("*") if p.is_file()]
        if not files or max(p.stat().st_mtime for p in files) > cutoff:
            continue
        target = live_dir / f"{folder.name}.zip"
        tmp = live_dir / f"{folder.name}.zip.tmp"
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as bundle:
                for path in files:
                    bundle.write(path, path.relative_to(folder).as_posix())
            tmp.replace(target)
            shutil.rmtree(folder)
        except OSError as exc:
            log.warning("Could not pack the recordings of game %s: %s", folder.name, exc)
            with contextlib.suppress(OSError):
                tmp.unlink()
            continue
        packed.append(int(folder.name))
        log.info("Packed %d recordings of game %s into %s", len(files), folder.name, target.name)
    return packed


# --- the loop ------------------------------------------------------------------------------------------------

TICK_SECONDS = 60
START_DELAY_SECONDS = 30
BACKUP_HOUR = 4
SLOW_JOB_SECONDS = 3600


class Maintenance:
    def __init__(
        self,
        *,
        data_dir: Path,
        backup_dir: Path,
        keep: int,
        window_open: Callable[[], bool],
        backups_enabled: Callable[[], bool],
        refresh_archive: Callable[[datetime], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        awake: KeepAwake | None = None,
        lock_program: Callable[[datetime], Any] | None = None,
        lock_postgame: Callable[[datetime], Any] | None = None,
        warm: Callable[[datetime], Any] | None = None,
        awake_mode: Callable[[], Any] | None = None,
        weekly: Callable[[datetime], Any] | None = None,
        rollover: Callable[[datetime], Any] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir)
        self.keep = keep
        self.window_open = window_open
        self.backups_enabled = backups_enabled
        self.refresh_archive = refresh_archive
        self.lock_program = lock_program  # wave B: the Pre-Game Program locked at kickoff, checked every tick
        self.lock_postgame = lock_postgame  # F8 feature 1: the Post-Game Program locked once the poll after the game is out
        self.warm = warm  # ENH-27: the nightly warm, paced to the month's target; it decides itself when it is due
        self.weekly = weekly  # Feature Set v2: the weekly jobs (Talent Edge first), Sundays from 6 AM; they decide when they are due
        self.rollover = rollover  # rollover R2: the season's switch, checked once a day; a due switch tries each hour until it is made
        self._clock = clock or (lambda: datetime.now().astimezone())
        self.awake = awake or KeepAwake()
        self.awake_mode = awake_mode or (lambda: "games")  # ENH-32: the Server Settings switch, read every tick
        self.backup_error: str | None = None
        self._last_slow: float | None = None
        self._task: asyncio.Task[Any] | None = None

    def backup_due(self, now: datetime) -> bool:
        if not self.backups_enabled():
            return False
        latest = last_backup(self.backup_dir)
        if latest is not None and latest[1].date() == now.date():
            return False
        return now.hour >= BACKUP_HOUR or latest is None  # the first one is made at once; after that, the small hours

    def status(self) -> dict[str, Any]:
        latest = last_backup(self.backup_dir)
        return {
            "enabled": self.backups_enabled(),
            "folder": str(self.backup_dir),
            "keep": self.keep,
            "last": latest[1].isoformat(timespec="minutes") if latest else None,
            "lastFile": latest[0].name if latest else None,
            "error": self.backup_error,
            "keepAwake": self.awake.status(),
        }

    async def run_backup(self) -> Path | None:
        now = self._clock()
        try:
            path = await asyncio.to_thread(backup_data, self.data_dir, self.backup_dir, self.keep, now)
        except (OSError, zipfile.BadZipFile) as exc:
            reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
            self.backup_error = f"The backup could not be written to {self.backup_dir}: {reason}"
            log.warning("%s", self.backup_error)
            return None
        self.backup_error = None
        log.info("Backup written: %s", path)
        return path

    async def tick(self) -> None:
        self.awake.set(self.awake.wanted(self.awake_mode(), bool(self.window_open())))
        if self.lock_program is not None:
            try:
                await self.lock_program(self._clock())
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("Locking the program at kickoff failed")
        if self.lock_postgame is not None:
            try:
                await self.lock_postgame(self._clock())
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("Locking the Post-Game Program failed")
        loop_now = asyncio.get_running_loop().time()
        if self._last_slow is not None and loop_now - self._last_slow < SLOW_JOB_SECONDS:
            return
        self._last_slow = loop_now
        now = self._clock()
        if self.backup_due(now):
            await self.run_backup()
        try:
            await asyncio.to_thread(tidy_recordings, self.data_dir / "live", self.data_dir / "archive", now)
        except OSError:
            log.exception("Tidying the recordings failed")
        if self.refresh_archive is not None and not self.window_open():
            try:
                await self.refresh_archive(now)
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("Archive refresh failed")
        if self.warm is not None and not self.window_open():
            try:
                pending = self.warm(now)
                if pending is not None:
                    await pending
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("The nightly warm failed")
        if self.weekly is not None and not self.window_open():
            try:
                pending = self.weekly(now)
                if inspect.isawaitable(pending):  # the server starts the run in the background and hands back its record
                    await pending
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("The weekly jobs failed")
        if self.rollover is not None and not self.window_open():
            try:
                pending = self.rollover(now)
                if inspect.isawaitable(pending):
                    await pending
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("The season's switch failed")

    async def _loop(self) -> None:
        await asyncio.sleep(START_DELAY_SECONDS)  # let the server finish starting before the first housekeeping
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("A housekeeping job failed; the loop continues")
            await asyncio.sleep(TICK_SECONDS)

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        if self._task is None or self._task.done() or self._task.get_loop() is not loop:  # an app served twice gets a fresh loop task
            self._task = loop.create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            if task.get_loop() is asyncio.get_running_loop():
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self.awake.release()
