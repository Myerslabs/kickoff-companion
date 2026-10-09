"""Phase 18.2: keep-awake, backups, packed recordings, the archive's second look, the clock changes."""

from __future__ import annotations

import asyncio
import json
import os
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.cfbd import publish
from app.config import default_season
from app.maintenance import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, KeepAwake, Maintenance, backup_data, last_backup, tidy_recordings
from app.services.archive import ArchiveService

NOW = datetime(2026, 10, 10, 5, 0, tzinfo=timezone.utc)


def test_keep_awake_on_windows_sets_and_clears_the_hold_once():
    calls: list[int] = []
    awake = KeepAwake(platform="win32", state_call=calls.append)
    awake.set(False)
    assert calls == []  # nothing held, nothing to clear
    awake.set(True)
    awake.set(True)
    awake.set(False)
    assert calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED, ES_CONTINUOUS]
    assert awake.held is False


def test_keep_awake_on_a_mac_holds_a_child_and_ends_it():
    child = SimpleNamespace(terminated=False)
    child.terminate = lambda: setattr(child, "terminated", True)
    awake = KeepAwake(platform="darwin", spawn=lambda: child)
    awake.set(True)
    assert awake.held and not child.terminated
    awake.release()
    assert child.terminated and not awake.held


def test_keep_awake_elsewhere_does_nothing_and_says_so_once(caplog):
    awake = KeepAwake(platform="linux")
    with caplog.at_level("INFO", logger="kickoff.maintenance"):
        awake.set(True)
        awake.set(True)
    assert not awake.held and not awake.supported
    assert sum("not supported" in r.message for r in caplog.records) == 1


def test_keep_awake_survives_a_failing_call():
    def boom(_flags: int) -> None:
        raise OSError("no")

    awake = KeepAwake(platform="win32", state_call=boom)
    awake.set(True)
    assert awake.held is False


