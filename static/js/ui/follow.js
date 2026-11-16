// In Game for any game (FEAT-1, owner 2026-10-25: "see every team the way I see my team"). The live engine follows one
// game: ours, or another the host picks with Watch it live. These are the two ends of that choice.
//
//   followButton(game, team)   "Watch it live" for another team's game on its day (null otherwise): In Game follows it
//   followingLine(live)        on In Game while it follows another game (the state's team is not ours): which one, and
//                              Back to our game
//   watchable(game, now)       whether a game is this week's (to come within eight days, or under way) and can be followed
//                              (owner 2026-11-02, "see it for any team": the twelve-hour rule went with Pick a game)

import { usSchool } from "../identity.js";
import { el, isNum, text } from "./dom.js";

const BEFORE_MS = 8 * 24 * 3600 * 1000; // any game of the week: up to eight days before kickoff (the pregame screen until plays arrive)
const AFTER_MS = 5 * 3600 * 1000; // to five hours after it

async function send(method, body) {
  const response = await fetch("/api/live/follow", { method, cache: "no-store", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  return envelope?.data || null;
}

export function watchable(game, now = Date.now()) {
  if (!game || typeof game !== "object" || game.completed === true) return false;
  const kickoff = Date.parse(String(game.kickoff || ""));
  return Number.isFinite(kickoff) && now >= kickoff - BEFORE_MS && now <= kickoff + AFTER_MS;
}

export function followButton(game, team, now = Date.now()) {
  const id = game?.gameId;
  if (!(isNum(id) || /^\d{1,12}$/.test(String(id ?? ""))) || !watchable(game, now)) return null;
  const said = el("span", { class: "note", role: "status" }, "");
  const button = el("button", { class: "btn btn--primary", type: "button", onclick: async () => {
    button.disabled = true;
    said.textContent = "Switching In Game…";
    try {
      await send("POST", { gameId: Number(id), team: typeof team === "string" ? team : null });
      window.location.hash = "live";
    } catch (error) {
      said.textContent = `Not switched: ${text(error?.message)}.`;
      button.disabled = false;
    }
  } }, "Watch it live");
  return el("span", { class: "follow-game" }, button, " ", said);
}

export function followingLine(live) {
  const team = typeof live?.team === "string" ? live.team : null;
  const ours = usSchool();
  if (!team || !ours || team === ours) return null;
  const followed = { team, home: typeof live.home === "string" ? live.home : null, away: typeof live.away === "string" ? live.away : null };
  const said = el("span", { class: "note", role: "status" }, "");
  const back = el("button", { class: "btn btn--quiet", type: "button", onclick: async () => {
    back.disabled = true;
    try {
      await send("DELETE");
      said.textContent = "Back to our game.";
    } catch (error) {
      said.textContent = `Not switched: ${text(error?.message)}.`;
      back.disabled = false;
    }
  } }, `Back to ${usSchool() || "our"}'s game`);
  const match = followed.away && followed.home ? `${text(followed.away)} at ${text(followed.home)}` : "another game";
  return el("p", { class: "following-line", role: "note" }, el("span", {}, `Watching ${match}, from ${text(followed.team)}'s side.`), " ", back, " ", said);
}
