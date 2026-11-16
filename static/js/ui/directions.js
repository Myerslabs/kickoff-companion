// Directions to the stadium (ENH-15, owner 2026-10-23): a link-out to the device's own maps app, which plans the route from
// where the device is; the app never sees the location and draws no map of its own. The app is the device's choice in
// Settings (prefs.js mapApp: Google Maps by default, Apple Maps, Waze, or Ask each time, which offers the three).
//
//   directionsHref(place, app)   the link for one app; place: { name, city, state, latitude, longitude } (the program's
//                                `trip` or a venueDetail); coordinates when there are, else the stadium's name and town
//   directionsLink(place, { label })   the link (or, with Ask each time, a Directions button that shows the three); null
//                                with nowhere to go
//   MAP_LABELS                   each app's name, for the links' words

import { MAP_APPS, mapApp } from "../prefs.js";
import { el, isNum } from "./dom.js";

export const MAP_LABELS = Object.fromEntries(MAP_APPS.map((m) => [m.id, m.label]));

function coords(place) {
  const lat = place?.latitude;
  const lon = place?.longitude;
  return isNum(lat) && isNum(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0) ? `${lat.toFixed(6)},${lon.toFixed(6)}` : null;
}

function words(place) {
  const parts = [place?.name, place?.city, place?.state].filter((w) => typeof w === "string" && w.trim()).map((w) => w.trim());
  return parts.length ? parts.join(", ") : null;
}

export function directionsHref(place, app = "google") {
  if (!place || typeof place !== "object") return null;
  const at = coords(place);
  const named = words(place);
  if (!at && !named) return null;
  if (app === "apple") return `https://maps.apple.com/?daddr=${encodeURIComponent(at || named)}${named ? `&q=${encodeURIComponent(place.name || named)}` : ""}`;
  if (app === "waze") return at ? `https://waze.com/ul?ll=${encodeURIComponent(at)}&navigate=yes` : `https://waze.com/ul?q=${encodeURIComponent(named)}&navigate=yes`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(at || named)}`;
}

function outLink(href, text, cls = "btn btn--quiet directions") {
  return el("a", { class: cls, href, target: "_blank", rel: "noopener" }, text);
}

export function directionsLink(place, { label = "Directions" } = {}) {
  const app = mapApp();
  if (app !== "ask") {
    const href = directionsHref(place, app);
    return href ? outLink(href, `${label} in ${MAP_LABELS[app]}`) : null;
  }
  const apps = MAP_APPS.filter((m) => m.id !== "ask").map((m) => ({ ...m, href: directionsHref(place, m.id) })).filter((m) => m.href);
  if (!apps.length) return null;
  const list = el("span", { class: "directions__apps" }, apps.map((m) => outLink(m.href, m.label, "btn btn--quiet directions__app")));
  list.setAttribute("hidden", "");
  const button = el("button", { class: "btn btn--quiet directions", type: "button", "aria-expanded": "false", onclick: () => {
    const open = list.hasAttribute("hidden");
    if (open) list.removeAttribute("hidden");
    else list.setAttribute("hidden", "");
    button.setAttribute("aria-expanded", open ? "true" : "false");
  } }, label);
  return el("span", { class: "directions__ask" }, button, list);
}
