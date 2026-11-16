// The Circle of Blame (FEAT-18, Feature Set v2 Phase C). The owner's board of 2026-10-30
// "Build as drawn": Claude Code's weekly red-team report on us, the
// blame for how the team is playing split 4 to 6 ways. Five bands, each its own flyout and page (FEAT-15), in the menu's
// New until he places it:
//   the wheel      a donut, an arc a slice by its share, colored by its kind (ten fixed colors, the legend under it), the
//                  slices listed beside it (the biggest selected), the verdict in bold, how and when it was written;
//                  Regenerate in the head for the host (owner: "Build as drawn"; the server's POST is the host's too)
//   the case       the selected slice: its kind (and who, for a coach or player), share and trend, the case, the evidence
//                  table (a headline's evidence links to its story)
//   What moved     the movement since last week and what the pack lacked
//   The season     a row a week, newest on top (the top slice and its share), and a stacked bar a week; a tap loads it
//   Headlines considered   folded: the titles Claude was shown, each linking out
// Nothing here calls CFBD or Claude: /api/blame/now reads the job's saved reports; a week from the strip is
// /api/blame/<season>/<key>; Regenerate starts the job (POST .../regenerate) and follows its run at /api/jobs/runs/<id>.
//
//   createBlameView({ onStatus })
//   KINDS, arcPaths(shares), trendWords(t), resultWords(row)   exported for the tests
//   blameGameBlock(record, { href })   the wheel and the slices alone, for the Post-Game stop's box (the line, Wave 3)

import { DASH, el, isNum, text } from "../ui/dom.js";
import { band, note } from "../ui/states.js";
import { errorPanel, poller } from "./common.js";

const SVG = "http://www.w3.org/2000/svg";
const RUN_POLL_MS = 10 * 1000;
const RUN_POLL_FOR_MS = 15 * 60 * 1000;
const WHEEL = { size: 320, outer: 148, inner: 90, push: 7, gap: 0.012 };

// the kinds' colors (the board's legend): told apart by lightness as well as hue, dark labels read on every one
export const KINDS = [
  { id: "coach", label: "Coach", color: "#F2994A" },
  { id: "player", label: "Player", color: "#EB6F92" },
  { id: "unit", label: "Unit", color: "#5B8DEF" },
  { id: "scheme", label: "Scheme", color: "#A78BFA" },
  { id: "roster", label: "Roster", color: "#2FA68A" },
  { id: "injuries", label: "Injuries", color: "#F25C54" },
  { id: "officiating", label: "Officiating", color: "#E8C547" },
  { id: "schedule", label: "Schedule", color: "#7FD1E8" },
  { id: "media", label: "Media", color: "#C97BDB" },
  { id: "other", label: "Other", color: "#9AA1AE" },
];
const kindOf = (id) => KINDS.find((k) => k.id === id) || KINDS[KINDS.length - 1];

export function trendWords(trend) {
  return { up: "up", down: "down", new: "new", flat: "flat" }[trend] || DASH; // words: the app draws no font glyphs (wave 3)
}

/** "W 27-24 at Texas" from a week's row (result, score, opponent, home, neutral); a dash where it is not known. */
export function resultWords(row) {
  const r = row && typeof row === "object" ? row : {};
  const letter = { win: "W", loss: "L", tie: "T" }[r.result] || null;
  const score = r.score && isNum(r.score.us) && isNum(r.score.them) ? `${r.score.us}-${r.score.them}` : null;
  const where = r.neutral ? "vs" : r.home === false ? "at" : "vs";
  const opponent = typeof r.opponent === "string" && r.opponent ? `${where} ${r.opponent}` : null;
  return [letter && score ? `${letter} ${score}` : letter, opponent].filter(Boolean).join(" ") || DASH;
}