def make_data(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    (data / "archive").mkdir(parents=True)
    (data / "archive" / "1.json").write_text('{"gameId":1}', encoding="utf-8")
    (data / "notes").mkdir()
    (data / "notes" / "1.json").write_text("{}", encoding="utf-8")
    (data / "season" / "2026").mkdir(parents=True)
    (data / "season" / "2026" / "coaches.json").write_text("{}", encoding="utf-8")
    (data / "feeds").mkdir()
    (data / "feeds" / "season-2026.json").write_text("{}", encoding="utf-8")
    (data / "feeds" / "espn.json").write_text("{}", encoding="utf-8")
    (data / "settings.json").write_text("{}", encoding="utf-8")
    (data / "certs").mkdir()
    (data / "certs" / "ca-key.pem").write_text("SECRET", encoding="utf-8")
    (data / "headshots").mkdir()
    (data / "headshots" / "9.png").write_bytes(b"x")
    return data


def test_backup_holds_what_cannot_be_fetched_again_and_nothing_secret(tmp_path):
    data = make_data(tmp_path)
    target = backup_data(data, tmp_path / "b", 7, NOW)
    with zipfile.ZipFile(target) as bundle:
        names = set(bundle.namelist())
    assert names == {"archive/1.json", "notes/1.json", "season/2026/coaches.json", "feeds/season-2026.json", "settings.json"}
    assert target.name == "kickoff-data-20261010.zip"
    assert not list((tmp_path / "b").glob("*.tmp"))


def test_backup_keeps_only_the_newest_and_replaces_today(tmp_path):
    data = make_data(tmp_path)
    for day in range(1, 6):
        backup_data(data, tmp_path / "b", 3, NOW.replace(day=day))
    backup_data(data, tmp_path / "b", 3, NOW.replace(day=5))
    assert [p.name for p in sorted((tmp_path / "b").glob("*.zip"))] == ["kickoff-data-20261003.zip", "kickoff-data-20261004.zip", "kickoff-data-20261005.zip"]


def maintenance(tmp_path: Path, *, window=False, enabled=True, clock=None, refresh=None) -> Maintenance:
    return Maintenance(data_dir=make_data(tmp_path), backup_dir=tmp_path / "b", keep=7, window_open=lambda: window, backups_enabled=lambda: enabled, clock=clock or (lambda: NOW.astimezone()), refresh_archive=refresh, awake=KeepAwake(platform="linux"))


def test_backup_is_due_at_once_when_there_is_none_then_after_four_in_the_morning(tmp_path):
    m = maintenance(tmp_path)
    local = datetime(2026, 10, 10, 1, 0).astimezone()
    assert m.backup_due(local)  # none yet: made at once
    asyncio.run(m.run_backup())
    assert not m.backup_due(datetime.now().astimezone())  # one today
    tomorrow_early = (datetime.now().astimezone() + timedelta(days=1)).replace(hour=2)
    tomorrow_late = tomorrow_early.replace(hour=5)
    assert not m.backup_due(tomorrow_early) and m.backup_due(tomorrow_late)
    assert not maintenance(tmp_path / "x", enabled=False).backup_due(local)


def test_a_backup_that_cannot_be_written_is_reported_not_raised(tmp_path):
    m = maintenance(tmp_path)
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the folder should go", encoding="utf-8")
    m.backup_dir = blocker / "b"
    assert asyncio.run(m.run_backup()) is None
    assert "could not be written" in m.status()["error"]


def test_tick_holds_awake_only_inside_a_window_and_runs_the_jobs(tmp_path):
    calls: list[int] = []
    refreshed: list[datetime] = []

    async def refresh(now):
        refreshed.append(now)

    m = maintenance(tmp_path, window=True)
    m.awake = KeepAwake(platform="win32", state_call=calls.append)
    asyncio.run(m.tick())
    assert m.awake.held and calls and last_backup(m.backup_dir) is not None
    m.window_open = lambda: False
    m.refresh_archive = refresh
    m._last_slow = None
    asyncio.run(m.tick())
    assert not m.awake.held and len(refreshed) == 1  # the archive's second look never runs inside a game window


def test_recordings_of_archived_old_games_are_packed_and_others_kept(tmp_path):
    data = tmp_path / "data"
    live, archive = data / "live", data / "archive"
    archive.mkdir(parents=True)
    for gid in ("11", "22", "33"):
        (live / gid).mkdir(parents=True)
        (live / gid / "plays-1.json").write_text("{}", encoding="utf-8")
    (archive / "11.json").write_text("{}", encoding="utf-8")
    (archive / "33.json").write_text("{}", encoding="utf-8")
    old = time.time() - 30 * 86400
    for gid in ("11", "22"):
        os.utime(live / gid / "plays-1.json", (old, old))
    packed = tidy_recordings(live, archive, datetime.now().astimezone())
    assert packed == [11]  # 22 has no archive file; 33 is recent
    assert not (live / "11").exists() and (live / "11.zip").is_file() and (live / "22").is_dir() and (live / "33").is_dir()
    with zipfile.ZipFile(live / "11.zip") as bundle:
        assert bundle.namelist() == ["plays-1.json"]


class FakeCache:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.restored: list[str] = []

    def delete(self, key: str) -> None:
        self.deleted.append(key)

    def get(self, key: str):  # the final pass keeps the entries aside; this fake holds none
        return None

    def put(self, key: str, *args, **kwargs) -> None:
        self.restored.append(key)


def archive_service(tmp_path: Path, games: list[SimpleNamespace]) -> tuple[ArchiveService, FakeCache, list[int]]:
    cache = FakeCache()
    fetched: list[int] = []
    service = ArchiveService.__new__(ArchiveService)
    service.folder = tmp_path / "archive"
    service.folder.mkdir()
    service.team = "Alpha"
    service.analytics = SimpleNamespace(client=SimpleNamespace(cache=cache), settings=SimpleNamespace(season=2026))

    async def schedule():
        return games

    async def game(game_id):
        fetched.append(game_id)

    service._schedule = schedule
    service.game = game
    for g in games:
        (service.folder / f"{g.id}.json").write_text(json.dumps({"gameId": g.id, "state": {}}), encoding="utf-8")
    return service, cache, fetched


def a_game(game_id: int, start: datetime, completed: bool = True) -> SimpleNamespace:
    return SimpleNamespace(id=game_id, home_team="Alpha", away_team="Beta", week=5, season_type="regular", start_date=start.isoformat().replace("+00:00", "Z"), completed=completed)


def test_archive_refresh_drops_the_cached_answers_once_two_days_after_kickoff(tmp_path):
    games = [a_game(1, NOW - timedelta(days=3)), a_game(2, NOW - timedelta(hours=20)), a_game(3, NOW - timedelta(days=5), completed=False)]
    service, cache, fetched = archive_service(tmp_path, games)
    assert asyncio.run(service.refresh_finished(NOW)) == [1]
    assert fetched == [1]
    assert "/game/box/advanced?id=1" in cache.deleted and any(k.startswith("/games/teams?") for k in cache.deleted)
    assert asyncio.run(service.refresh_finished(NOW)) == []  # once only
    assert asyncio.run(service.refresh_finished(NOW + timedelta(days=2))) == [2]


def test_archive_refresh_survives_a_failing_game_and_tries_again_later(tmp_path):
    service, _cache, _fetched = archive_service(tmp_path, [a_game(1, NOW - timedelta(days=3))])

    async def broken(_game_id):
        raise RuntimeError("down")

    service.game = broken
    assert asyncio.run(service.refresh_finished(NOW)) == []
    assert service._refreshed() == {}


# --- the clock changes -----------------------------------------------------------------------------------------


def test_eastern_slots_follow_the_clock_change():
    # Daylight time ends Sunday 2026-11-01 at 2 a.m.: 6 a.m. Eastern is 10:00 UTC the week before, 11:00 UTC after.
    before = publish._eastern(date(2026, 10, 25), 6)
    after = publish._eastern(date(2026, 11, 1), 6)
    assert before.astimezone(timezone.utc).hour == 10 and after.astimezone(timezone.utc).hour == 11
    assert after.astimezone(ZoneInfo("America/New_York")).hour == 6


def test_the_season_rolls_over_in_march_not_january():
    assert default_season(date(2027, 1, 20)) == 2026  # bowls and the title game
    assert default_season(date(2027, 2, 28)) == 2026
    assert default_season(date(2027, 3, 1)) == 2027
    assert default_season(date(2026, 12, 31)) == 2026
