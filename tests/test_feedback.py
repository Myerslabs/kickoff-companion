"""Feedback with the logs (owner 2026-10-23: "The logs should come with the feedback. I want to be able to see what was
done when feedback was submitted."). Any device sends a report; the server keeps it with the tablet's trail, its own log
of the same fifteen minutes and the status snapshot, one folder a report; only the host reads reports and logs. Nothing
goes to GitHub: a report offers GitHub's own form with the words, the logs stay home. The page in the fake browser: the
trail, the form, the host's list. Since 2026-10-23 (the testers run their own copies) a report reaches the developer like a
crash report: the sender's own mail app, addressed to him, with the summary filled in and home addresses taken out."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import SUPPORT_EMAIL
from app.services.feedback import MAIL_SHORT, FeedbackIn, FeedbackStore, scrub, share_safe
from tests.fakedom import needs_node, run_scenario

NOW = datetime(2026, 10, 24, 15, 30, 0)


def write_log(folder: Path, lines: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def stamp(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")


def test_the_log_window_keeps_the_last_fifteen_minutes_with_their_tracebacks(tmp_path: Path):
    write_log(tmp_path / "logs", [
        f"{stamp(40)} INFO    kickoff.live: an old line",
        f"{stamp(14)} WARNING kickoff.live: the feed was late",
        f"{stamp(2)} ERROR   kickoff.client: something broke",
        "Traceback (most recent call last):",
        "  File \"x.py\", line 1",
        f"{stamp(1)} INFO    kickoff.cfbd: GET /games api_key=abc123 pin=4321",
    ])
    store = FeedbackStore(tmp_path / "data", tmp_path / "logs", clock=lambda: NOW)
    window = store.window_log(NOW)
    assert "an old line" not in window and "the feed was late" in window
    assert "Traceback" in window and 'File "x.py"' in window, "a traceback stays with its line"
    assert "abc123" not in window and "4321" not in window and "api_key=[redacted]" in window


def test_the_log_window_reads_across_the_rotation(tmp_path: Path):
    logs = tmp_path / "logs"
    write_log(logs, [f"{stamp(1)} INFO    kickoff: the newest"])
    (logs / "app.log.1").write_text(f"{stamp(5)} INFO    kickoff: rotated a moment ago\n", encoding="utf-8")
    store = FeedbackStore(tmp_path / "data", logs, clock=lambda: NOW)
    window = store.window_log(NOW).splitlines()
    assert window == [f"{stamp(5)} INFO    kickoff: rotated a moment ago", f"{stamp(1)} INFO    kickoff: the newest"]
    assert store.tail(1) == f"{stamp(1)} INFO    kickoff: the newest"


def test_a_report_keeps_its_damaged_steps_out_and_its_words_in():
    report = FeedbackIn.model_validate({
        "kind": "enhancement", "text": "  The ticker hid the score.  ", "name": "Couch Coordinators", "route": "#live",
        "device": {"width": 820, "height": 1180, "nested": {"no": 1}, "browser": "x" * 400},
        "trail": [{"at": "2026-10-24T19:29:00Z", "kind": "tap", "what": "Big screen"}, {"kind": "tap"}, "junk", {"at": "2026-10-24T19:29:05Z", "kind": "rocket", "what": "?"}],
    })
    assert report.text == "The ticker hid the score." and report.device == {"width": 820, "height": 1180}
    assert [s.what for s in report.trail] == ["Big screen"], "a step without its time, or of no known kind, is dropped"
    assert scrub("Authorization: Bearer xyz") == "Authorization: Bearer [redacted]"


def test_any_device_sends_and_only_the_host_reads(app, client: TestClient):
    logging.getLogger("kickoff.test").warning("a line the report should carry")
    logging.getLogger("kickoff.test").error("the feed at 192.168.1.20 failed")
    sent = client.post("/api/feedback", json={"kind": "bug", "text": "The menu covered the score.", "name": "Pat", "route": "#live", "device": {"width": 820}, "trail": [{"at": "2026-10-24T19:29:00Z", "kind": "page", "what": "#live", "route": "#live"}]})
    assert sent.status_code == 200, sent.text
    summary = sent.json()["data"]
    mail = summary["mail"]
    assert mail["to"] == SUPPORT_EMAIL and "bug: The menu covered the score." in mail["subject"]
    assert "The menu covered the score." in mail["body"] and "page: #live" in mail["body"] and len(mail["body"]) <= MAIL_SHORT
    assert "the feed at [a home address] failed" in mail["full"] and "192.168.1.20" not in mail["full"], "the log's errors go, the home address does not"
    assert summary["canDownload"] is True
    assert summary["kind"] == "bug" and summary["first"] == "The menu covered the score." and summary["trailSteps"] == 1
    folder = app.state.feedback.folder / summary["id"]
    assert sorted(p.name for p in folder.iterdir()) == ["report.json", "server-log.txt", "status.json", "trail.json"]
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["from"] == "host", "no PIN set: every device is the host"
    assert "a line the report should carry" in (folder / "server-log.txt").read_text(encoding="utf-8")
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["version"] and "health" in status and "settings" in status
    assert "cfbd_api_key" not in json.dumps(status) and "test-key" not in json.dumps(status).lower()
    listed = client.get("/api/feedback").json()["data"]["reports"]
    assert [r["id"] for r in listed] == [summary["id"]]
    one = client.get(f"/api/feedback/{summary['id']}").json()["data"]
    assert one["trail"][0]["what"] == "#live" and "a line the report should carry" in one["serverLog"]
    assert one["mail"]["to"] == SUPPORT_EMAIL and "The menu covered the score." in one["mail"]["body"]
    assert "a line the report should carry" in one["mail"]["full"], "the log's warnings go in the mail too (an info line stays home)"
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/feedback/{summary['id']}/zip").content))
    assert sorted(archive.namelist()) == sorted(f"{summary['id']}/{n}" for n in ("report.json", "server-log.txt", "status.json", "trail.json"))
    logs = zipfile.ZipFile(io.BytesIO(client.get("/api/logs/download").content))
    assert "status.json" in logs.namelist() and any(n.startswith("logs/app.log") for n in logs.namelist())
    assert "a line the report should carry" in client.get("/api/logs/tail?lines=50").json()["data"]["text"]
    # a guest (a PIN set, no host cookie, not the server computer) still sends, but reads nothing
    app.state.host_access.set_pin("2468")
    guest = client.post("/api/feedback", json={"kind": "feature", "text": "A dark mode for the board."})
    assert guest.status_code == 200 and json.loads((app.state.feedback.folder / guest.json()["data"]["id"] / "report.json").read_text(encoding="utf-8"))["from"] == "guest"
    for path in ("/api/feedback", f"/api/feedback/{summary['id']}", f"/api/feedback/{summary['id']}/zip", "/api/logs/download", "/api/logs/tail"):
        assert client.get(path).status_code == 403, path


def test_the_mail_is_share_safe_and_fits_a_mail_link(tmp_path: Path):
    text = r"GET http://192.168.1.77:8642/x from kitchen.localdomain C:\Users\pat\app /home/kim/x 10.0.0.5 api_key=abc 8.8.8.8"
    assert share_safe(text) == r"GET http://[a home address]:8642/x from [a computer] C:\Users\[user]\app /home/[user]/x [a home address] api_key=[redacted] 8.8.8.8"
    store = FeedbackStore(tmp_path / "data", tmp_path / "logs", clock=lambda: NOW)
    long_trail = [{"at": "2026-10-24T19:29:00Z", "kind": "tap", "what": "x" * 250} for _ in range(60)]
    report = {"id": "20261024-153000-abcdef", "kind": "feature", "text": "A wish\nwith details", "route": "#live", "device": {"width": 390, "height": 844}, "submittedAt": "2026-10-24T19:30:00-04:00", "trail": long_trail, "serverLog": "\n".join(f"{stamp(1)} ERROR kickoff.x: {'y' * 200}" for _ in range(40))}
    mail = store.mail(report, "9.9.9", "dev@example.com", "Kickoff Companion")
    assert mail["subject"] == "Kickoff Companion 9.9.9 feature: A wish"
    assert len(mail["body"]) <= MAIL_SHORT and mail["body"].startswith("A wish\nwith details"), "a long trail and log are cut to fit the link, the words first"
    assert len(mail["full"]) > len(mail["body"]) and "screen 390x844" in mail["full"]
    assert store.mail({}, "9.9.9", "dev@example.com", "Kickoff Companion")["subject"].endswith("bug: Feedback"), "a damaged report still mails"


def test_bad_reports_and_names_are_refused(app, client: TestClient):
    assert client.post("/api/feedback", json={"kind": "bug", "text": "   "}).status_code == 422
    assert client.post("/api/feedback", json={"kind": "rant", "text": "x"}).status_code == 422
    assert client.post("/api/feedback", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 400
    for name in ("..%2F..%2Fsettings", "20261024-153000-zzzzzz", "nope"):
        assert client.get(f"/api/feedback/{name}").status_code == 404
        assert client.get(f"/api/feedback/{name}/zip").status_code == 404
    folder = app.state.feedback.folder / "20261024-153000-abcdef"
    folder.mkdir(parents=True)
    (folder / "report.json").write_text("{damaged", encoding="utf-8")
    assert client.get("/api/feedback").json()["data"]["skipped"] == 1, "a damaged folder is counted, not fatal"


def test_reports_are_limited_per_device(app, client: TestClient):
    codes = [client.post("/api/feedback", json={"kind": "bug", "text": f"report {i}"}).status_code for i in range(8)]
    assert codes[:6] == [200] * 6 and codes[6] == 429


SCENARIOS = r"""
scenarios.trail = async () => {
  installWindow();
  const { note, trailSteps, labelOf, startTrail } = await import(moduleUrl("ui/trail.js"));
  const button = document.createElement("button");
  button.setAttribute("aria-label", "Big screen");
  assert.equal(labelOf(button), "Big screen");
  const link = document.createElement("a");
  link.textContent = "  Season  ";
  assert.equal(labelOf(link), "Season");
  const row = document.createElement("button");
  const b = document.createElement("b");
  b.textContent = "Send feedback";
  const small = document.createElement("small");
  small.textContent = "a bug, an idea";
  row.append(b, small);
  assert.equal(labelOf(row), "Send feedback", "a two-line row by its title");
  const box = document.createElement("input");
  box.setAttribute("type", "checkbox");
  box.setAttribute("name", "Tray mode");
  box.checked = true;
  assert.equal(labelOf(box), "Tray mode on", "a switch's name and state, never typed words");
  assert.equal(labelOf(null), "");
  startTrail();
  note("tap", "Menu");
  note("error", "x".repeat(500));
  const steps = trailSteps();
  assert.ok(steps.some((s) => s.kind === "page"), "the page it started on");
  assert.equal(steps[steps.length - 1].what.length, 300, "a long message is clipped");
  advance(16 * 60 * 1000);
  assert.equal(trailSteps().length, 0, "fifteen minutes later the old steps are gone");
};

