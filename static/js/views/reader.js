// The Newspaper's reader (FEAT-14 wave 3, the owner's board of 2026-10-27):
// a copied story whole, from this computer's own copy, at #story=<id>. The reader's bar goes back to the same spot in the
// paper and steps to the stories either side (Story n of N, in the paper's order); the head, the byline and the read time;
// the photo at the page's width with its cutline; the article in one serif column about 75 characters wide; where it came
// from with the way to the publisher's page; Back and Next in the paper; more from the same section of the week.
//
//   createReaderView({ onStatus, id })

import { el, fmtDate, isNum, obj, records, text } from "../ui/dom.js";
import { icon } from "../ui/icons.js";
import { note } from "../ui/states.js";
import { errorPanel, poller } from "./common.js";
import { pastYear } from "../ui/past.js"; // rollover R3

const STORY = /^[0-9a-f]{16}$/;

const httpUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : null);

/** Back to the paper: the browser's own back when the reader was opened from it (the paper keeps its place), else the paper. */
// rollover R3: a past season's story (#story=<id>?season=2026) reads that season's copy and leads back to that season's paper
let SEASON = null;
const storyHash = (id) => (SEASON ? `#story=${id}?season=${SEASON}` : `#story=${id}`);
const paperHash = () => (SEASON ? `#newspaper?season=${SEASON}` : "#newspaper");

function backToPaper(event) {
  let from = null;
  try {
    from = JSON.parse(sessionStorage.getItem("np.from") || "null");
    if (from && isNum(from.y)) sessionStorage.setItem("np.back", JSON.stringify({ y: from.y, at: Date.now() }));
  } catch {
    from = null;
  }
  if (from && isNum(from.at) && Date.now() - from.at < 30 * 60 * 1000 && typeof history !== "undefined" && history.length > 1) {
    event?.preventDefault?.();
    history.back();
  }
}

function brief(s, cls = "np-brief") {
  const b = obj(s);
  if (!b.title) return null;
  const href = b.copied && STORY.test(String(b.id || "")) ? storyHash(b.id) : httpUrl(b.url);
  const kids = [el("span", { class: "np-brief__head" }, text(b.title)), el("span", { class: "np-src" }, [text(b.source || "News"), b.publishedAt ? fmtDate(b.publishedAt, "short") : null, b.copied ? null : "Headline only"].filter(Boolean).join(" · "))];
  if (!href) return el("div", { class: cls }, kids);
  return href.startsWith("#") ? el("a", { class: cls, href }, kids) : el("a", { class: cls, href, target: "_blank", rel: "noopener" }, kids);
}

function bar(paper) {
  const p = obj(paper);
  const where = isNum(p.position) && isNum(p.count) ? `Story ${p.position} of ${p.count}` : "The week's paper";
  const step = (s, label, which) => {
    const b = obj(s);
    const href = b.id && STORY.test(String(b.id)) ? (b.copied ? storyHash(b.id) : httpUrl(b.url)) : null;
    const glyph = icon(which === "prev" ? "back" : "chevron-right");
    if (!href) return el("button", { type: "button", class: "btn", disabled: true, "aria-label": `${label}: none` }, glyph);
    return href.startsWith("#") ? el("a", { class: "btn", href, "aria-label": `${label}: ${text(b.title)}` }, glyph) : el("a", { class: "btn", href, target: "_blank", rel: "noopener", "aria-label": `${label}: ${text(b.title)} (at its site)` }, glyph);
  };
  return el(
    "nav",
    { class: "np-reader__bar", "aria-label": "The paper" },
    el("a", { class: "btn", href: paperHash(), onclick: backToPaper }, icon("back"), "The paper"),
    el("span", { class: "np-reader__where" }, el("span", { class: "np-label" }, [text(p.label || null), p.section || null].filter((v) => v && v !== "–").join(" · ") || "Newspaper"), el("span", { class: "np-src" }, where)),
    step(p.prev, "Previous story", "prev"),
    step(p.next, "Next story", "next"),
  );
}

