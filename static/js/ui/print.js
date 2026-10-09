// Print the program (Phase 19, owner's idea "print the program"). One button on the Game program opens a small sheet: the
// paper (Letter, A4 or Legal), portrait or landscape, then Print. The page prints in the light theme, one column, every
// folded section opened, without the top bar, tabs, radio or buttons (the @media print rules in components.css). The
// paper choice is applied as an @page rule only for the moment of printing and is remembered on this device.
//
//   PAPERS                     [id, label, css size]
//   pageRule(paper, orient)    the @page rule text (exported for the tests)
//   openPrintSheet()           the sheet; returns its handle
//   printButton()              the small "Print" button for a page

import { el } from "./dom.js";
import { openSheet } from "./remote.js";

export const PAPERS = [["letter", "Letter (8.5 x 11 in)", "letter"], ["a4", "A4 (210 x 297 mm)", "A4"], ["legal", "Legal (8.5 x 14 in)", "legal"]];
const KEY = "kickoff.print";

export function pageRule(paper, orientation) {
  const size = (PAPERS.find(([id]) => id === paper) || PAPERS[0])[2];
  const orient = orientation === "landscape" ? "landscape" : "portrait";
  return `@page { size: ${size} ${orient}; margin: 12mm; }`;
}

function recall() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    return { paper: PAPERS.some(([id]) => id === raw.paper) ? raw.paper : "letter", orientation: raw.orientation === "landscape" ? "landscape" : "portrait" };
  } catch {
    return { paper: "letter", orientation: "portrait" };
  }
}

function remember(choice) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(choice));
  } catch {
    // blocked storage: the choice lasts until the page closes
  }
}

export function printNow(choice, doc = document, win = window) {
  const style = doc.createElement("style");
  style.setAttribute("id", "print-page");
  style.textContent = pageRule(choice.paper, choice.orientation);
  (doc.head || doc.body).append(style);
  const root = doc.documentElement;
  const theme = root.dataset.theme;
  root.dataset.theme = "light"; // ink on white, whatever the screen shows
  doc.body.classList.add("printing");
  const done = () => {
    style.remove();
    doc.body.classList.remove("printing");
    if (theme === undefined) delete root.dataset.theme;
    else root.dataset.theme = theme;
    win.removeEventListener?.("afterprint", done);
  };
  win.addEventListener?.("afterprint", done);
  if (typeof win.print === "function") win.print();
  else done();
  return done;
}

export function openPrintSheet() {
  const choice = recall();
  const paper = el("select", { class: "setting__select", "aria-label": "Paper", onchange: (event) => { choice.paper = event.target.value; remember(choice); } }, PAPERS.map(([id, label]) => el("option", { value: id, selected: id === choice.paper ? true : null }, label)));
  const orient = el("select", { class: "setting__select", "aria-label": "Orientation", onchange: (event) => { choice.orientation = event.target.value; remember(choice); } }, [["portrait", "Portrait"], ["landscape", "Landscape"]].map(([id, label]) => el("option", { value: id, selected: id === choice.orientation ? true : null }, label)));
  let handle = null;
  const go = el("button", { class: "btn btn--primary", type: "button", onclick: () => { handle?.close?.(); setTimeout(() => printNow(choice), 250); } }, "Print");
  handle = openSheet({
    title: "Print the program",
    body: () => el("div", { class: "settings" }, el("p", { class: "note" }, "Prints this page in ink on white: one column, every section open, no menus or buttons."), el("label", { class: "print-field" }, "Paper ", paper), el("label", { class: "print-field" }, "Orientation ", orient), el("p", { class: "settings__actions" }, go)),
  });
  return handle;
}

export function printButton() {
  return el("button", { class: "btn btn--quiet print-button", type: "button", "aria-haspopup": "dialog", onclick: () => openPrintSheet() }, "Print");
}