scenarios.form = async () => {
  installWindow();
  const { openFeedback, payload } = await import(moduleUrl("ui/feedback.js"));
  const p = payload({ kind: "rant", text: "  hi  ", name: "x".repeat(60) }, [{ at: "t", kind: "tap", what: "a" }], { width: 820, gone: null });
  assert.deepEqual([p.kind, p.text, p.name.length, p.device], ["bug", "hi", 40, { width: 820 }]);
  const posted = [];
  globalThis.fetch = async (url, init) => {
    posted.push({ url: String(url), body: init && init.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, json: async () => ({ data: { id: "20261024-153000-abcdef", canDownload: true, mail: { to: "dev@example.com", subject: "Kickoff Companion 9.9.9 feature: Show the down", body: "Show the down & distance", full: "Show the down & distance\n\nmore" } } }) };
  };
  openFeedback();
  const form = document.querySelector(".feedback-form");
  assert.ok(form, "the sheet opens with the form");
  const kinds = form.querySelectorAll(".feedback-form__kinds button");
  assert.deepEqual(kinds.map((b) => b.textContent), ["Bug", "Enhancement", "Feature"]);
  kinds[2].click();
  assert.equal(form.querySelector(".feedback-form__ask").textContent, "What would you like it to do?");
  const submit = () => form.dispatchEvent({ type: "submit", preventDefault() {} });
  submit();
  await settle();
  assert.equal(posted.length, 0, "nothing written: nothing sent");
  assert.ok(form.querySelector(".feedback-form__said").textContent.includes("Write a line"));
  form.querySelector(".feedback-form__text").value = "Show the down and distance on the board.";
  submit();
  await settle();
  assert.equal(posted[0].url, "/api/feedback");
  assert.equal(posted[0].body.kind, "feature");
  assert.ok(Array.isArray(posted[0].body.trail));
  const done = document.querySelector(".feedback-done");
  assert.ok(done.textContent.includes("it's saved"));
  const mailLink = done.querySelector(".feedback-mail a.btn--primary");
  assert.equal(mailLink.textContent, "Email it to the developer");
  assert.equal(mailLink.getAttribute("href"), "mailto:dev@example.com?subject=Kickoff%20Companion%209.9.9%20feature%3A%20Show%20the%20down&body=Show%20the%20down%20%26%20distance");
  assert.ok(done.querySelector('a[href="/api/feedback/20261024-153000-abcdef/zip"]'), "the full report to attach");
  assert.ok(done.textContent.includes("Copy the report"));
  const { mailtoHref, openFeedback: open } = await import(moduleUrl("ui/feedback.js"));
  assert.equal(mailtoHref({ to: "not an address", body: "x" }), null);
  assert.equal(mailtoHref(null), null);
  open({ kind: "bug", text: "The Season page could not load: boom" });
  const forms = document.querySelectorAll(".feedback-form");
  assert.equal(forms[forms.length - 1].querySelector("textarea").value, "The Season page could not load: boom", "an error panel fills it in");
};

scenarios.list = async () => {
  installWindow();
  const { feedbackBand } = await import(moduleUrl("ui/feedback.js"));
  const report = { id: "20261024-153000-abcdef", kind: "bug", text: "The menu covered the score.", name: "Pat", from: "guest", route: "#live", submittedAt: "2026-10-24T19:30:00Z", trailSteps: 2, device: { width: 820, height: 1180 },
    trail: [{ at: "2026-10-24T19:29:00Z", kind: "page", what: "#live", route: "#live" }, { at: "2026-10-24T19:29:30Z", kind: "error", what: "boom", route: "#live" }],
    serverLog: "2026-10-24 15:29:31 ERROR kickoff.client: boom", mail: { to: "dev@example.com", subject: "Kickoff Companion bug: The menu", body: "The menu covered the score.", full: "The menu covered the score." } };
  route("/api/feedback", () => envelope({ reports: [{ id: report.id, kind: "bug", first: report.text, name: "Pat", from: "guest", route: "#live", submittedAt: report.submittedAt }], skipped: 0 }));
  route("/api/feedback/20261024", () => envelope(report)); // the later route is asked first
  const section = feedbackBand();
  document.body.append(section);
  await settle();
  const rows = section.querySelectorAll(".feedback-row");
  assert.equal(rows.length, 1);
  assert.ok(rows[0].textContent.includes("The menu covered the score.") && rows[0].textContent.includes("Pat, a guest"));
  assert.ok(section.querySelector('a[href="/api/logs/download"]'), "the logs to download, at the top of the list");
  rows[0].click();
  await settle();
  const view = section.querySelector(".feedback-report");
  assert.ok(view, "the report opens in place");
  assert.equal(view.querySelector('a[href="/api/feedback/20261024-153000-abcdef/zip"]').textContent, "Download the report");
  assert.ok(view.querySelector('a[target="_blank"]').getAttribute("href").startsWith("mailto:dev@example.com?subject="), "Email it from the host's list too");
  assert.equal(view.querySelectorAll(".feedback-trail tbody tr").length, 2);
  assert.ok(view.querySelector(".feedback-trail__error"), "an error stands out");
  assert.ok(view.querySelector(".feedback-report__log pre").textContent.includes("boom"));
  view.querySelector("button").click();
  await settle();
  assert.equal(section.querySelectorAll(".feedback-row").length, 1, "back to the list");
  document.body.dataset.role = "guest";
  const guest = feedbackBand();
  await settle();
  assert.ok(guest.textContent.includes("Reports go to the host"), "a guest is told where reports go");
};
"""


SCENARIOS += r"""
scenarios.crash = async () => {
  installWindow();
  const { errorPanel } = await import(moduleUrl("views/common.js"));
  const panel = errorPanel("Season", "The server answered 500", () => {});
  document.body.append(panel);
  const button = panel.querySelectorAll("button").find((b) => b.textContent === "Send a report");
  assert.ok(button, "an error panel offers a report, like a crash reporter");
  button.click();
  const form = document.querySelector(".feedback-form");
  assert.equal(form.querySelector("textarea").value, "The Season page could not load: The server answered 500");
  assert.equal(form.querySelector('.feedback-form__kinds button[aria-pressed="true"]').textContent, "Bug");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["trail", "form", "list", "crash"])
def test_feedback_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_menu_has_send_feedback_and_profile_the_list() -> None:
    root = Path(__file__).resolve().parents[1] / "static" / "js"
    shell = (root / "ui" / "shell.js").read_text(encoding="utf-8")
    assert "feedbackRow()" in shell and '"Send feedback"' in shell
    app_js = (root / "app.js").read_text(encoding="utf-8")
    assert "onFeedback: () => openFeedback()" in app_js and "startTrail();" in app_js
    assert 'page: "profile=feedback"' in (root / "ui" / "menu-tree.js").read_text(encoding="utf-8")
    assert '{ id: "feedback", title: "Feedback"' in (root / "views" / "settings.js").read_text(encoding="utf-8")
