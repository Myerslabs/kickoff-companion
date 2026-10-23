// The To do flyout (the layout pass, owner 2026-10-22: the To do note at the top of every page, "dont show that unless its
// in its own flyout"). The notes of ui/page-notes.js (Not loaded yet, a new version on the server, the server's code
// updated, a newer release, On this day, a guest's welcome) never sit above a page any more: their one note waits off the
// page, the Menu button carries their count and every list of the menu a To do row at its top (ui/shell.js), which opens
// this flyout, as wide as every other (about 83%), with the note inside. The note's own × gives way to the flyout's
// "Clear the list" at its foot (every item listed goes, each telling its owner, as the × did); closing the flyout keeps
// them for later. The flyout follows the list while it is open and closes itself when the last item goes. The trivia's
// join is the corner popup on every page instead (ui/trivia.js). Nothing here opens by itself.
//
//   openTodo()    the flyout's handle, or null when there is nothing to do (or it is open already)

import { el } from "./dom.js";
import { dismissAll, noteCount, parkNotes, takeNotes } from "./page-notes.js";
import { openSheet } from "./remote.js";

let open = null; // the open flyout's handle

function words(count) {
  return count === 1 ? "One thing to look at" : `${count} things to look at`;
}

export function openTodo() {
  if (open || noteCount() < 1) return null;
  const holder = el("div", { class: "todo-flyout" });
  const clear = el("button", { class: "btn todo-flyout__clear", type: "button", onclick: () => dismissAll() }, "Clear the list");
  const onNotes = (event) => {
    const n = Number(event?.detail?.count);
    if (!open) return;
    if (!Number.isFinite(n) || n < 1) open.close(); // the last item went: nothing left to show
    else open.setSubtitle(words(n));
  };
  open = openSheet({
    title: "To do",
    subtitle: words(noteCount()),
    wide: true,
    className: "todo-sheet",
    body: holder,
    foot: el("div", { class: "todo-flyout__foot" }, clear),
    onClose: () => {
      document.removeEventListener("kickoff:notes", onNotes);
      parkNotes(); // the note goes back off the page, every item kept
      open = null;
    },
  });
  const host = takeNotes(); // every item listed is seen now; one added while the flyout is open shows here at once
  if (!host) {
    open.close();
    return null;
  }
  holder.append(host);
  document.addEventListener("kickoff:notes", onNotes);
  return open;
}