/** The arcs of the wheel, one a share (in order, from twelve o'clock clockwise), the first pushed out: [{ d, label: {x, y} }]. */
export function arcPaths(shares, { selected = 0 } = {}) {
  const { size, outer, inner, push, gap } = WHEEL;
  const c = size / 2;
  const total = shares.reduce((s, v) => s + (isNum(v) && v > 0 ? v : 0), 0) || 1;
  const at = (r, a) => [c + r * Math.cos(a), c + r * Math.sin(a)];
  const f = (v) => v.toFixed(1);
  let start = -Math.PI / 2;
  return shares.map((v, i) => {
    const sweep = (2 * Math.PI * (isNum(v) && v > 0 ? v : 0)) / total;
    const end = start + sweep;
    const mid = (start + end) / 2;
    const out = i === selected ? push : 0;
    const dx = out * Math.cos(mid);
    const dy = out * Math.sin(mid);
    const a0 = start + (sweep > 2 * gap ? gap : 0);
    const a1 = end - (sweep > 2 * gap ? gap : 0);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const [x0, y0] = at(outer, a0);
    const [x1, y1] = at(outer, a1);
    const [x2, y2] = at(inner, a1);
    const [x3, y3] = at(inner, a0);
    const [lx, ly] = at((outer + inner) / 2, mid);
    start = end;
    return {
      d: `M${f(x0 + dx)},${f(y0 + dy)}A${outer},${outer} 0 ${large} 1 ${f(x1 + dx)},${f(y1 + dy)}L${f(x2 + dx)},${f(y2 + dy)}A${inner},${inner} 0 ${large} 0 ${f(x3 + dx)},${f(y3 + dy)}Z`,
      label: { x: lx + dx, y: ly + dy + 5 },
    };
  });
}

function svgEl(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(typeof kid === "string" ? document.createTextNode(kid) : kid);
  return node;
}

const str = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);

/** A report's slices, checked: [{ name, kind, share, case, evidence, trend }] (the server checked them; the page guards). */
function slicesOf(report) {
  const raw = Array.isArray(report?.slices) ? report.slices : [];
  return raw
    .filter((s) => s && typeof s === "object" && str(s.name))
    .map((s) => ({
      name: str(s.name),
      kind: kindOf(s.kind).id,
      share: isNum(s.share_pct) ? s.share_pct : 0,
      case: str(s.case) || "",
      trend: s.trend,
      evidence: (Array.isArray(s.evidence) ? s.evidence : []).filter((e) => e && typeof e === "object" && (str(e.metric) || str(e.value))),
    }));
}

function whenWords(iso) {
  const d = typeof iso === "string" ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null;
}

function wheel(slices, selected, pick, centerTop, centerBottom) {
  const arcs = arcPaths(slices.map((s) => s.share), { selected });
  const c = WHEEL.size / 2;
  return svgEl(
    "svg",
    { class: "blame-wheel__svg", viewBox: `0 0 ${WHEEL.size} ${WHEEL.size}`, role: "img", "aria-label": `The blame: ${slices.map((s) => `${s.name} ${s.share} percent`).join(", ")}` },
    ...arcs.map((a, i) => {
      const path = svgEl("path", { d: a.d, fill: kindOf(slices[i].kind).color, class: `blame-wheel__arc${i === selected ? " is-selected" : ""}`, "data-slice": i });
      path.addEventListener("click", () => pick(i));
      return path;
    }),
    ...arcs.map((a, i) => (slices[i].share >= 6 ? svgEl("text", { class: "blame-wheel__pct", x: a.label.x.toFixed(1), y: a.label.y.toFixed(1), "text-anchor": "middle" }, `${slices[i].share}%`) : null)),
    svgEl("text", { class: "blame-wheel__over", x: c, y: c - 6, "text-anchor": "middle" }, centerTop),
    svgEl("text", { class: "blame-wheel__score", x: c, y: c + 20, "text-anchor": "middle" }, centerBottom),
  );
}

function sliceList(slices, selected, pick) {
  return el(
    "div",
    { class: "blame-list", role: "group", "aria-label": "The slices" },
    ...slices.map((s, i) =>
      el(
        "button",
        { type: "button", class: `blame-list__row${i === selected ? " is-selected" : ""}`, "aria-pressed": i === selected ? "true" : "false", onclick: () => pick(i) },
        el("span", { class: "blame-swatch", style: { background: kindOf(s.kind).color }, "aria-hidden": "true" }),
        el("span", { class: "blame-list__who" }, el("span", { class: "blame-list__name" }, s.name), el("small", {}, `${kindOf(s.kind).label} · ${trendWords(s.trend)}`)),
        el("b", { class: "blame-list__share" }, `${s.share}%`),
      ),
    ),
  );
}

