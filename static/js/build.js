// The build this page was loaded with (Phase 12). Every API envelope carries meta.build and the
// live stream's hello carries build; the first one seen is this page's. When a later one differs,
// the server restarted or a file under static/ changed, so this page runs old code: one
// "kickoff:update" event goes out and the shell offers a reload.

let first = null;
let announced = false;

/** Note a build id from the server; returns true the first time it differs from this page's. */
export function noteBuild(id) {
  if (typeof id !== "string" || !id) return false;
  if (first === null) {
    first = id;
    return false;
  }
  if (id === first || announced) return false;
  announced = true;
  if (typeof document !== "undefined" && typeof CustomEvent === "function") {
    document.dispatchEvent(new CustomEvent("kickoff:update", { detail: { build: id, loaded: first } }));
  }
  return true;
}

/** For the tests: forget what was seen. */
export function resetBuild() {
  first = null;
  announced = false;
}
