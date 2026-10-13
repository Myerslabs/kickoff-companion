// The radio's station list (X4): what is playing, then one 44 px row per source with its Play or Stop. The Pre-Game
// Program's Radio band and In Game's Radio sheet both draw it (owner 2026-10-11: "the radio is always available in the
// big screen and in game, even before the game"). The player itself lives in the shell's dock, so the audio keeps
// playing when the view changes; this list only starts and stops it.
//
//   radioStations({ onDraw })   -> <div class="radio-panel">, redrawn on every radio change; it stops listening once it
//                                  has been on the page and left it. onDraw(snap) runs after each draw (a band's summary).

import { loadRadioSources, radioHelpBlock, radioSnapshot, startRadio, stateText, stopRadio, subscribeRadio } from "../radio.js";
import { el, replaceWith, text } from "./dom.js";
import { note } from "./states.js";

const KIND_WORD = { stream: "stream", embed: "station player", link: "opens a tab" };

export function radioStations({ onDraw } = {}) {
  const host = el("div", { class: "radio-panel radio-panel--compact" });
  let attached = false;
  const draw = (snap) => {
    const current = snap.current;
    const sources = Array.isArray(snap.sources) ? snap.sources : [];
    replaceWith(
      host,
      snap.loadError ? note(snap.loadError, { kind: "error", lead: "Radio unavailable." }) : null,
      !snap.loaded && !snap.loadError ? el("p", { class: "note" }, "Loading the radio sources.") : null,
      snap.loaded && !snap.loadError && sources.length === 0 ? (radioHelpBlock(snap.help) || el("p", { class: "note" }, "No radio station yet. ", el("a", { href: "#settings" }, "Add one in Settings"), ".")) : null,
      current ? el("p", { class: "radio-now" }, el("b", {}, text(current.name)), ` · ${stateText(snap.state)}${snap.detail ? ` · ${snap.detail}` : ""}. The controls stay in the bar at the bottom of every page.`) : null,
      sources.map((source) =>
        el(
          "div",
          { class: "radio-source radio-source--row", "aria-current": current?.id === source.id ? "true" : null },
          el("span", { class: "radio-source__name" }, text(source.name)),
          el("span", { class: "radio-source__kind" }, KIND_WORD[source.kind] || text(source.kind)),
          el("button", { class: `btn${current?.id === source.id ? " btn--primary" : ""}`, type: "button", onclick: () => (current?.id === source.id ? stopRadio() : startRadio(source)) }, current?.id === source.id ? "Stop" : source.kind === "link" ? "Open" : "Play"),
        ),
      ),
      snap.note ? el("p", { class: "note" }, snap.note) : null,
    );
    if (typeof onDraw === "function") {
      try {
        onDraw(snap);
      } catch (error) {
        console.error("radio: a station list's caller failed to follow it.", error);
      }
    }
  };
  draw(radioSnapshot());
  const unsubscribe = subscribeRadio((snap) => {
    if (host.isConnected) attached = true;
    if (attached && !host.isConnected) {
      unsubscribe();
      return;
    }
    draw(snap);
  });
  loadRadioSources();
  return host;
}
