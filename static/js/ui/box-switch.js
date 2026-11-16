// A box's view switch (the season as one line, Wave 2; shared by the Pre-Game Program's boxes and the Season stop's The
// numbers since Wave 4): the app's .seg in the band's head, one button a view. The choice is kept per device under `key`,
// so the box opens the same way next time; ?view= on the address wins for one visit.
//
//   viewSwitch(views, current, onPick)   views: [[id, label], ...]; the node has mark(id) and drop(id)
//   rememberedView(key, fallback, allowed)   the device's last choice for the box, else the fallback
//   rememberView(key, view)

import { el } from "./dom.js";

export function viewSwitch(views, current, onPick) {
  const buttons = views.map(([id, label]) => el("button", { type: "button", "aria-pressed": id === current ? "true" : "false", dataset: { view: id }, onclick: () => onPick(id) }, label));
  const seg = el("div", { class: "seg box__switch", role: "group", "aria-label": "Which view" }, buttons);
  seg.mark = (id) => {
    for (const b of buttons) b.setAttribute("aria-pressed", b.dataset.view === id ? "true" : "false");
  };
  seg.drop = (id) => {
    const b = buttons.find((x) => x.dataset.view === id);
    if (b) b.remove();
  };
  return seg;
}

export function rememberedView(key, fallback, allowed) {
  try {
    const v = window.localStorage.getItem(`program.view.${key}`);
    if (allowed.includes(v)) return v;
  } catch (_error) {
    /* no storage: the default view */
  }
  return fallback;
}

export function rememberView(key, view) {
  try {
    window.localStorage.setItem(`program.view.${key}`, view);
  } catch (_error) {
    /* no storage: the choice lasts the visit */
  }
}
