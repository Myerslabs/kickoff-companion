// The Newspaper (N1 to N4): headlines from the team's feeds every day, the day's slate on our game
// days and on every other Saturday of the season (a bye week, Phase 12) with our opponents
// pinned first and a Scores band that refreshes every minute, and on other days a line saying
// when the next slate is. Headlines are links out. Betting
// news never shows (the server drops it); the feeds line says how many betting headlines were hidden.

import { confLabel, usName, usSchool } from "../identity.js";
import { el, fmtDate, isNum, text } from "../ui/dom.js";
import { newsDigest, newsSkeleton, slateList, slateSkeleton } from "../ui/news.js";
import { scoresTable } from "../ui/scores.js";
import { band, note } from "../ui/states.js";
import { getPrefs, pollMs } from "../prefs.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";

const SCORES_MS = 60 * 1000;

/** The Scores band: /api/ticker now and every minute while the band is on the page. */
function scoresBand() {
  const host = el("div", {}, band({ id: "news-scores", title: "Scores", collapsible: false, state: { status: "loading" } }));
  const load = async () => {
    const delay = Number(getPrefs().delaySeconds);
    try {
      const envelope = await fetchJson(`/api/ticker?delay=${Number.isFinite(delay) ? delay : 30}`);
      const games = Array.isArray(envelope?.data?.games) ? envelope.data.games : [];
      const mine = envelope?.data?.mode === "mine"; // public release Phase 5b: the My teams ticker
      const modeNote = typeof envelope?.data?.modeNote === "string" && envelope.data.modeNote ? note(envelope.data.modeNote) : null;
      host.replaceChildren(band({ id: "news-scores", title: mine ? "My teams' scores" : "Scores", collapsible: false, summary: `${games.length} ${mine ? "games" : "FBS games"}`, body: () => el("div", {}, scoresTable({ games }), modeNote, note(mine ? "Your primary and secondary teams' games. Our line follows your spoiler delay." : "Every FBS game. Our line follows your spoiler delay.")) }));
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

function render(envelope, container) {
  const data = envelope.data || {};
  const news = Array.isArray(data.news) ? data.news : [];
  const slate = Array.isArray(data.slate) ? data.slate : [];
  const next = data.nextGame;
  const slateDay = data.slateDay === true || data.gameDay === true; // a server from before Phase 12 sends only gameDay
  const slateSummary = slateDay ? `${slate.length} games today${data.byeWeek ? `, ${usName()} bye` : ""}` : next?.date ? `next slate ${fmtDate(next.date)}` : "";
  container.replaceChildren(
    el(
      "div",
      { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } },
      band({
        id: "news-headlines",
        title: `${usName()} headlines`,
        collapsible: false,
        summary: feedsSummary(data.feeds),
        state: feedsState(data.feeds, news.length > 0),
        emptyText: `No ${usName()} headlines in the feeds right now.`,
        body: () => newsDigest({ items: news }),
      }),
      band({
        id: "news-slate",
        title: slateDay ? `Today's slate, ${fmtDate(data.today)}` : "Today's slate",
        collapsible: false,
        summary: slateSummary,
        state: slateDay ? partState(data.parts?.weekGames, slate.length > 0) : { status: "ready" },
        emptyText: `No Top 25, ${confLabel()}, or opponent games today.`,
        body: () =>
          slateDay
            ? slateList({ games: slate, usName: usSchool(), note: data.byeWeek && next ? `The ${usName()} are off this week. Next: ${fmtDate(next.date)} against ${text(next.opponent)}.` : null })
            : note(`${text(data.slateNote)}${next ? ` Our next game: ${fmtDate(next.date)} against ${text(next.opponent)}.` : ""}`),
      }),
      slateDay ? scoresBand() : null,
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
    renderLoading: () =>
      el(
        "div",
        { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } },
        band({ title: `${usName()} headlines`, collapsible: false, state: { status: "loading" }, skeleton: () => newsSkeleton(6) }),
        band({ title: "Today's slate", collapsible: false, state: { status: "loading" }, skeleton: () => slateSkeleton(2) }),
      ),
  });
}

export { isNum };
