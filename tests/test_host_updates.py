"""FEAT-13 and BUG-22 (owner 2026-10-26): a host can run the app from a clone of the repository.
The app asks GitHub for new commits on main (here a bare repository on disk, so nothing leaves the computer), brings them
in only on a tap, asks the launcher to sync the packages when they changed, and restarts in a fresh process, which is
what loads new Python code. On a first start it offers to bring over the packaged install's files."""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import restart
from app.config import load_settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import public_import
from app.services.updates import FETCH_SECONDS, GitUpdater, UpdateRefused, fetch_trouble, find_git
from tests.conftest import TEST_KEY, FakeCfbd

ROOT = Path(__file__).resolve().parents[1]
GIT = find_git()
needs_git = pytest.mark.skipif(GIT is None, reason="git is not installed here")


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run([GIT, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "init.defaultBranch=main", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, name: str, body: str, message: str) -> str:
    (repo / name).write_text(body, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path):
    """origin (bare, standing in for GitHub), host (the host's clone) and dev (where the work is pushed from)."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    dev = tmp_path / "dev"
    git(tmp_path, "clone", "-q", str(origin), str(dev))
    git(dev, "checkout", "-q", "-b", "main")
    commit(dev, "app.py", "x = 1\n", "The first version")
    commit(dev, "uv.lock", "lock 1\n", "Pin the packages")
    git(dev, "push", "-q", "origin", "main")
    host = tmp_path / "host"
    git(tmp_path, "clone", "-q", str(origin), str(host))
    return origin, host, dev


def updater(host: Path, tmp_path: Path, **kw) -> GitUpdater:
    return GitUpdater(host, tmp_path / "data", git=GIT, environ={}, **kw)


def counting(target: GitUpdater) -> list[list[str]]:
    seen: list[list[str]] = []
    real = target._run

    def run(args: list[str], timeout: float):
        seen.append(args[1:])
        return real(args, timeout)

    target._runner = run
    return seen


@needs_git
def test_up_to_date_then_new_commits_on_github(repos, tmp_path: Path):
    _origin, host, dev = repos
    up = updater(host, tmp_path)
    now = asyncio.run(up.status(force=True))
    assert now["available"] and now["branch"] == "main" and now["behind"] == 0 and now["canUpdate"] is False and now["blocked"] is None
    assert now["head"]["subject"] == "Pin the packages" and now["error"] is None and now["checkedAt"]
    commit(dev, "app.py", "x = 2\n", "Show every team")
    git(dev, "push", "-q", "origin", "main")
    later = asyncio.run(up.status(force=True))
    assert later["behind"] == 1 and later["canUpdate"] is True and later["packagesChange"] is False
    assert [c["subject"] for c in later["changes"]] == ["Show every team"]


@needs_git
def test_a_tap_brings_the_update_in_and_a_package_change_asks_for_a_sync(repos, tmp_path: Path):
    _origin, host, dev = repos
    up = updater(host, tmp_path)
    commit(dev, "app.py", "x = 3\n", "New code")
    newest = commit(dev, "uv.lock", "lock 2\n", "New packages")
    git(dev, "push", "-q", "origin", "main")
    done = asyncio.run(up.apply())
    assert done["updated"] and done["count"] == 2 and done["to"] == newest and done["syncNeeded"] is True and done["relaunch"] is False
    assert git(host, "rev-parse", "HEAD") == newest and (host / "app.py").read_text(encoding="utf-8") == "x = 3\n"
    marker = json.loads((tmp_path / "data" / "update-sync.json").read_text(encoding="utf-8"))
    assert marker["to"] == newest
    after = asyncio.run(up.status(force=True))
    assert after["behind"] == 0 and after["syncPending"] is True and after["lastUpdate"]["count"] == 2
    with pytest.raises(UpdateRefused) as nothing:
        asyncio.run(up.apply())
    assert nothing.value.code == "up_to_date"


@needs_git
def test_a_copy_changed_by_hand_on_a_branch_or_ahead_is_never_updated(repos, tmp_path: Path):
    _origin, host, dev = repos
    commit(dev, "app.py", "x = 4\n", "More")
    git(dev, "push", "-q", "origin", "main")
    up = updater(host, tmp_path)
    (host / "app.py").write_text("changed by hand\n", encoding="utf-8")
    dirty = asyncio.run(up.status(force=True))
    assert dirty["behind"] == 1 and dirty["canUpdate"] is False and dirty["blocked"]["code"] == "dirty" and "app.py" in dirty["blocked"]["message"]
    with pytest.raises(UpdateRefused) as refused:
        asyncio.run(up.apply())
    assert refused.value.code == "dirty" and (host / "app.py").read_text(encoding="utf-8") == "changed by hand\n", "nothing overwritten"
    git(host, "checkout", "-q", "--", "app.py")
    git(host, "checkout", "-q", "-b", "work")
    assert asyncio.run(up.status(force=True))["blocked"]["code"] == "branch"
    git(host, "checkout", "-q", "main")
    commit(host, "local.txt", "mine\n", "A local commit")
    ahead = asyncio.run(up.status(force=True))
    assert ahead["ahead"] == 1 and ahead["blocked"]["code"] == "ahead"


@needs_git
def test_github_is_asked_at_most_once_an_hour_and_never_when_off(repos, tmp_path: Path):
    _origin, host, _dev = repos
    clock = [datetime(2026, 10, 26, 12, tzinfo=timezone.utc)]
    up = updater(host, tmp_path, clock=lambda: clock[0])
    seen = counting(up)
    asyncio.run(up.status())
    up._answer = None
    asyncio.run(up.status())
    assert sum(args[0] == "fetch" for args in seen) == 1, "the second look within the hour asks only git on this computer"
    clock[0] += timedelta(seconds=FETCH_SECONDS + 1)
    up._answer = None
    asyncio.run(up.status())
    assert sum(args[0] == "fetch" for args in seen) == 2
    off = updater(host, tmp_path / "off", enabled=lambda: False)
    off_seen = counting(off)
    assert asyncio.run(off.status(force=True))["enabled"] is False and not any(args[0] == "fetch" for args in off_seen)


@needs_git
def test_a_fetch_that_fails_says_why_and_a_folder_without_git_says_so(repos, tmp_path: Path):
    _origin, host, _dev = repos
    git(host, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    broken = asyncio.run(updater(host, tmp_path).status(force=True))
    assert broken["available"] and broken["error"] and broken["canUpdate"] is False
    plain = tmp_path / "plain"
    plain.mkdir()
    assert asyncio.run(updater(plain, tmp_path / "p").status(force=True))["blocked"]["code"] == "not_a_clone"
    nogit = updater(host, tmp_path / "n")
    nogit.git = None
    assert asyncio.run(nogit.status(force=True))["blocked"]["code"] == "no_git"


def test_gits_refusals_in_plain_words():
    assert "sign in to GitHub" in fetch_trouble("fatal: could not read Username for 'https://github.com': terminal prompts disabled")
    assert "sign in to GitHub" in fetch_trouble("remote: Repository not found.")
    assert "no internet" in fetch_trouble("fatal: unable to access 'https://github.com/': Could not resolve host: github.com")
    assert fetch_trouble("").startswith("git fetch failed")


@needs_git
def test_the_routes_update_on_a_tap_and_restart(repos, tmp_path: Path, settings, fake_cfbd, monkeypatch):
    _origin, host, dev = repos
    commit(dev, "app.py", "x = 5\n", "Every game")
    git(dev, "push", "-q", "origin", "main")
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, updates_root=host)
    application.state.updates.git = GIT
    try:
        with TestClient(application, base_url="https://testserver") as tc:
            tc.portal.call(application.state.live.stop_background)
            data = tc.get("/api/updates?force=1").json()["data"]
            assert data["behind"] == 1 and data["canUpdate"] is True and data["changes"][0]["subject"] == "Every game"
            assert tc.post("/api/updates/apply", content="confirm=true").status_code in (415, 422), "a plain form is refused"
            assert tc.post("/api/updates/apply", json={}).json()["errors"][0]["code"] == "confirm"
            monkeypatch.setattr("app.api.server._game_under_way", lambda request: True)
            assert tc.post("/api/updates/apply", json={"confirm": True}).status_code == 409, "not while our game is on, unless forced"
            monkeypatch.setattr("app.api.server._game_under_way", lambda request: False)
            monkeypatch.setattr("app.api.server._last", {"at": 0.0})
            done = tc.post("/api/updates/apply", json={"confirm": True})
            assert done.status_code == 200 and done.json()["data"]["restarting"] is True and done.json()["data"]["count"] == 1
            assert restart.requested() and "GitHub" in restart.requested()
            assert (host / "app.py").read_text(encoding="utf-8") == "x = 5\n"
    finally:
        shutdown_logging()
        restart.reset()


def test_the_test_league_server_still_builds_and_never_asks_github(tmp_path: Path, monkeypatch):
    """The page check's server: create_app's arguments changed with FEAT-13 and app/demo/run.py was left passing the old
    updates_transport, so the page check found no server at all (2026-10-26)."""
    import os

    from app.demo import run
    from tests.conftest import league

    monkeypatch.setattr(os, "environ", dict(os.environ))  # build() clears the settings' names from the environment
    world = league()
    clock = run.SimClock(run.next_game(world).slot.start, 1.0)
    application, _asgi, _upstream, settings = run.build(world, clock, tmp_path / "demo", 8650, "127.0.0.1", 2, None)
    assert settings.team == "Florida" and application.state.updates._enabled() is False
    assert asyncio.run(application.state.updates.status(force=True))["enabled"] is False


# --- BUG-22: a restart under a launcher is a fresh process -------------------------------------------------------------


def test_a_restart_under_a_launcher_exits_for_a_fresh_process(tmp_path: Path, monkeypatch):
    from app import cli

    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"CFBD_API_KEY={TEST_KEY}\nTEAM=Florida\nCONFERENCE=SEC\nDATA_DIR={(tmp_path / 'data').as_posix()}\nLOG_DIR={(tmp_path / 'logs').as_posix()}\n", encoding="utf-8")
    seen: list[dict] = []

    def fake_run(settings, **kwargs):
        seen.append(kwargs)
        return restart.RESTART

    monkeypatch.setattr("app.serving.run_server", fake_run)
    monkeypatch.setenv("KICKOFF_RELAUNCH", "1")
    assert cli.main(["--no-browser"], env_file=env) == restart.RELAUNCH == 8
    assert len(seen) == 1, "the launcher serves again, not this process"
    seen.clear()
    monkeypatch.setattr("app.serving.run_server", lambda settings, **kwargs: seen.append(kwargs) or 0)
    assert cli.main(["--restarted"], env_file=env) == 0
    assert seen[0]["open_url"] is None and seen[0]["restarting"] is True, "started again: no browser, and the port may need a moment"


def test_the_launchers_start_the_server_again_and_sync_first_when_asked():
    tray = (ROOT / "tools" / "tray.ps1").read_text(encoding="utf-8")
    assert "$Relaunch = 8" in tray and '$env:KICKOFF_RELAUNCH = "1"' in tray and "Start-Server -Restarted" in tray
    assert 'sync --frozen --quiet --no-dev --inexact' in tray and "update-sync.json" in tray and "[string]$Uv" in tray
    start = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert '$env:KICKOFF_RELAUNCH = "1"' in start and "while ($code -eq 8)" in start and "& $python -m app --restarted" in start
    assert ' -Uv `"$uv`"' in start and "update-sync.json" in start


# --- bringing over the packaged install -------------------------------------------------------------------------------


def public_install(local: Path) -> Path:
    source = local / "Kickoff Companion"
    (source / "data" / "archive").mkdir(parents=True)
    (source / "data" / "notes").mkdir()
    (source / "data" / "demo").mkdir()
    (source / ".env").write_text(f'# the packaged program\nCFBD_API_KEY={TEST_KEY}\nTEAM="Florida"\nCONFERENCE=SEC\nPORT=8642\nDATA_DIR=\nLOG_DIR=logs\n', encoding="utf-8")
    (source / "data" / "archive" / "401.json").write_text("{}", encoding="utf-8")
    (source / "data" / "notes" / "401.json").write_text("{}", encoding="utf-8")
    (source / "data" / "notes" / "_example.json").write_text("{}", encoding="utf-8")
    (source / "data" / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    (source / "data" / "kickoff.db").write_bytes(b"sqlite")
    (source / "data" / "demo" / "league.pickle").write_bytes(b"pickle")
    return source


def test_the_public_install_is_found_summed_up_and_copied_once(tmp_path: Path):
    local = tmp_path / "Local"
    source = public_install(local)
    assert public_import.find_public({"LOCALAPPDATA": str(local)}) == source
    assert public_import.find_public({"LOCALAPPDATA": str(tmp_path / "nowhere")}) is None
    seen = public_import.summary(source)
    assert seen["team"] == "Florida" and seen["hasKey"] and seen["archive"] == 1 and seen["notes"] == 1 and seen["files"] == 4
    env = tmp_path / "project" / ".env"
    env.parent.mkdir()
    env.write_text("PORT=8650\nTEAM=\n", encoding="utf-8")
    data = tmp_path / "project" / "data"
    done = public_import.copy_into(source, env, data)
    assert done["copied"] == 4 and done["skipped"] == 0 and done["envKeys"] == ["CFBD_API_KEY", "CONFERENCE", "TEAM"]
    copied = public_import.read_env(env)
    assert copied["PORT"] == "8650", "a setting this install has stays" and copied["TEAM"] == "Florida"
    assert "DATA_DIR" not in copied and "LOG_DIR" not in copied
    assert (data / "archive" / "401.json").is_file() and json.loads((data / "settings.json").read_text(encoding="utf-8"))["theme"] == "dark"
    assert not (data / "kickoff.db").exists() and not (data / "demo").exists(), "the open cache and the test league stay behind"


def test_the_welcome_page_offers_it_in_setup_mode_and_brings_it_over(tmp_path: Path, monkeypatch):
    local = tmp_path / "Local"
    public_install(local)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    env = tmp_path / ".env"
    settings = load_settings(env_file=env, cfbd_api_key="", team="", conference="", log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"))
    fake = FakeCfbd()
    fake.fixture("/teams/fbs", "teams_fbs")
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake.transport)
    try:
        with TestClient(application, base_url="http://testserver") as tc:
            offer = tc.get("/api/welcome").json()["data"]["publicInstall"]
            assert offer["team"] == "Florida" and offer["archive"] == 1
            done = tc.post("/api/welcome/import", json={"confirm": True})
            assert done.status_code == 200 and done.json()["data"]["restarting"] is True and restart.requested()
            assert "TEAM=Florida" in env.read_text(encoding="utf-8") and (tmp_path / "data" / "archive" / "401.json").is_file()
    finally:
        shutdown_logging()
        restart.reset()
    welcome = (ROOT / "static" / "js" / "welcome.js").read_text(encoding="utf-8")
    assert '"/api/welcome/import"' in welcome and "Bring over its settings and data" in welcome
