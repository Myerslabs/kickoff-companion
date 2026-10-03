// The Phase 6 debug page: start and stop a replay, set the delay, watch the delayed state arrive
// over the event stream. Plain and small; the real live sheet is Phase 7.

import { DASH, el, fmtClock, period, text } from "./ui/dom.js";
import { pill } from "./ui/pills.js";
import { playLog } from "./ui/play-log.js";

const els = {
  pill: document.getElementById("pill"),
  game: document.getElementById("game"),
  speed: document.getElementById("speed"),
  delay: document.getElementById("delay"),
  delayValue: document.getElementById("delay-value"),
  start: document.getElementById("start"),
  stop: document.getElementById("stop"),
  reconnect: document.getElementById("reconnect"),
  note: document.getElementById("note"),
  engine: document.getElementById("engine"),
  state: document.getElementById("state"),
  plays: document.getElementById("plays"),
};

let source = null;
let us = { name: DASH, abbr: DASH };
let them = { name: DASH, abbr: DASH };

function setPill(kind, label) {
  els.pill.replaceWith(pill({ kind, label }));
  els.pill = document.querySelector(".topbar .pill");
}

function facts(container, rows) {
  container.replaceChildren(...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, text(v))]));
}

async function json(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.errors?.[0]?.message || `HTTP ${response.status}`);
  return body;
}

async function loadGames() {
  try {
    const body = await json("/api/season/overview");
    const games = (body.data?.schedule || []).filter((g) => g.completed);
    els.game.replaceChildren(...games.map((g) => el("option", { value: g.gameId }, `Week ${g.week}: ${g.homeAway === "home" ? "vs" : "at"} ${g.opponent?.school} (${g.result} ${g.usPoints}-${g.themPoints})`)));
    if (!games.length) els.game.append(el("option", { value: "" }, "No finished games yet"));
  } catch (error) {
    els.note.textContent = `Could not load the schedule: ${error.message}`;
  }
}

function renderState(state) {
  if (!state) return;
  const ourSchool = typeof state.team === "string" && state.team ? state.team : state.home;
  us = { name: ourSchool, abbr: ourSchool ? ourSchool.slice(0, 4).toUpperCase() : DASH };
  const other = state.home === ourSchool ? state.away : state.home;
  them = { name: other || DASH, abbr: other ? other.slice(0, 3).toUpperCase() : DASH };
  facts(els.state, [
    ["Mode", state.mode],
    ["Status", state.status],
    ["Score", `${text(state.home)} ${text(state.homeScore)}, ${text(state.away)} ${text(state.awayScore)}`],
    ["Clock", `${period(state.period)} ${fmtClock(state.clock)}`],
    ["Possession", `${text(state.possession)} · ${text(state.down)} & ${text(state.distance)} at ${text(state.yardsToGoal)}`],
    ["Released", `${state.counts?.plays} plays, ${state.counts?.drives} drives, ${state.counts?.events} events, last seq ${state.lastSeq}`],
    ["Held back by delay", state.pending ? "yes, more is waiting" : "no"],
    ["Last play success", state.lastPlay ? `${state.lastPlay.success ? "success" : "failed"}: ${text(state.lastPlay.text)}` : DASH],
    ["New this tick", (state.new || []).length],
  ]);
  els.plays.replaceChildren(playLog({ plays: state.plays || [], us, them, maxHeight: 460 }));
}

async function refreshEngine() {
  try {
    const body = await json("/api/live/status");
    const e = body.data;
    facts(els.engine, [
      ["Mode", e.mode],
      ["Game", e.gameId],
      ["Window", e.window ? `${e.window.open ? "open" : "closed"}, kickoff ${e.window.kickoff}` : "none"],
      ["Live plays on this key", e.livePlaysAvailable ? "yes" : "no (Tier 2 needed)"],
      ["Clients connected", e.clientsConnected ? "yes" : "no"],
      ["Poll", `${e.pollSeconds} s, about ${e.projectedCallsPerGame} calls per game`],
      ["Replay", e.replay.running ? `running ${e.replay.emitted} of ${e.replay.total} at ${e.replay.speed}x` : e.replay.finished ? `finished, ${e.replay.emitted} events` : e.replay.error || "idle"],
      ["Stored events", e.stats.eventsStored],
      ["Polls / failures", `${e.stats.polls} / ${e.stats.poll_failures}`],
      ["Last error", e.stats.last_error || DASH],
    ]);
  } catch (error) {
    facts(els.engine, [["Error", error.message]]);
  }
}

function connect() {
  if (source) source.close();
  const delay = Number(els.delay.value);
  source = new EventSource(`/api/live/stream?delay=${delay}`);
  setPill("quiet", "Connecting");
  source.addEventListener("hello", () => setPill(delay ? "delayed" : "live", delay ? `Delayed ${delay} s` : "Live"));
  source.addEventListener("state", (event) => {
    try {
      renderState(JSON.parse(event.data));
    } catch (error) {
      els.note.textContent = `Bad state event: ${error.message}`;
    }
  });
  source.onerror = () => setPill("offline", "Reconnecting");
}

els.delay.addEventListener("input", () => {
  els.delayValue.textContent = `${els.delay.value} s`;
});
els.delay.addEventListener("change", connect);
els.reconnect.addEventListener("click", connect);
els.start.addEventListener("click", async () => {
  els.note.textContent = "";
  try {
    const body = await json("/api/live/replay", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gameId: Number(els.game.value), speed: Number(els.speed.value) }) });
    els.note.textContent = `Replay started: game ${body.data.gameId} at ${body.data.speed}x.`;
  } catch (error) {
    els.note.textContent = `Replay refused: ${error.message}`;
  }
  refreshEngine();
});
els.stop.addEventListener("click", async () => {
  await json("/api/live/replay", { method: "DELETE" }).catch(() => null);
  refreshEngine();
});

loadGames();
refreshEngine();
connect();
setInterval(refreshEngine, 5000);
