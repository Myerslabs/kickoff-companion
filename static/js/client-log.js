// Tablet problems reach the server log (added on the game night of 2026-09-26). Uncaught errors,
// rejected promises, and every console.error and console.warn the app writes are sent to
// POST /api/client-log, where they land in logs/app.log under kickoff.client. The console still
// gets everything as before. A report that fails to send is dropped quietly (logging it would
// loop), at most MAX_PER_MINUTE go out a minute, and the same message goes out once a minute.

const ENDPOINT = "/api/client-log";
const MAX_PER_MINUTE = 20;
const REPEAT_MS = 60 * 1000;

let installed = false;
let sending = false;
const sent = [];
const recent = new Map();

function describe(value) {
  if (value instanceof Error) return value.message || String(value);
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Whether a report may go out now (rate cap and repeat suppression). Exported for the tests. */
export function admit(message, now = Date.now()) {
  while (sent.length && now - sent[0] > 60 * 1000) sent.shift();
  if (sent.length >= MAX_PER_MINUTE) return false;
  const last = recent.get(message);
  if (last !== undefined && now - last < REPEAT_MS) return false;
  recent.set(message, now);
  if (recent.size > 200) recent.delete(recent.keys().next().value);
  sent.push(now);
  return true;
}

export function report(level, kind, parts, stack) {
  if (sending) return; // a report about a failing report would loop
  const message = parts.map(describe).join(" ").slice(0, 2000);
  if (!message || !admit(`${kind}|${message}`)) return;
  const body = { level, kind, message, stack: typeof stack === "string" ? stack.slice(0, 4000) : null, page: (typeof location !== "undefined" ? location.hash || "/" : null), agent: typeof navigator !== "undefined" ? navigator.userAgent.slice(0, 300) : null };
  sending = true;
  try {
    fetch(ENDPOINT, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), keepalive: true }).catch(() => {});
  } catch {
    // no network API: nothing to do
  } finally {
    sending = false;
  }
}

export function installClientLog() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = { error: console.error.bind(console), warn: console.warn.bind(console) };
  console.error = (...args) => {
    original.error(...args);
    report("error", "console", args, args.find((a) => a instanceof Error)?.stack);
  };
  console.warn = (...args) => {
    original.warn(...args);
    report("warn", "console", args, null);
  };
  window.addEventListener("error", (event) => {
    const where = event.filename ? ` at ${event.filename.replace(location.origin, "")}:${event.lineno}:${event.colno}` : "";
    report("error", "error", [`${event.message || "Script error"}${where}`], event.error?.stack);
  });
  window.addEventListener("unhandledrejection", (event) => {
    report("error", "rejection", [event.reason], event.reason?.stack);
  });
}
