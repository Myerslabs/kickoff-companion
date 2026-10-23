// One of In Game's panels asked for from the menu (the layout pass, owner 2026-10-22): the menu sends the reader to In Game
// and leaves the request here; In Game opens it wide as soon as its panels are built (views/live.js). On In Game itself the
// request arrives as the document event "kickoff:live-panel" instead.
//
//   askLivePanel(detail)   leave { id, steps, back } for In Game
//   takeLivePanel()        In Game takes it (once), or null

let waiting = null;

export function askLivePanel(detail) {
  waiting = detail && typeof detail === "object" && typeof detail.id === "string" ? detail : null;
}

export function takeLivePanel() {
  const detail = waiting;
  waiting = null;
  return detail;
}
