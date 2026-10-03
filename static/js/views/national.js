// The national list as a page (Phase 16, stream NV; G3-01): "#national=<metric>?team=&year=&scope=", the
// 'Full page' of the side sheet a rank chip opens. The same list as the sheet (ui/national-sheet.js), with a
// Back row, its switches as links (so Back steps through them) and the tapped team's row scrolled into view
// on arrival. A poll list's full page is the Season polls band instead (#season=polls:<poll>).

import { pollMs } from "../prefs.js";
import { el, text } from "../ui/dom.js";
import { centerRow, listState, listTitle, nationalApiUrl, nationalListBody, summaryText } from "../ui/national-sheet.js";
import { nationalHref, nationalRoute } from "../ui/national-link.js";
import { backRow, band } from "../ui/states.js";
import { statTableSkeleton } from "../ui/stat-table.js";
import { errorPanel, poller } from "./common.js";

function withBack(node) {
  node.prepend(backRow({ fallback: "#season" }));
  return node;
}

function shortSummary(data) {
  const line = summaryText(data);
  const cut = line.indexOf(" · ");
  return cut > 0 ? line.slice(0, cut) : line;
}

export function createNationalView({ onStatus, arg, params } = {}) {
  const want = nationalRoute({ arg, params: params && typeof params === "object" ? params : {} });
  const url = nationalApiUrl(want);
  if (!url) {
    let host = null;
    return {
      mount(target) {
        host = target;
        host.replaceChildren(withBack(errorPanel("National list", "There is no national list with that name", null)));
        if (typeof onStatus === "function") onStatus({ kind: "quiet", label: "No such list" });
      },
      refresh() {},
      unmount() {
        host = null;
      },
    };
  }
  const go = (patch) => {
    const href = nationalHref(want.metric, { ...want, ...patch });
    if (href) window.location.hash = href;
  };
  let arrived = false;
  const view = poller({
    url,
    refreshMs: pollMs(),
    onStatus,
    render: (envelope, container) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      container.replaceChildren(
        el(
          "div",
          { class: "page nat-page" },
          backRow({ fallback: "#season" }),
          band({
            id: "national-list",
            title: listTitle(data),
            collapsible: false,
            summary: shortSummary(data),
            state: listState(envelope),
            body: () => nationalListBody(envelope, { onScope: (scope) => go({ scope }), onYear: (year) => go({ year }), onRetry: () => view.refresh() }),
          }),
        ),
      );
      if (!arrived) {
        arrived = true; // only on arrival: a refresh keeps the reader where he is
        const later = () => centerRow(container);
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => requestAnimationFrame(later));
      }
    },
    renderError: (message, container, retry) => container.replaceChildren(withBack(errorPanel("National list", text(message), retry))),
    renderLoading: () => el("div", { class: "page nat-page" }, backRow({ fallback: "#season" }), band({ title: "National list", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(14, 3) })),
  });
  return view;
}
