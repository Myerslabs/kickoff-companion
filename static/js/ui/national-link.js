// Routes and list links (Phase 16, stream F). DOM-free, so Node tests can check the encoding.
//
// Frozen API (later streams call these; do not change the signatures):
//   ROUTE_IDS                                   Set of route ids the router accepts by default.
//   parseRoute(raw, valid = ROUTE_IDS)          "#national=advanced%3Adefense_explosiveness?team=Ole%20Miss"
//                                               -> { id, arg, params, query, key } or null (unknown id, bad encoding).
//                                               params is a plain object of strings; query is its canonical
//                                               form (sorted keys) and key = "id=arg?query" (the router's currentKey).
//   routeKey(route)                             the same key for a route object.
//   nationalHref(metric, { team, year, scope }) "#national=<metric>?team=&year=&scope=conference", or null when the
//                                               metric is not a registry-shaped key (family:key, at most 60 chars).
//   nationalRoute(route)                        { metric, team, year, scope } read back from a parsed national route.
//   pollHref(poll, { team })                    the national list of a poll ("poll:AP"), or null for an unknown poll.
//   pollsPageHref(poll)                         "#season=polls:AP", the Season polls band on that poll (Full page).
//   pollName(value)                             "AP Top 25" -> "AP", "Coaches Poll" -> "Coaches", "Playoff Committee Rankings" -> "CFP".
//   metricLink({ team, year, scope, key })      a column hook for statTable: (row) => href from row[key] (default "metric"), or null.
//   isListHref(href)                            true for a "#national=" link.
//
// Scope is "national" (the default, left out of the link) or "conference". Year is four digits and only
// ever the season or the one before (the server refuses others). A team is at most 80 characters and only
// highlights a row; it never changes what the server fetches.

export const ROUTE_IDS = new Set([
  "season", "leaders", "roster", "recruiting", "newspaper", "program", "team", "live", "archive",
  "settings", "ratings", "glossary", "national", "radio", "injuries",
]);

export const METRIC_RE = /^[a-z]+:[A-Za-z0-9_:]+$/;
const MAX_METRIC = 60;
const MAX_TEAM = 80;
const MAX_PARAM = 120;
const SCOPES = new Set(["national", "conference", "opponents", "mine"]); // opponents and mine: public release Phase 5b

function clean(value, max) {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const s = String(value).trim();
  return s && s.length <= max ? s : null;
}

export function isMetric(metric) {
  return typeof metric === "string" && metric.length <= MAX_METRIC && METRIC_RE.test(metric);
}

function queryOf(params) {
  return Object.keys(params)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join("&");
}

/** One route's key for the router: the same page with a different highlighted team is a different key. */
export function routeKey(route) {
  if (!route || typeof route.id !== "string") return "";
  const query = typeof route.query === "string" ? route.query : queryOf(route.params && typeof route.params === "object" ? route.params : {});
  return `${route.id}=${route.arg ?? ""}${query ? `?${query}` : ""}`;
}

function decode(part) {
  try {
    return decodeURIComponent(part);
  } catch {
    return undefined; // a stray '%' in a hand-typed link
  }
}

/** Parse a hash (with or without '#'). Unknown ids and undecodable text give null, never a throw. */
export function parseRoute(raw, valid = ROUTE_IDS) {
  if (typeof raw !== "string") return null;
  const hash = raw.replace(/^#/, "");
  if (!hash) return null;
  const q = hash.indexOf("?");
  const head = q >= 0 ? hash.slice(0, q) : hash;
  const tail = q >= 0 ? hash.slice(q + 1) : "";
  const eq = head.indexOf("=");
  const id = eq >= 0 ? head.slice(0, eq) : head;
  if (!(valid instanceof Set ? valid.has(id) : Array.isArray(valid) && valid.includes(id))) return null;
  let arg = null;
  if (eq >= 0) {
    const decoded = decode(head.slice(eq + 1));
    if (decoded === undefined) return null;
    arg = decoded.trim() === "" ? null : decoded;
  }
  const params = {};
  if (tail) {
    for (const pair of tail.split("&")) {
      if (!pair) continue;
      const at = pair.indexOf("=");
      const key = decode((at >= 0 ? pair.slice(0, at) : pair).replace(/\+/g, " "));
      const value = decode((at >= 0 ? pair.slice(at + 1) : "").replace(/\+/g, " "));
      if (key === undefined || value === undefined) continue;
      const k = clean(key, 24);
      const v = clean(value, MAX_PARAM);
      if (k && v !== null && /^[A-Za-z][\w-]*$/.test(k)) params[k] = v;
    }
  }
  const query = queryOf(params);
  const route = { id, arg, params, query };
  route.key = routeKey(route);
  return route;
}

/** The link a national (or conference) rank chip opens. Null when the metric is missing or malformed. */
export function nationalHref(metric, { team, year, scope } = {}) {
  if (!isMetric(metric)) return null;
  const parts = [];
  const t = clean(team, MAX_TEAM);
  if (t) parts.push(`team=${encodeURIComponent(t)}`);
  const y = clean(year, 4);
  if (y && /^\d{4}$/.test(y)) parts.push(`year=${y}`);
  if (scope !== "national" && SCOPES.has(scope)) parts.push(`scope=${scope}`);
  return `#national=${encodeURIComponent(metric)}${parts.length ? `?${parts.join("&")}` : ""}`;
}

/** What a national route asks for, validated: bad pieces come back null (scope falls back to national). */
export function nationalRoute(route) {
  const params = route && typeof route.params === "object" && route.params ? route.params : {};
  const metric = route && isMetric(route.arg) ? route.arg : null;
  const year = typeof params.year === "string" && /^\d{4}$/.test(params.year) ? Number(params.year) : null;
  const scope = SCOPES.has(params.scope) ? params.scope : "national";
  return { metric, team: clean(params.team, MAX_TEAM), year, scope };
}

/** "AP", "Coaches" or "CFP" for the names CFBD and the payloads use; null for anything else. */
export function pollName(value) {
  if (typeof value !== "string") return null;
  const s = value.trim();
  if (/^ap\b/i.test(s)) return "AP";
  if (/coach/i.test(s)) return "Coaches";
  if (/^cfp\b|playoff|committee/i.test(s)) return "CFP";
  return null;
}

export function pollHref(poll, { team } = {}) {
  const short = pollName(poll);
  return short ? nationalHref(`poll:${short}`, { team }) : null;
}

export function pollsPageHref(poll) {
  const short = pollName(poll);
  return short ? `#season=${encodeURIComponent(`polls:${short}`)}` : "#season";
}

/** A statTable link hook: the row's metric key (row.metric by default) as a national-list link. */
export function metricLink({ team, year, scope, key = "metric" } = {}) {
  return (row) => (row && typeof row === "object" ? nationalHref(row[key], { team: typeof team === "function" ? team(row) : team, year, scope }) : null);
}

export function isListHref(href) {
  return typeof href === "string" && href.startsWith("#national=");
}
