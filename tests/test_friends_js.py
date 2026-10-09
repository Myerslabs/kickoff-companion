"""Phase 18.6 in the fake browser: Invite friends (the QR and address, the warnings, no network), the board's zoom, a guest's
banner after a PIN is set, and the Not-loaded list staying away from guests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.invite = async () => {
  const { inviteBody, warningsList } = await import(moduleUrl("views/invite.js"));
  const good = inviteBody({ url: "http://192.168.0.20:8642/", qrPath: "/setup/qr.svg?url=http://192.168.0.20:8642/", warnings: ["No host PIN is set."] }, { big: true });
  document.body.append(good);
  const t = text(good);
  assert.ok(!RAW.test(t), t);
  const img = good.querySelector("img.invite__qr");
  assert.ok(img && img.getAttribute("src").startsWith("/setup/qr.svg?url=http://192.168.0.20") && img.className.includes("invite__qr--big"));
  assert.ok(t.includes("http://192.168.0.20:8642/") && t.includes("No host PIN is set."));
  // no network: a sentence instead of a code
  const none = inviteBody({ url: null, qrPath: null, warnings: [] });
  assert.equal(none.querySelector("img"), null);
  assert.ok(text(none).includes("no network address"));
  // a hostile address or path draws nothing
  assert.equal(inviteBody({ url: "javascript:alert(1)", qrPath: "/evil.svg" }).querySelector("img"), null);
  assert.equal(warningsList([]), null);
  assert.equal(warningsList(["a", 5, "", null]).querySelectorAll("li").length, 1);
  assert.ok(!RAW.test(text(inviteBody(null))));
};

scenarios.zoom = async () => {
  const { boardZoom } = await import(moduleUrl("views/board.js"));
  assert.equal(boardZoom(1024), 1);
  assert.equal(boardZoom(1440), 1.3);
  assert.equal(boardZoom(1920), 1.6);
  assert.equal(boardZoom(3840), 2.2);
  assert.equal(boardZoom(NaN), 1);
  assert.equal(boardZoom(undefined), 1);
};

scenarios.guest = async () => {
  const answers = { "/api/host": { data: { pinSet: true, isHost: false, serverComputer: false } }, "/api/invite": { data: { url: "http://192.168.0.20:8642/", copyUrl: null, warnings: [] } } };
  globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => answers[String(url).split("?")[0]] || { data: {} } });
  const { startGuestMode } = await import(moduleUrl("ui/guest.js"));
  const status = await startGuestMode();
  assert.equal(status.pinSet, true);
  assert.equal(document.body.dataset.role, "guest");
  const bar = document.body.querySelector(".guest-bar");
  assert.ok(bar && text(bar).includes("View only") && bar.querySelector("button"));
  // a host (no PIN, or signed in) gets no banner
  document.body.querySelector(".guest-bar").remove();
  answers["/api/host"] = { data: { pinSet: true, isHost: true, serverComputer: false } };
  await startGuestMode();
  assert.equal(document.body.dataset.role, "host");
  assert.equal(document.body.querySelector(".guest-bar"), null);
  // a server that cannot answer leaves the page as it was
  globalThis.fetch = async () => { throw new Error("down"); };
  assert.equal(await startGuestMode(), null);
};

scenarios.readiness = async () => {
  document.body.dataset.role = "guest";
  let asked = 0;
  globalThis.fetch = async () => { asked += 1; return { ok: true, status: 200, json: async () => ({ data: { ready: false, items: [{ id: "season", title: "The 2026 season load", detail: "Not loaded", href: "#preseason" }], serverStartedAt: "t1" } }) }; };
  const { maybeShowReadiness } = await import(moduleUrl("ui/readiness.js"));
  assert.equal(await maybeShowReadiness(), null, "a guest cannot load anything, so no list");
  document.body.dataset.role = "host";
  const sheet = await maybeShowReadiness();
  assert.ok(sheet && text(sheet.layer).includes("The 2026 season load"));
  assert.ok(asked >= 2);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["invite", "zoom", "guest", "readiness"])
def test_friends_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