function legend() {
  return el("div", { class: "blame-legend", "aria-label": "The kinds" }, ...KINDS.map((k) => el("span", { class: "blame-legend__item" }, el("span", { class: "blame-swatch blame-swatch--small", style: { background: k.color }, "aria-hidden": "true" }), k.label)));
}

function evidenceTable(slice, headlines) {
  const linkFor = (e) => {
    if (!/headline/i.test(String(e.metric || ""))) return null;
    const value = String(e.value || "").trim().toLowerCase();
    const hit = headlines.find((h) => typeof h?.title === "string" && (h.title.trim().toLowerCase() === value || h.title.trim().toLowerCase().startsWith(value)));
    return hit && typeof hit.url === "string" && /^https?:\/\//.test(hit.url) ? hit.url : null;
  };
  return el(
    "div",
    { class: "stat-table-wrap" },
    el(
      "table",
      { class: "stat-table blame-evidence" },
      el("caption", { class: "sr-only" }, `The evidence for ${slice.name}`),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", class: "txt" }, "Evidence"), el("th", { scope: "col" }, "Value"), el("th", { scope: "col", class: "txt" }, "Context"))),
      el(
        "tbody",
        {},
        ...slice.evidence.map((e) => {
          const url = linkFor(e);
          return el(
            "tr",
            {},
            el("td", { class: "txt" }, text(e.metric) || DASH),
            el("td", { class: "blame-evidence__value" }, url ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, text(e.value)) : text(e.value) || DASH),
            el("td", { class: "txt blame-evidence__context" }, text(e.context) || DASH),
          );
        }),
      ),
    ),
  );
}

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  state.data = data;
  const record = state.shown && state.shown.key !== data.latest?.key ? state.shown : data.latest && typeof data.latest === "object" ? data.latest : null;
  const regenerate = data.canRegenerate === true && !state.kept ? regenerateButton(data, state) : null;
  if (data.available !== true || !record) {
    const message = text(data.message) || "The Circle of Blame has not been written yet.";
    const page = el(
      "div",
      { class: state.embedded ? "blame blame--embedded" : "page page--wide blame" },
      band({ id: "blame-wheel", title: "Circle of Blame", collapsible: false, tools: regenerate, state: { status: data.failed ? "error" : "empty", message }, errorLead: "No report yet." }),
      state.runNote(),
    );
    container.replaceChildren(page);
    if (data.runs?.running === true && data.runs.runningId && !state.running) queueMicrotask(() => state.follow(data.runs.runningId));
    return;
  }
  const report = record.report && typeof record.report === "object" ? record.report : {};
  const slices = slicesOf(report);
  if (!slices.length) {
    container.replaceChildren(el("div", { class: state.embedded ? "blame blame--embedded" : "page page--wide blame" }, band({ id: "blame-wheel", title: "Circle of Blame", collapsible: false, tools: regenerate, state: { status: "error", message: "This week's report came back without its slices." } })));
    return;
  }
  if (state.selected === null || state.selected >= slices.length || state.key !== record.key) {
    const biggest = slices.reduce((best, s, i) => (s.share > slices[best].share ? i : best), 0);
    state.selected = biggest;
    state.key = record.key;
  }
  const headlines = (Array.isArray(record.headlines) ? record.headlines : []).filter((h) => h && typeof h === "object" && str(h.title));
  const people = record.people && typeof record.people === "object" ? record.people : {};
  const weekWords = text(record.label) || `Week ${text(record.week)}`;
  const summary = `${weekWords} · ${resultWords({ result: report.after_result, score: record.score, opponent: record.opponent, home: record.home, neutral: record.neutral })}`;
  const centerBottom = resultWords({ result: report.after_result, score: record.score });
  if (data.runs?.running === true && data.runs.runningId && !state.running) queueMicrotask(() => state.follow(data.runs.runningId)); // the Sunday run, or another device's Regenerate

  const pick = (i) => {
    state.selected = i;
    draw();
  };
  const draw = () => {
    const s = slices[state.selected];
    const who = (s.kind === "coach" || s.kind === "player") && str(people[s.name]) ? ` · ${people[s.name]}` : "";
    const written = whenWords(record.generatedAt);
    const meta = [written ? `Written ${written}` : null, str(record.modelUsed) ? `by ${record.modelUsed}` : null].filter(Boolean).join(" ");
    const wheelBand = band({
      id: "blame-wheel",
      title: "Circle of Blame",
      foldable: true,
      collapsible: true,
      summary,
      tools: regenerate,
      state: { status: "ready" },
      body: () =>
        el(
          "div",
          { class: "blame-top" },
          el("div", { class: "blame-top__grid" }, el("figure", { class: "blame-wheel" }, wheel(slices, state.selected, pick, `AFTER ${weekWords.toUpperCase()}`, centerBottom)), sliceList(slices, state.selected, pick)),
          legend(),
          str(report.verdict) ? el("p", { class: "blame-verdict" }, report.verdict) : null,
          el("p", { class: "blame-meta" }, [meta ? `${meta} from the week's evidence pack` : null, str(report.confidence) ? `confidence ${report.confidence}` : null, "blame only, no credit"].filter(Boolean).join(" · ")),
          state.key !== data.latest?.key ? el("p", { class: "blame-meta" }, el("button", { type: "button", class: "btn btn--quiet", onclick: () => state.showLatest() }, "Back to the latest week")) : null,
          failureNote(data, record),
          state.runNote(),
        ),
    });
    const caseBand = band({
      id: "blame-case",
      title: s.name,
      foldable: true,
      collapsible: true,
      summary: el("span", { class: "blame-case__head" }, el("span", { class: "blame-kind", style: { "--kind": kindOf(s.kind).color } }, `${kindOf(s.kind).label}${who}`), el("b", { class: "blame-case__share" }, `${s.share}%`), el("span", {}, trendWords(s.trend))),
      state: { status: "ready" },
      body: () => el("div", { class: "blame-case" }, s.case ? el("p", { class: "blame-case__text" }, s.case) : note("No case was written for this slice."), s.evidence.length ? evidenceTable(s, headlines) : null),
    });
    const limits = (Array.isArray(report.limitations) ? report.limitations : []).filter(str);
    const movedBand = band({
      id: "blame-moved",
      title: "What moved",
      foldable: true,
      collapsible: true,
      state: { status: "ready" },
      body: () =>
        el(
          "div",
          { class: "blame-moved" },
          el("p", {}, str(report.movement) || "Nothing on movement this week."),
          limits.length ? el("h3", { class: "blame-sub" }, "What the pack lacked") : null,
          limits.length ? el("ul", { class: "blame-limits" }, ...limits.map((l) => el("li", {}, l))) : null,
        ),
    });
    const weeks = (Array.isArray(data.history) ? data.history : []).filter((w) => w && typeof w === "object" && str(w.key));
    const seasonBand = band({
      id: "blame-season",
      title: "The season",
      foldable: true,
      collapsible: true,
      summary: `${weeks.length} ${weeks.length === 1 ? "week" : "weeks"}`,
      state: { status: "ready" },
      body: () => seasonStrip(weeks, record.key, (key) => state.load(key)),
    });
    // one column (owner 2026-11-01): the four bands stacked, each the page's whole width; Headlines considered is gone ("I dont
    // need to see which headlines are considered"), the case's evidence table still names the headlines it rests on
    const page = el("div", { class: state.embedded ? "blame blame--embedded" : "page page--wide blame" }, wheelBand, caseBand, movedBand, seasonBand);
    container.replaceChildren(page);
  };
  draw();
}

