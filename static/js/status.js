// Kickoff Companion server status page (served at /status). Phase 0 diagnostics, kept.
// Polls /api/health and renders four states: loading (skeletons), live, stale (last good
// data with its age), and offline (never loaded). Every field is guarded: missing renders as a dash.

const REFRESH_MS = 15000;
const FETCH_TIMEOUT_MS = 8000;
const DASH = "–";

const els = {
  pill: document.getElementById("status-pill"),
  server: document.getElementById("server-facts"),
  checks: document.getElementById("checks-body"),
  tls: document.getElementById("tls-facts"),
  cfbd: document.getElementById("cfbd-facts"),
  quota: document.getElementById("quota-facts"),
  config: document.getElementById("config-facts"),
  published: document.getElementById("published-body"),
  updated: document.getElementById("updated"),
  refresh: document.getElementById("refresh"),
};

const state = { data: null, receivedAt: null, failing: false, inFlight: false };

function text(value) {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : DASH;
  if (typeof value === "boolean") return value ? "yes" : "no";
  const s = String(value).trim();
  return s === "" ? DASH : s;
}

function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function duration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return DASH;
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h} h ${m} min`;
  if (m > 0) return `${m} min ${s} s`;
  return `${s} s`;
}

function bytes(n) {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return DASH;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function localTime(iso) {
  if (typeof iso !== "string" || !iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function setFacts(container, rows) {
  container.replaceChildren();
  for (const [label, value, className] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = text(value);
    if (className) dd.className = className;
    container.append(dt, dd);
  }
}

function localDate(iso) {
  if (typeof iso !== "string" || !iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleDateString([], { dateStyle: "medium" });
}

const PILL_CLASS = { live: "pill--live", degraded: "pill--stale", stale: "pill--stale", offline: "pill--offline", loading: "pill--quiet" };

function setPill(kind, label) {
  els.pill.className = `pill ${PILL_CLASS[kind] || "pill--quiet"}`;
  els.pill.textContent = label;
}

// One breaker lane as [text, class]: the general lane and the live lane read the same way.
function breakerText(raw, reachable) {
  const b = obj(raw);
  if (b.state === "closed") return [`closed, ${reachable}`, ""];
  if (b.state === "open") {
    const retry = typeof b.retry_in_seconds === "number" && Number.isFinite(b.retry_in_seconds) ? Math.round(b.retry_in_seconds) : null;
    return [`open, retry in ${text(retry)} s`, "status-degraded"];
  }
  if (b.state === "half_open") {
    // Half-open covers two cases: a test call is out, or the pause is over and no call has come yet.
    if (b.probe_stuck === true) return [`test call stuck for ${duration(b.probe_seconds)}`, "status-degraded"];
    if (typeof b.probe_seconds === "number" && Number.isFinite(b.probe_seconds)) return ["testing the connection", ""];
    return ["paused; the next call tests the connection", "status-degraded"];
  }
  return [DASH, ""];
}

// The live lane's call count, and its last error when its latest call failed.
function liveCallsText(raw) {
  const lane = obj(raw);
  if (typeof lane.calls !== "number" || !Number.isFinite(lane.calls)) return [DASH, ""];
  const failedAt = typeof lane.last_failure_at === "string" ? lane.last_failure_at : "";
  const okAt = typeof lane.last_success_at === "string" ? lane.last_success_at : "";
  if (failedAt && failedAt > okAt) return [`${lane.calls} this session, last one failed: ${text(lane.last_error)}`, "status-degraded"];
  return [`${lane.calls} this session`, ""];
}

function finishedGamesText(upstream) {
  if (upstream.settling === true) return `kept 1 h until ${localTime(upstream.settle_until)} while the last game settles`;
  if (upstream.settling === false) return "kept permanently once posted, empty answers 10 min";
  return DASH;
}

function renderChecks(checks) {
  els.checks.replaceChildren();
  if (!Array.isArray(checks) || checks.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 3;
    td.className = "note";
    td.textContent = "No checks reported yet. They appear once the server finishes starting.";
    tr.append(td);
    els.checks.append(tr);
    return;
  }
  for (const raw of checks) {
    const check = obj(raw);
    const status = typeof check.status === "string" ? check.status : "";
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = text(check.name);
    const st = document.createElement("td");
    st.className = `status status-${status || "down"}`;
    st.textContent = status === "ok" ? "OK" : status === "degraded" ? "Degraded" : status ? text(status) : DASH;
    const detail = document.createElement("td");
    detail.textContent = text(check.detail);
    tr.append(name, st, detail);
    els.checks.append(tr);
  }
}

function shortTime(iso) {
  if (typeof iso !== "string" || !iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function lateText(minutes) {
  if (typeof minutes !== "number" || !Number.isFinite(minutes)) return "";
  if (minutes < 0) return "";
  if (minutes < 60) return `${minutes} min after`;
  const h = Math.floor(minutes / 60);
  return h < 48 ? `${h} h ${minutes % 60} min after` : `${Math.round(h / 24)} days after`;
}

// Phase 14: the publication schedules and when each source actually changed.
function renderPublished(list) {
  els.published.replaceChildren();
  const rows = Array.isArray(list) ? list.map(obj) : [];
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "note";
    td.textContent = "No schedule reported. The server predates Phase 14 or the publication log could not be read.";
    tr.append(td);
    els.published.append(tr);
    return;
  }
  for (const s of rows) {
    const tr = document.createElement("tr");
    const cell = (value) => {
      const td = document.createElement("td");
      td.textContent = text(value);
      tr.append(td);
      return td;
    };
    cell(s.label);
    cell(shortTime(s.nextSlot));
    const rule = typeof s.recheckMinutes === "number"
      ? `then every ${s.recheckMinutes >= 60 ? `${Math.round(s.recheckMinutes / 60)} h` : `${s.recheckMinutes} min`} until it changes${s.prewarm ? "; the server refreshes it" : ""}`
      : "once per update time";
    cell(`${typeof s.keys === "number" ? `${s.keys} kept; ` : ""}${rule}`);
    const changes = Array.isArray(s.changes) ? s.changes.map(obj).slice(0, 3) : [];
    cell(changes.length ? changes.map((c) => `${text(c.endpoint)} ${shortTime(c.changedAt)}${lateText(c.afterSlotMinutes) ? ` (${lateText(c.afterSlotMinutes)})` : ""}`).join("; ") : "none yet");
    els.published.append(tr);
  }
}

function render(data) {
  const app = obj(data.app);
  const server = obj(data.server);
  const config = obj(data.config);
  const logging = obj(data.logging);
  const files = obj(server.files);

  setFacts(els.server, [
    ["Version", app.version ? `${text(app.version)}, phase ${text(app.phase)}` : DASH],
    ["Machine", server.hostname],
    ["LAN address", server.lan_ip],
    ["Tablet URL", server.tablet_url],
    ["Listening on", server.host && server.port ? `${text(server.host)}:${text(server.port)}` : DASH],
    ["Started", localTime(server.started_at)],
    ["Uptime", duration(server.uptime_seconds)],
    ["Python", server.python],
    ["Program", files.packaged ? `${text(files.program)}${files.portable ? " (portable)" : ""}` : files.install ? "From the project folder (python -m app)" : DASH],
    ["Files", files.install],
    ["Log file", logging.file ? `${text(logging.file)} (${bytes(logging.size_bytes)})` : DASH],
  ]);

  renderChecks(data.checks);
  renderPublished(data.publications);

  const tls = obj(data.tls);
  const ca = obj(tls.ca);
  const cert = obj(tls.server);
  const covers = [
    ...(Array.isArray(cert.dns_names) ? cert.dns_names : []),
    ...(Array.isArray(cert.ip_addresses) ? cert.ip_addresses : []),
  ].map(text).join(", ");
  const connectUrl = document.getElementById("connect-url");
  if (connectUrl) connectUrl.textContent = text(server.tablet_url);
  setFacts(els.tls, tls.enabled === true ? [
    ["HTTPS", "on"],
    ["Certificate authority", ca.name],
    ["CA fingerprint", ca.fingerprint_sha256, "mono"],
    ["Certificate valid until", localDate(cert.not_after)],
    ["Covers", covers],
    ["New device setup", server.setup_url],
  ] : [
    ["HTTPS", tls.enabled === false ? "off: plain HTTP on the home network" : DASH],
    ["Devices", "nothing to install; open the address or scan the code"],
    ["Connect a device", server.setup_url],
  ]);

  const upstream = obj(data.upstream);
  const calls = obj(upstream.stats);
  const cache = obj(data.cache);
  const quota = obj(data.quota);
  const caps = obj(data.capabilities);
  const [generalBreaker, generalClass] = breakerText(upstream.breaker, "CFBD reachable");
  const [liveBreaker, liveClass] = breakerText(upstream.live_breaker, "live calls reachable");
  const [liveCalls, liveCallsClass] = liveCallsText(obj(calls.lanes).live);
  setFacts(els.cfbd, [
    ["API", upstream.base_url],
    ["Circuit breaker", generalBreaker, generalClass],
    ["Live breaker", liveBreaker, liveClass],
    ["Last success", localTime(calls.last_success_at)],
    ["Last error", calls.last_error],
    ["Calls this session", calls.session_calls],
    ["Live calls", liveCalls, liveCallsClass],
    ["Served stale", calls.stale_serves],
    ["Cache", typeof cache.entries === "number" ? `${cache.entries} entries, ${text(cache.fresh)} fresh, ${bytes(cache.db_bytes)} on disk` : DASH],
    ["Cache lifetimes", typeof upstream.ttl_scale === "number" ? `x${upstream.ttl_scale} (budget-scaled)` : DASH],
    ["Finished games", finishedGamesText(upstream)],
  ]);
  const flag = (value) => (value === true ? "available" : value === false ? "not on this tier" : "unknown");
  setFacts(els.quota, [
    ["Tier", caps.tier_name],
    ["Used this month", typeof quota.used === "number" && typeof quota.budget === "number"
      ? `${quota.used.toLocaleString()} of ${quota.budget.toLocaleString()} (${text(quota.pct_used)}%)` : DASH],
    ["Remaining", typeof quota.remaining === "number" ? quota.remaining.toLocaleString() : DASH],
    ["Mode", quota.mode],
    ["Resets", localDate(quota.reset_at)],
    ["Checked with CFBD", quota.reconciled === true ? localTime(quota.reconciled_at) : quota.reconciled === false ? "not yet" : DASH],
    ["Weather", flag(caps.weather)],
    ["Scoreboard", flag(caps.scoreboard)],
    ["Live plays", flag(caps.live_plays)],
  ]);

  const sources = Array.isArray(config.radio_sources)
    ? config.radio_sources.map((s) => text(obj(s).name)).join(", ")
    : "";
  const teamLine = [config.team, config.season]
    .filter((v) => v !== undefined && v !== null && v !== "")
    .map(text)
    .join(" ");
  setFacts(els.config, [
    ["Team", teamLine ? (config.conference ? `${teamLine} (${text(config.conference)})` : teamLine) : DASH],
    ["Time zone", config.timezone],
    ["CFBD key", config.api_key_configured === true ? "configured" : config.api_key_configured === false ? "missing" : DASH],
    ["Settings file", config.env_file],
    ["Monthly call budget", typeof config.monthly_call_budget === "number" ? config.monthly_call_budget.toLocaleString() : DASH],
    ["Hard stop", typeof config.quota_hard_stop_pct === "number" ? `${config.quota_hard_stop_pct}%` : DASH],
    ["Live poll", typeof config.live_poll_seconds === "number" ? `every ${config.live_poll_seconds} s` : DASH],
    ["Radio sources", sources],
    ["DNS name", config.lan_hostname],
    ["Log level", config.log_level],
  ]);
}

function renderOffline() {
  const message = "Could not reach the server. Retrying every 15 s.";
  for (const container of [els.server, els.tls, els.cfbd, els.quota, els.config]) {
    container.replaceChildren();
    const dd = document.createElement("dd");
    dd.className = "note note--error";
    dd.style.gridColumn = "1 / -1";
    dd.textContent = message;
    container.append(dd);
  }
  els.checks.replaceChildren();
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 3;
  td.className = "note note--error";
  td.textContent = message;
  tr.append(td);
  els.checks.append(tr);
}

function ageSeconds() {
  return state.receivedAt ? Math.max(0, Math.round((Date.now() - state.receivedAt) / 1000)) : null;
}

function updateStatusLine() {
  const age = ageSeconds();
  if (state.data && !state.failing) {
    const live = state.data.status === "ok";
    setPill(live ? "live" : "degraded", live ? "Live" : "Degraded");
    els.updated.textContent = age === null ? "Updated just now" : `Updated ${age} s ago`;
  } else if (state.data && state.failing) {
    setPill("stale", age === null ? "Stale" : `Stale ${age} s`);
    els.updated.textContent = `Updated ${age === null ? DASH : `${age} s`} ago. Server not answering. Retrying every 15 s.`;
  } else if (state.failing) {
    setPill("offline", "Offline");
    els.updated.textContent = "Server not reachable. Retrying every 15 s.";
  }
}

async function fetchHealth() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch("/api/health", { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    if (!body || typeof body !== "object" || !body.data || typeof body.data !== "object") {
      throw new Error("Malformed health response");
    }
    return body.data;
  } finally {
    clearTimeout(timer);
  }
}

async function tick() {
  if (state.inFlight) return;
  state.inFlight = true;
  els.refresh.disabled = true;
  try {
    const data = await fetchHealth();
    state.data = data;
    state.receivedAt = Date.now();
    state.failing = false;
    render(data);
    els.pill.classList.remove("flash");
    void els.pill.offsetWidth;
    els.pill.classList.add("flash");
  } catch (err) {
    state.failing = true;
    if (!state.data) renderOffline();
    console.warn("Health refresh failed:", err && err.message ? err.message : err);
  } finally {
    state.inFlight = false;
    els.refresh.disabled = false;
    updateStatusLine();
  }
}

els.refresh.addEventListener("click", () => { void tick(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) void tick(); });
setInterval(() => { void tick(); }, REFRESH_MS);
setInterval(updateStatusLine, 1000);
void tick();