function render(envelope, container) {
  const s = obj(envelope?.data);
  const paper = obj(s.paper);
  const minutes = isNum(s.readMinutes) ? `${s.readMinutes} min read` : null;
  const byline = [text(s.source || null), s.publishedAt ? fmtDate(s.publishedAt, "long") : null, minutes].filter((v) => v && v !== "–").join(" · ");
  const photo = typeof s.photo === "string" && s.photo.startsWith("/") ? s.photo : null;
  const img = photo ? el("img", { src: photo, alt: typeof s.cutline === "string" ? s.cutline : "", decoding: "async" }) : null;
  const figure = img ? el("figure", { class: "np-reader__photo" }, img, s.cutline || s.credit ? el("figcaption", { class: "np-cut" }, [typeof s.cutline === "string" ? s.cutline : null, typeof s.credit === "string" ? `Photo: ${s.credit}` : null].filter(Boolean).join(" ")) : null) : null;
  if (img) img.addEventListener("error", () => figure.remove());
  const site = httpUrl(s.url);
  const next = obj(paper.next);
  const related = records(paper.related).slice(0, 6);
  const half = Math.ceil(related.length / 2);
  const page = el(
    "article",
    { class: "page page--wide np-reader np" },
    bar(paper),
    el(
      "header",
      { class: "np-reader__col" },
      el("span", { class: "np-kicker" }, text(paper.section || "The week")),
      el("h1", { class: "np-head np-head--lead" }, text(s.title)),
      el("div", { class: "np-reader__byline" }, s.author ? el("span", { style: { fontWeight: "600" } }, `By ${text(s.author)}`) : null, el("span", { class: "np-src" }, byline)),
    ),
    figure,
    el("div", { class: "np-reader__col np-reader__body" }, (Array.isArray(s.paragraphs) ? s.paragraphs : []).filter((p) => typeof p === "string" && p.trim()).map((p) => el("p", {}, p))),
    el(
      "div",
      { class: "np-reader__col", style: { display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "4px 12px", paddingTop: "12px", borderTop: "1px solid var(--rule)" } },
      el("span", { class: "np-src" }, s.copiedAt ? `Copied to the server ${fmtDate(s.copiedAt, "long")}` : "Copied to the server"),
      site ? el("a", { class: "np-go", href: site, target: "_blank", rel: "noopener" }, `Read it at ${text(s.host || "the site")} ↗`) : null,
    ),
    el(
      "div",
      { class: "np-reader__next" },
      el("a", { class: "np-card", href: paperHash(), onclick: backToPaper }, el("span", { class: "np-label" }, "‹ Back"), el("b", {}, "The paper")),
      next.title ? brief(next, "np-card np-card--next") : el("span", { class: "np-card" }, el("span", { class: "np-label" }, "Next in the paper"), el("span", { class: "np-src" }, "The last story of the week")),
    ),
    related.length
      ? el("section", { class: "np-related" }, el("div", { class: "np-standing" }, `More this week${paper.section ? `: ${text(paper.section)}` : ""}`), el("div", { class: "np-related__cols" }, el("div", {}, related.slice(0, half).map((r) => brief(r))), el("div", { class: "np-rule-v" }, related.slice(half).map((r) => brief(r)))))
      : null,
  );
  if (next.title) page.querySelector(".np-card--next")?.prepend(el("span", { class: "np-label" }, "Next in the paper ›"));
  container.replaceChildren(page);
  if (typeof window !== "undefined" && typeof window.scrollTo === "function") window.scrollTo(0, 0);
  return page;
}

export function createReaderView({ onStatus, id = null, season = null } = {}) {
  const sid = typeof id === "string" && STORY.test(id) ? id : null;
  SEASON = pastYear(season);
  if (!sid) {
    return {
      mount(target) {
        target.replaceChildren(el("div", { class: "page" }, note("That story is not on this server.", { kind: "empty" }), el("a", { class: "btn", href: paperHash() }, "The paper")));
      },
      refresh() {},
      unmount() {},
      last: null,
    };
  }
  const inner = poller({
    url: SEASON ? `/api/paper/story/${sid}?season=${SEASON}` : `/api/paper/story/${sid}`,
    onStatus,
    render,
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("The story", message, retry), el("p", {}, el("a", { class: "btn", href: paperHash() }, "The paper"))),
    loadingDetail: "The story",
    renderLoading: () => el("div", { class: "page page--wide np-reader np" }, el("div", { class: "np-reader__col skel", style: { height: "60px" } }), el("div", { class: "np-reader__col skel", style: { height: "420px" } })),
  });
  return {
    mount: (target) => inner.mount(target),
    refresh: () => inner.refresh(),
    unmount: () => inner.unmount(),
    get last() {
      return inner.last;
    },
  };
}