function failureNote(data, record) {
  const last = data.runs?.last;
  if (data.lastFailure && last && last.status === "failed") {
    return note(`The last run failed: ${text(last.message)}. This is the report from ${whenWords(record.generatedAt) || "the last good run"}.`, { kind: "error" });
  }
  return null;
}

function seasonStrip(weeks, current, load) {
  const newest = weeks.slice().reverse();
  return el(
    "div",
    { class: "blame-season" },
    el(
      "div",
      { class: "blame-season__rows" },
      ...newest.map((w) =>
        el(
          "button",
          { type: "button", class: `blame-season__row${w.key === current ? " is-current" : ""}`, "aria-pressed": w.key === current ? "true" : "false", onclick: () => load(w.key) },
          el("span", { class: "blame-season__week" }, isNum(w.week) && /^week-/.test(w.key) ? `Wk ${w.week}` : text(w.label) || DASH),
          el("span", { class: "blame-season__what" }, resultWords(w), w.top ? el("span", { class: "blame-season__sep" }, " · ") : null, w.top ? el("b", {}, text(w.top.name)) : null), // a phone puts the unit on a line of its own (owner 2026-11-15: never cut)
          el("b", { class: "blame-season__share" }, w.top && isNum(w.top.share) ? `${w.top.share}%` : DASH),
        ),
      ),
    ),
    el(
      "div",
      { class: "blame-season__bars" },
      ...newest.map((w) =>
        el(
          "div",
          { class: "blame-season__bar-row" },
          el("span", {}, isNum(w.week) && /^week-/.test(w.key) ? `Wk ${w.week}` : text(w.label) || DASH),
          el(
            "div",
            { class: "blame-season__bar", role: "img", "aria-label": `${text(w.label)}: ${(w.slices || []).map((s) => `${text(s.name)} ${s.share}`).join(", ")}` },
            ...(Array.isArray(w.slices) ? w.slices : []).filter((s) => s && isNum(s.share) && s.share > 0).map((s) => el("span", { style: { width: `${s.share}%`, background: kindOf(s.kind).color }, title: `${text(s.name)} ${s.share}%` })),
          ),
        ),
      ),
    ),
    el("p", { class: "blame-meta" }, "A row and a bar each week, newest on top. Tap a week to load its report."),
  );
}

