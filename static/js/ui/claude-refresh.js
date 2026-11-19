// Run with Claude (batch 4 part 3, owner 2026-11-19: "the clauder run button is hard to find unless it tells you. I want to
// make it easier"; "Let's just add it in the top layer of the menu"). One row at the top of the menu's opening level, on
// any page Claude Code wrote something on ("any with claude on it"), while that page's window is open. A tap starts one run
// on the server that reads what the page already holds and refreshes it ("Each run should see what is in the current page
// and refresh it with updated info, or additional info"): out of date corrected or removed, the new added, never a section
// emptied. The loading bar above the page follows it (ui/run-bar.js), and the To do says when the new data is in. The
// server keeps a log of what each run changed; the app does not show it ("leave a log somewhere, but dont show it").
// Never for a guest; hidden where Claude Code's command is not found.
//
//   refreshState(route)  -> Promise<{ available, label, detail } | null>   GET /api/refresh?route=...
//   startRefresh(route)  -> Promise<{ ok, error }>                         POST /api/refresh/run { route }
//   refreshRow({ route, onStart })  -> <button> the menu's row, hidden until the server says the page can refresh

import { el, text } from "./dom.js";
import { icon } from "./icons.js";
import { watchRun } from "./run-bar.js";
import { addNote } from "./page-notes.js";

const isGuest = () => typeof document !== "undefined" && document.body?.dataset?.role === "guest";

export async function refreshState(route) {
  if (isGuest()) return null;
  try {
    const response = await fetch(`/api/refresh?route=${encodeURIComponent(String(route || ""))}`, { cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) return null;
    const body = await response.json();
    const data = body && typeof body.data === "object" && body.data ? body.data : null;
    if (!data) return null;
    return { available: data.available === true, running: data.running === true, label: typeof data.label === "string" ? data.label : "", detail: typeof data.detail === "string" ? data.detail : "" };
  } catch (error) {
    console.warn("Could not ask whether this page can refresh.", error?.message || error);
    return null;
  }
}

export async function startRefresh(route) {
  try {
    const response = await fetch("/api/refresh/run", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ route: String(route || "") }) });
    const body = await response.json().catch(() => null);
    const data = body && typeof body.data === "object" && body.data ? body.data : {};
    const said = Array.isArray(body?.errors) && typeof body.errors[0]?.message === "string" ? body.errors[0].message : null;
    if (!response.ok || data.error) return { ok: false, error: (typeof data.error === "string" && data.error) || said || `The server said ${response.status}.` };
    return { ok: true, error: null };
  } catch (error) {
    return { ok: false, error: "The server could not be reached." };
  }
}

/** The menu's row: drawn hidden, shown once the server says this page has something of Claude's to refresh. */
export function refreshRow({ route, onStart } = {}) {
  const small = el("small", {}, "Refresh what Claude wrote on this page");
  const row = el(
    "button",
    { class: "drawer__item drawer__group-row drawer__claude", type: "button", hidden: true },
    el("span", { class: "drawer__icon", "aria-hidden": "true" }, icon("refresh")),
    el("span", { class: "drawer__words" }, el("b", {}, "Run with Claude"), small),
  );
  if (isGuest()) return row;
  refreshState(route).then((state) => {
    if (!state || !state.available) return;
    if (state.detail) small.textContent = text(state.detail);
    if (state.running) {
      row.disabled = true;
      small.textContent = "Running now: the bar above the page follows it";
    }
    row.removeAttribute("hidden");
  });
  row.addEventListener("click", async () => {
    row.disabled = true;
    small.textContent = "Starting…";
    const result = await startRefresh(route);
    if (typeof onStart === "function") onStart(result);
    if (result.ok) {
      watchRun();
      return;
    }
    row.disabled = false;
    small.textContent = result.error;
    addNote({ id: "claude-refresh", title: "Run with Claude did not start", body: () => el("p", {}, result.error), leaveWithPage: true });
  });
  return row;
}
