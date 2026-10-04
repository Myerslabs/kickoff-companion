"""Public release Phase 9b: a fresh install starts in the demo. The start mode (data/startup.json) picks the demo or
this install's own team; the demo page explains the key, that nothing goes to Myers Labs and nothing is paid to it,
and switches each way with a restart in place; the README says the same."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import cli, restart, startmode
from app.config import load_settings
from tests.conftest import TEST_KEY

ROOT = Path(__file__).resolve().parent.parent
PRIVACY = "nothing is sent to Myers Labs"
PLANS = "CFBD's paid plans are paid to CFBD, not to us, and they only unlock more data"


@pytest.fixture(autouse=True)
def no_restart_left():
    yield
    restart.reset()


def fresh(tmp_path: Path, **values):
    return load_settings(env_file=None, data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"), **values)


# --- the start mode ----------------------------------------------------------------------------------------


def test_a_fresh_install_starts_the_demo_and_a_set_up_one_its_team(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    assert startmode.start_mode(fresh(tmp_path, cfbd_api_key="", team="", conference="")) == startmode.DEMO
    assert startmode.start_mode(fresh(tmp_path, cfbd_api_key=TEST_KEY, team="Swampwater Tech", conference="Biscuit Belt")) == startmode.APP


def test_a_saved_choice_wins_and_a_broken_file_falls_back(tmp_path: Path):
    settings = fresh(tmp_path, cfbd_api_key=TEST_KEY)
    startmode.save_mode(settings.data_dir, startmode.DEMO)
    assert startmode.start_mode(settings) == startmode.DEMO
    startmode.save_mode(settings.data_dir, startmode.APP)
    assert startmode.start_mode(settings) == startmode.APP
    startmode.mode_path(settings.data_dir).write_text("{not json", encoding="utf-8")
    assert startmode.start_mode(settings) == startmode.APP
    startmode.mode_path(settings.data_dir).write_text('{"mode": "party"}', encoding="utf-8")
    assert startmode.saved_mode(settings.data_dir) is None
    with pytest.raises(ValueError):
        startmode.save_mode(settings.data_dir, "party")


def test_the_cli_serves_the_demo_then_the_app_after_a_switch(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"DATA_DIR={(tmp_path / 'data').as_posix()}\nLOG_DIR={(tmp_path / 'logs').as_posix()}\n", encoding="utf-8")
    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    seen: list[tuple[str, object, bool]] = []

    def fake_demo(settings, *, open_url=None, restarting=False):
        seen.append(("demo", open_url, restarting))
        startmode.save_mode(settings.data_dir, startmode.APP)  # "Use my own team"
        return restart.RESTART

    def fake_app(settings, *, reload=False, open_url=None, restarting=False, asgi=None):
        seen.append(("app", open_url, restarting))
        return 0

    monkeypatch.setattr("app.demo.run.serve_embedded", fake_demo)
    monkeypatch.setattr("app.serving.run_server", fake_app)
    monkeypatch.setattr("app.cli.browser_url", lambda settings, *, no_browser, login: "http://localhost:8642/")
    assert cli.main([], env_file=env) == 0
    assert seen == [("demo", "http://localhost:8642/demo", False), ("app", None, True)]  # the demo page opens first; the setup app after


# --- the demo page and the switch --------------------------------------------------------------------------


def test_in_the_app_the_demo_is_one_click_away(app, client: TestClient):
    state = client.get("/api/demo").json()["data"]
    assert state["demo"] is False and state["configured"] is True and state["publisher"] == "Myers Labs"
    assert client.post("/api/demo/leave").status_code == 409
    entered = client.post("/api/demo/enter").json()["data"]
    assert entered["restarting"] is True and entered["next"] == "demo" and restart.requested()
    assert startmode.saved_mode(app.state.settings.data_dir) == startmode.DEMO
    page = client.get("/demo")
    assert page.status_code == 200 and PRIVACY in page.text and PLANS in page.text and "Use my own team" in page.text


def test_in_the_demo_use_my_own_team_saves_the_choice_at_home(tmp_path: Path):
    import httpx

    from app.demo.run import SimClock, build, next_game
    from app.demo.upstream import load_world
    from tests.conftest import league

    world = league()
    game = next_game(world)
    home = tmp_path / "home-data"
    application, asgi, _upstream, _settings = build(world, SimClock(game.slot.start, 1.0), tmp_path / "demo-data", 8655, "127.0.0.1", 2, None)
    application.state.demo_mode = True
    application.state.home_data_dir = home
    application.state.home_configured = False
    assert callable(load_world) and httpx  # the demo's own pieces import cleanly
    with TestClient(application, base_url="http://testserver") as client:
        client.portal.call(application.state.live.stop_background)
        state = client.get("/api/demo").json()["data"]
        assert state["demo"] is True and state["configured"] is False
        assert client.post("/api/demo/enter").status_code == 409
        left = client.post("/api/demo/leave").json()["data"]
        assert left["next"] == "app" and restart.requested()
    assert startmode.saved_mode(home) == startmode.APP
    assert not (tmp_path / "demo-data" / startmode.MODE_FILE).exists()  # the choice goes home, never into the demo's scratch folder


def test_setup_mode_lets_the_demo_page_through(tmp_path: Path, monkeypatch):
    from app.main import create_app

    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    settings = fresh(tmp_path, cfbd_api_key="", team="", conference="")
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        assert client.get("/demo").status_code == 200 and client.get("/api/demo").status_code == 200
        welcome = client.get("/welcome").text
        assert 'href="/demo"' in welcome and PRIVACY in welcome


def test_the_readme_and_the_menu_say_the_same():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert PRIVACY in readme and PLANS in readme and "**Use my own team**" in readme and "**demo**" in readme
    shell = (ROOT / "static/js/ui/shell.js").read_text(encoding="utf-8")
    assert '{ id: "demo", label: "Demo", href: "/demo"' in shell
    app_js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    assert "showDemoBanner(page);" in app_js