function regenerateButton(data, state) {
  const running = data.runs?.running === true || state.running;
  const button = el("button", { type: "button", class: "btn blame-regen", disabled: running ? "" : null, onclick: async (event) => {
    event.stopPropagation();
    const key = data.latest?.key || "latest";
    button.disabled = true;
    button.textContent = "Writing…";
    try {
      const response = await fetch(`/api/blame/${encodeURIComponent(String(data.season))}/${encodeURIComponent(key)}/regenerate`, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.errors?.[0]?.message || `The server answered ${response.status}`);
      state.follow(body?.data?.run?.id);
    } catch (error) {
      state.say(`Not started: ${text(error?.message)}`, "error");
      button.disabled = false;
      button.textContent = "Regenerate";
    }
  } }, running ? "Writing…" : "Regenerate");
  return button;
}

/** The Circle of Blame's bands (the wheel, the case, What moved, The season) on My Team (wave 3 of the one-column page,
 *  owner 2026-11-01: the page of its own dissolved into My Team and the Post-Game; Headlines considered dropped): the
 *  same view mounted in a host on the page, its bands stacked, no page of its own. */
export function createBlameView({ onStatus = () => {}, embedded = true, url = "/api/blame/now", kept = false } = {}) {
  let timer = null;
  let until = 0;
  let alive = false;
  let last = null;
  let target = null;
  let said = null;
  const state = {
    embedded, // wave 3 (2026-11-01): on My Team the bands stack in a host, no page of their own
    kept, // rollover R2: a past season's report as kept when the app moved on (the Seasons list); nothing to regenerate
    selected: null,
    key: null,
    shown: null,
    data: null,
    running: false,
    redraw: () => {
      if (alive && last && target) render(last, target, state);
    },
    say: (message, kind = "empty") => {
      said = { message, kind };
      state.redraw();
    },
    runNote: () => (said ? note(said.message, { kind: said.kind === "error" ? "error" : "empty" }) : state.running ? note("Claude Code is writing the report now; it takes a few minutes.") : null),
    load: async (key) => {
      if (!state.data || key === (state.shown?.key || state.data.latest?.key)) return;
      if (key === state.data.latest?.key) {
        state.showLatest();
        return;
      }
      try {
        const response = await fetch(`/api/blame/${encodeURIComponent(String(state.data.season))}/${encodeURIComponent(key)}`, { cache: "no-store" });
        const body = await response.json().catch(() => null);
        if (!response.ok || !body?.data) throw new Error(body?.errors?.[0]?.message || `The server answered ${response.status}`);
        state.shown = body.data;
        state.selected = null;
        said = null;
        state.redraw();
      } catch (error) {
        state.say(`That week could not be loaded: ${text(error?.message)}`, "error");
      }
    },
    showLatest: () => {
      state.shown = null;
      state.selected = null;
      state.redraw();
    },
    follow: (id) => {
      state.running = true;
      said = null;
      state.redraw();
      until = Date.now() + RUN_POLL_FOR_MS;
      const tick = async () => {
        timer = null;
        if (!alive) return;
        let run = null;
        try {
          const response = await fetch(`/api/jobs/runs/${encodeURIComponent(String(id))}`, { cache: "no-store" });
          const body = await response.json().catch(() => null);
          run = body?.data && typeof body.data === "object" ? body.data : null;
        } catch {
          run = null; // the server is busy or restarting: ask again
        }
        if (run && run.status && run.status !== "running") {
          state.running = false;
          state.shown = null;
          state.selected = null;
          said = run.status === "ok" ? null : { message: `${run.status === "skipped" ? "Skipped" : "The run failed"}: ${text(run.message)}`, kind: run.status === "failed" ? "error" : "empty" };
          state.redraw(); // the note goes at once; the new report follows with the refresh
          inner.refresh();
          return;
        }
        if (Date.now() > until) {
          state.running = false;
          state.say("Still writing after 15 minutes; the page will show the report once it is saved.");
          return;
        }
        timer = setTimeout(tick, RUN_POLL_MS);
      };
      if (id) timer = setTimeout(tick, RUN_POLL_MS);
      else {
        state.running = false;
        inner.refresh();
      }
    },
  };
  const inner = poller({
    url,
    onStatus,
    render: (envelope, container) => {
      last = envelope;
      target = container;
      render(envelope, container, state);
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Circle of Blame", message, retry)),
    loadingDetail: "This week's report",
    renderLoading: () => el("div", { class: embedded ? "blame blame--embedded" : "page page--wide blame" }, band({ id: "blame-wheel", title: "Circle of Blame", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "skel blame-skel" }) })),
  });
  return {
    mount(node) {
      alive = true;
      return inner.mount(node);
    },
    refresh: () => inner.refresh(),
    unmount() {
      alive = false;
      clearTimeout(timer);
      timer = null;
      inner.unmount();
    },
  };
}

