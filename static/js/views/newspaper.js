// The Newspaper (N1 to N4): headlines from the team's feeds every day, the day's slate on our game
// days and on every other Saturday of the season (a bye week, Phase 12) with our opponents
// pinned first and a Scores band that refreshes every minute, and on other days a line saying
// when the next slate is. Headlines are links out. Betting
// news never shows (the server drops it); the feeds line says how many betting headlines were hidden.
//
// Phase 17 #26 (owner-approved mockup, 2026-10-07): a newspaper page. A masthead whose name changes a little
// from week to week (steady within a week, made from the team's own names), then one section per game week
// with this week open and the earlier weeks folded under "Earlier weeks", every headline the app saw this
// season. Each week's newest story leads in larger type; the rest run in ruled columns that multiply with the
// screen's width. Every story has a small pixel picture by its topic, or the pixelated headshot of a player it
// names, always smaller than its headline.

import { confLabel, ours, usName, usSchool } from "../identity.js";
import { el, fmtDate, isNum, records, teamLink, text } from "../ui/dom.js";
import { ageOf, newsDigest, newsSkeleton, slateList, slateSkeleton } from "../ui/news.js";
import { pixelBanner, pixelPicture, seedOf } from "../ui/pixel-art.js";
import { scoresSummary, scoresTable } from "../ui/scores.js";
import { band, note } from "../ui/states.js";
import { getPrefs, pollMs } from "../prefs.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";

const SCORES_MS = 60 * 1000;

/** The Scores band: /api/ticker now and every minute while the band is on the page. */
function scoresBand() {
  const host = el("div", {}, band({ id: "news-scores", title: "Scores", collapsible: false, state: { status: "loading" } }));
  let table = null; // kept across the minute's refreshes so only the changed scores flash (Phase 16 wave 3)
  const load = async () => {
    const delay = Number(getPrefs().delaySeconds);
    try {
      const envelope = await fetchJson(`/api/ticker?delay=${Number.isFinite(delay) ? delay : 30}`);
      const games = Array.isArray(envelope?.data?.games) ? envelope.data.games : [];
      const mine = envelope?.data?.mode === "mine"; // public release Phase 5b: the My teams ticker
      const modeNote = typeof envelope?.data?.modeNote === "string" && envelope.data.modeNote ? note(envelope.data.modeNote) : null;
      if (table) table.update(games);
      else table = scoresTable({ games });
      host.replaceChildren(band({ id: "news-scores", title: mine ? "My teams' scores" : "Scores", collapsible: false, summary: scoresSummary(games) || `${games.length} ${mine ? "games" : "FBS games"}`, body: () => el("div", {}, table, modeNote, note(mine ? "Your primary and secondary teams' games. Our line follows your spoiler delay." : "Every FBS game. Our line follows your spoiler delay.")) }));
    } catch (error) {
      host.replaceChildren(band({ id: "news-scores", title: "Scores", collapsible: false, state: { status: "error", message: `${error?.message || "The request failed"}. Retrying every minute.` } }));
    }
  };
  load();
  const timer = setInterval(() => {
    if (!host.isConnected) clearInterval(timer); // the page was redrawn or left: this band is done
    else load();
  }, SCORES_MS);
  return host;
}

// The feed status objects, skipping anything that is not one.
function feedEntries(feeds) {
  return feeds && typeof feeds === "object" ? Object.values(feeds).filter((f) => f && typeof f === "object") : [];
}

function feedsSummary(feeds) {
  const entries = feedEntries(feeds);
  if (!entries.length) return "";
  const ok = entries.filter((f) => f.status === "ok").length;
  const stale = entries.filter((f) => f.status === "stale").length;
  const down = entries.filter((f) => f.status === "error").length;
  const hidden = entries.reduce((sum, f) => sum + (isNum(f.betting) && f.betting > 0 ? Math.round(f.betting) : 0), 0);
  return [
    `${ok} of ${entries.length} feeds fresh`,
    stale ? `${stale} stale` : null,
    down ? `${down} down` : null,
    hidden ? `${hidden} betting headline${hidden === 1 ? "" : "s"} hidden` : null,
  ]
    .filter(Boolean)
    .join(", ");
}

