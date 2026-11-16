// The Seasons list (rollover R2, owner 2026-11-15: "A Seasons list", "The book and its games"): this season, then each
// season before it with what was kept when the app moved on (/api/seasons, no CFBD call). A past season opens its season in
// review as kept (#review=<year>), its schedule leading to each game's kept Pre-Game and Post-Game and its Archive game. Under
// the list, the switch: the app moves to the next season by itself once our season is closed out, the national title game
// is final and CFBD lists our next schedule; it looks once a day and says here what it is waiting for.

import { el, fmtDate, isNum, records, text } from "../ui/dom.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { band, note } from "../ui/states.js";
import { errorPanel, poller } from "./common.js";

function day(iso) {
  return typeof iso === "string" && isNum(Date.parse(iso)) ? fmtDate(iso) : null;
}

function seasonRow(row) {
  const year = isNum(row.season) ? row.season : null;
  if (year === null) return null;
  if (row.current === true) {
    return el(
      "li",
      { class: "seasons__row seasons__row--now" },
      el("b", { class: "seasons__year" }, String(year)),
      el("span", { class: "seasons__what" }, "This season"),
      el("span", { class: "seasons__links" }, el("a", { class: "btn btn--quiet", href: "#season" }, "My Team"), el("a", { class: "btn btn--quiet", href: "#review" }, "The season in review so far")),
    );
  }
  const games = isNum(row.games) ? row.games : 0;
  const kept = day(row.keptAt);
  const what = row.book === true ? `The season in review, kept${kept ? ` ${kept}` : ""} · ${games} ${games === 1 ? "game" : "games"} closed out` : `${games} ${games === 1 ? "game" : "games"} kept; the season in review was not kept`;
  return el(
    "li",
    { class: "seasons__row" },
    el("b", { class: "seasons__year" }, String(year)),
    el("span", { class: "seasons__what" }, what),
    el("span", { class: "seasons__links" }, row.book === true ? el("a", { class: "btn", href: `#review=${year}` }, `Open ${year}`) : el("a", { class: "btn btn--quiet", href: "#archive" }, "The Archive")),
  );
}

function switchBody(sw, current) {
  const next = isNum(sw?.next) ? sw.next : current + 1;
  const lines = [el("p", {}, `The app moves to ${next} by itself once our ${current} season is closed out, the national title game is final and CFBD lists our ${next} schedule. It looks once a day, and restarts itself when it moves.`)];
  if (!sw || typeof sw !== "object") {
    lines.push(note("The switch is off in the test league."));
    return el("div", { class: "seasons__switch" }, ...lines);
  }
  const checked = typeof sw.checkedOn === "string" && sw.checkedOn ? fmtDate(`${sw.checkedOn}T12:00:00`) : null;
  if (typeof sw.error === "string" && sw.error) lines.push(note(text(sw.error), { kind: "error" }));
  else if (isNum(sw.due)) lines.push(el("p", { class: "seasons__state" }, text(sw.waiting) || `The switch to ${sw.due} is due; it is made at the next hourly check.`));
  else if (checked) lines.push(el("p", { class: "seasons__state" }, `Last looked ${checked}: ${text(sw.waiting) || "nothing to do yet."}`));
  else lines.push(el("p", { class: "seasons__state" }, "Not looked yet: the first look comes with the next hourly housekeeping."));
  const moves = records(sw.switched);
  if (moves.length) lines.push(el("ul", { class: "seasons__moves" }, ...moves.slice(-3).reverse().map((m) => el("li", {}, `Moved from ${text(m.from)} to ${text(m.to)}${day(m.at) ? ` on ${day(m.at)}` : ""}.`))));
  return el("div", { class: "seasons__switch" }, ...lines);
}

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const current = isNum(data.current) ? data.current : null;
  const rows = records(data.seasons).map(seasonRow).filter(Boolean);
  const page = el(
    "div",
    { class: "page seasons" },
    band({
      id: "seasons-list",
      title: "Seasons",
      collapsible: false,
      summary: rows.length > 1 ? `${rows.length} seasons` : "this season so far",
      state: rows.length ? { status: "ready" } : { status: "empty", message: "No season to list yet." },
      body: () => el("div", {}, el("ul", { class: "seasons__list" }, ...rows), rows.length === 1 ? note("Earlier seasons show here once the app has moved on from them: each keeps its season in review and its games.") : null),
    }),
    current !== null ? band({ id: "seasons-switch", title: "The next season", collapsible: false, foldable: true, state: { status: "ready" }, body: () => switchBody(data.switch, current) }) : null,
  );
  stopFlow(state.ui);
  container.replaceChildren(page);
  mountFlow(state.ui, container, page, { chips: false });
}

export function createSeasonsView({ onStatus } = {}) {
  const state = { ui: {} };
  const view = poller({
    url: "/api/seasons",
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Seasons", message, retry)),
    renderLoading: () => el("div", { class: "page seasons" }, band({ title: "Seasons", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "skel skel--block" }) })),
    loadingDetail: "The seasons kept on this computer",
  });
  return { ...view, unmount() { stopFlow(state.ui); view.unmount(); } };
}