/** The report's wheel and slices alone, for another page (the Post-Game stop's Circle of Blame box, the season as one line,
 *  Wave 3): a tap on an arc or a row selects a slice and its case reads under the wheel; the link opens the whole page. */
export function blameGameBlock(record, { href = "#band=season:blame-wheel" } = {}) {
  const rec = record && typeof record === "object" ? record : {};
  const report = rec.report && typeof rec.report === "object" ? rec.report : {};
  const slices = slicesOf(report);
  if (!slices.length) return note("This week's report came back without slices.", { kind: "error" });
  let selected = slices.reduce((best, s, i) => (s.share > slices[best].share ? i : best), 0);
  const people = rec.people && typeof rec.people === "object" ? rec.people : {};
  const weekWords = text(rec.label) || `Week ${text(rec.week)}`;
  const centerBottom = resultWords({ result: report.after_result, score: rec.score });
  const root = el("div", { class: "blame-top blame-top--box" });
  const pick = (i) => {
    selected = i;
    draw();
  };
  function draw() {
    const s = slices[selected];
    const who = (s.kind === "coach" || s.kind === "player") && str(people[s.name]) ? ` · ${people[s.name]}` : "";
    const written = whenWords(rec.generatedAt);
    root.replaceChildren(
      el("div", { class: "blame-top__grid" }, el("figure", { class: "blame-wheel" }, wheel(slices, selected, pick, `AFTER ${weekWords.toUpperCase()}`, centerBottom)), sliceList(slices, selected, pick)),
      el(
        "div",
        { class: "blame-case blame-case--box" },
        el("p", { class: "blame-case__head" }, el("span", { class: "blame-kind", style: { "--kind": kindOf(s.kind).color } }, `${kindOf(s.kind).label}${who}`), " ", el("b", {}, s.name), " ", el("b", { class: "blame-case__share" }, `${s.share}%`), " ", el("span", {}, trendWords(s.trend))),
        s.case ? el("p", { class: "blame-case__text" }, s.case) : note("No case was written for this slice."),
      ),
      str(report.verdict) ? el("p", { class: "blame-verdict" }, report.verdict) : null,
      el("p", { class: "blame-meta" }, [written ? `Written ${written}` : null, str(rec.modelUsed) ? `by ${rec.modelUsed}` : null, "blame only, no credit"].filter(Boolean).join(" · "), " ", el("a", { href }, "Open the Circle of Blame")),
    );
  }
  draw();
  return root;
}