function feedsState(feeds, has) {
  const entries = feedEntries(feeds);
  if (entries.length && entries.every((f) => f.status === "error")) return { status: "error", message: `Every feed failed: ${text(entries[0].error)}. The app keeps retrying.` };
  if (!has) return { status: "empty" };
  const stale = entries.find((f) => f.status === "stale");
  if (stale) return { status: "stale", ageSeconds: stale.ageSeconds, message: `${text(stale.name)}: ${text(stale.error)}.` };
  const down = entries.filter((f) => f.status === "error");
  if (down.length) return { status: "ready", updatedText: `${down.map((f) => text(f.name)).join(", ")} not answering: ${text(down[0].error)}. The app keeps retrying.` };
  return { status: "ready" };
}

// The masthead's names: the team's mascot or school in a newspaper's name, one per week of the season.
const MASTHEADS = ["The {m} Gazette", "The {m} Herald", "The {s} Courier", "The {m} Chronicle", "The {s} Sentinel", "The {m} Tribune", "The Saturday {m}", "The {m} Bugle", "The {s} Ledger", "The {m} Dispatch"];

/** This week's paper's name, steady all week (Phase 17 #26: "randomize a little bit, depending on the week"). */
export function mastheadName(season, week, who = ours()) {
  const id = who && typeof who === "object" ? who : {};
  const word = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
  const school = word(id.school) || word(id.name) || "Kickoff";
  const mascot = word(id.mascot) || school;
  const pick = MASTHEADS[seedOf(`${isNum(season) ? season : ""}:${isNum(week) ? week : "x"}`) % MASTHEADS.length];
  return pick.replace("{m}", mascot).replace("{s}", school);
}

function storyPicture(item, size) {
  const players = records(item.players);
  const face = players.find((p) => typeof p.playerId === "string" && p.playerId);
  const label = face ? `${text(face.name)}, in pixels` : `A pixel picture: ${text(item.topic || "the game")}`;
  const pic = pixelPicture({ topic: item.topic, seed: seedOf(item.title), playerId: face ? face.playerId : null, label });
  pic.classList.add(`px-pic--${size}`);
  return pic;
}

function headline(item, cls) {
  const title = text(item.title);
  const href = typeof item.url === "string" && /^https?:\/\//i.test(item.url) ? item.url : null;
  return el("h3", { class: cls }, href ? el("a", { href, target: "_blank", rel: "noopener" }, title) : title);
}

function dateline(item) {
  return el("p", { class: "paper-story__line" }, [item.source, ageOf(item.publishedAt)].filter(Boolean).map(text).join(" · "));
}

/**
 * How big a story is printed (Phase 19, owner: "story cards in randomized sizes like a real paper"). Random but steady: the
 * same story is always the same size, because the size comes from its own headline. About one story in seven is a feature
 * (spans the page), one in three a medium (a bigger picture over its headline), the rest small. No two features in a row,
 * and the first story after the lead is never a feature, so the page keeps its shape.
 */
export function storySizes(items) {
  const list = Array.isArray(items) ? items : [];
  const sizes = [];
  for (let i = 0; i < list.length; i += 1) {
    const roll = seedOf(`size:${text(list[i]?.title)}`) % 21;
    let size = roll < 3 ? "l" : roll < 10 ? "m" : "s";
    if (size === "l" && (i === 0 || sizes[i - 1] === "l")) size = "m";
    sizes.push(size);
  }
  return sizes;
}

function storyEl(item, size = "s") {
  const picture = storyPicture(item, size === "l" ? "feature" : size === "m" ? "medium" : "small");
  return el("article", { class: `paper-story paper-story--${size}` }, picture, el("div", { class: "paper-story__words" }, headline(item, size === "l" ? "paper-story__head paper-story__head--feature" : "paper-story__head"), dateline(item)));
}

function weekBody(week) {
  const items = records(week.headlines).filter((h) => typeof h.title === "string" && h.title.trim());
  if (!items.length) return el("p", { class: "note" }, "No stories this week.");
  const [lead, ...rest] = items;
  return el(
    "div",
    { class: "paper-week" },
    el("article", { class: "paper-lead" }, el("div", { class: "paper-lead__words" }, headline(lead, "paper-lead__head"), dateline(lead)), storyPicture(lead, "lead")),
    rest.length ? el("div", { class: "paper-cols" }, (() => { const sizes = storySizes(rest); return rest.map((item, i) => storyEl(item, sizes[i])); })()) : null,
  );
}

