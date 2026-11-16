"""One request per address (batch 1, owner 2026-11-15, "Every page in ~1.5 s"): bands asking for the same answer side by side
share one request while it runs, a page's own load and Refresh start their own, every caller has its own copy, a caller's
signal ends only its own wait, and the last caller to let go cancels the request. Runs under Node
(GitHub's test run; skipped where Node is not installed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.shared = async () => {
  const { fetchJson } = await import(moduleUrl("views/common.js"));
  let n = 0;
  let open = null;
  route("/api/thing", () => new Promise((resolve) => { n += 1; open = () => resolve(envelope({ n, list: [1, 2] })); }));
  const a = fetchJson("/api/thing");
  const b = fetchJson("/api/thing");
  await settle();
  assert.equal(n, 1, "two bands side by side: one request");
  open();
  const [ea, eb] = await Promise.all([a, b]);
  assert.equal(ea.data.n, 1);
  assert.equal(eb.data.n, 1);
  ea.data.list.push(3);
  assert.deepEqual(eb.data.list, [1, 2], "each caller its own copy");
  const later = fetchJson("/api/thing");
  await settle();
  assert.equal(n, 2, "once answered, the next ask is a request of its own");
  open();
  await later;
};

scenarios.fresh = async () => {
  const { fetchJson } = await import(moduleUrl("views/common.js"));
  let n = 0;
  const opens = [];
  route("/api/page", () => new Promise((resolve) => { n += 1; const mine = n; opens.push(() => resolve(envelope({ n: mine }))); }));
  const band = fetchJson("/api/page");
  const page = fetchJson("/api/page", null, { fresh: true });
  await settle();
  assert.equal(n, 2, "a page's own load or Refresh never joins a request already running");
  const another = fetchJson("/api/page");
  await settle();
  assert.equal(n, 2, "a band asking after joins the page's request");
  opens.forEach((open) => open());
  const answers = await Promise.all([band, page, another]);
  assert.deepEqual(answers.map((e) => e.data.n), [1, 2, 2]);
};

scenarios.abort = async () => {
  const { fetchJson } = await import(moduleUrl("views/common.js"));
  let n = 0;
  let open = null;
  route("/api/slow", () => new Promise((resolve) => { n += 1; open = () => resolve(envelope({ n })); }));
  const controller = new AbortController();
  const mine = fetchJson("/api/slow", controller.signal);
  const theirs = fetchJson("/api/slow");
  await settle();
  controller.abort();
  let name = null;
  try {
    await mine;
  } catch (error) {
    name = error.name;
  }
  assert.equal(name, "AbortError", "the caller that let go stops waiting");
  open();
  assert.equal((await theirs).data.n, 1, "the other band still gets the shared answer");
  assert.equal(n, 1);
  // the last caller to let go cancels the request itself, as a card closing did before
  const real = globalThis.fetch;
  let seen = null;
  globalThis.fetch = (url, options) => { seen = options && options.signal; return new Promise(() => {}); };
  try {
    const alone = new AbortController();
    const waiting = fetchJson("/api/held", alone.signal).catch((error) => error.name);
    await settle();
    alone.abort();
    assert.equal(await waiting, "AbortError");
    assert.ok(seen && seen.aborted, "nobody waits any more: the request is cancelled");
  } finally {
    globalThis.fetch = real;
  }
  // the review (2026-11-16): a request every caller let go is never joined; the next page's band starts afresh
  let asked = 0;
  route("/api/left", () => { asked += 1; return asked === 1 ? new Promise(() => {}) : envelope({ asked }); });
  const leaving = new AbortController();
  const first = fetchJson("/api/left", leaving.signal).catch((error) => error.name);
  await settle();
  leaving.abort();
  assert.equal(await first, "AbortError");
  const next = await fetchJson("/api/left");
  assert.equal(next.data.asked, 2, "a fresh request, not the cancelled one");
  let count = 0;
  route("/api/alone", () => { count += 1; return envelope({ count }); });
  await Promise.all([fetchJson("/api/alone", null, { shared: false }), fetchJson("/api/alone", null, { shared: false })]);
  assert.equal(count, 2, "a request of its own (a patient wait's next round) never joins another");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["shared", "fresh", "abort"])
def test_one_request_per_address_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