function weekBand(week, current) {
  const count = records(week.headlines).length;
  return band({
    id: `paper-week-${text(week.key)}`,
    title: text(week.label),
    collapsible: true,
    foldable: true,
    collapsed: !current,
    summary: `${count} ${count === 1 ? "story" : "stories"}`,
    state: { status: "ready" },
    body: () => weekBody(week),
  });
}

function masthead(data, weeks) {
  const week = weeks.length && isNum(weeks[0].week) ? weeks[0].week : null;
  return el(
    "header",
    { class: "paper-mast" },
    pixelBanner({ seed: seedOf(`${isNum(data.season) ? data.season : ""}:${isNum(week) ? week : "x"}:banner`) }),
    el("h1", { class: "paper-mast__name" }, mastheadName(data.season, week)),
    el(
      "div",
      { class: "paper-mast__line" },
      el("span", {}, fmtDate(data.today || new Date().toISOString(), "long")),
      el("span", {}, feedsSummary(data.feeds) || "Headlines from the team's feeds"),
      el("span", {}, weeks.length ? `${text(weeks[0].label)} edition` : "This week's edition"),
    ),
  );
}

function render(envelope, container) {
  const data = envelope.data || {};
  const news = Array.isArray(data.news) ? data.news : [];
  const weeks = records(data.weeks);
  const slate = Array.isArray(data.slate) ? data.slate : [];
  const next = data.nextGame;
  const slateDay = data.slateDay === true || data.gameDay === true; // a server from before Phase 12 sends only gameDay
  const slateSummary = slateDay ? `${slate.length} games today${data.byeWeek ? `, ${usName()} bye` : ""}` : next?.date ? `next slate ${fmtDate(next.date)}` : "";
  const slateBand = band({
    id: "news-slate",
    title: slateDay ? `Today's slate, ${fmtDate(data.today)}` : "Today's slate",
    collapsible: false,
    summary: slateSummary,
    state: slateDay ? partState(data.parts?.weekGames, slate.length > 0) : { status: "ready" },
    emptyText: `No Top 25, ${confLabel()}, or opponent games today.`,
    body: () =>
      slateDay
        ? slateList({ games: slate, usName: usSchool(), note: data.byeWeek && next ? `The ${usName()} are off this week. Next: ${fmtDate(next.date)} against ${text(next.opponent)}.` : null })
        : el("p", { class: "note" }, `${text(data.slateNote)}`, next ? [` Our next game: ${fmtDate(next.date)} against `, teamLink(typeof next.opponent === "string" ? next.opponent : null, text(next.opponent)), "."] : null), // G3-07: the opponent links
  });
  // a server from before Phase 17 sends no weeks: the old digest
  const lead = weeks.length
    ? weekBand(weeks[0], true)
    : band({ id: "news-headlines", title: `${usName()} headlines`, collapsible: false, summary: feedsSummary(data.feeds), state: feedsState(data.feeds, news.length > 0), emptyText: `No ${usName()} headlines in the feeds right now.`, body: () => newsDigest({ items: news }) });
  const earlier = weeks.length > 1 ? [el("h2", { class: "paper-earlier" }, "Earlier weeks"), ...weeks.slice(1).map((w) => weekBand(w, false))] : [];
  const trouble = feedsState(data.feeds, news.length > 0 || weeks.length > 0);
  container.replaceChildren(
    el(
      "div",
      { class: "page page--wide paper-page" },
      masthead(data, weeks),
      weeks.length && (trouble.status === "error" || trouble.status === "stale") ? note(text(trouble.message), { kind: trouble.status === "error" ? "error" : "empty" }) : null,
      lead, // this week's stories first, as a paper leads with its news; the day's games follow
      slateBand,
      slateDay ? scoresBand() : null,
      ...earlier,
    ),
  );
}

export function createNewspaperView({ onStatus } = {}) {
  return poller({
    url: "/api/newspaper",
    refreshMs: pollMs(),
    onStatus,
    render,
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Newspaper", message, retry)),
    loadingDetail: "This week's stories and today's slate",
    renderLoading: () =>
      el(
        "div",
        { class: "page page--wide paper-page" },
        el("header", { class: "paper-mast" }, el("div", { class: "skel", style: { width: "min(420px, 70%)", height: "40px", margin: "4px auto" } })),
        band({ title: "This week", collapsible: false, state: { status: "loading" }, skeleton: () => newsSkeleton(6) }),
        band({ title: "Today's slate", collapsible: false, state: { status: "loading" }, skeleton: () => slateSkeleton(2) }),
      ),
  });
}

export { isNum };
