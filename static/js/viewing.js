// Switch teams (batch 3, owner 2026-11-16: "I want to be able to have all the features of our current my team, but it just
// doesnt save ... She wants to be able to switch teams at will, like to the gators opponent so she can see what they are
// talking about"). A device can look at the app as another FBS team: My Team, this week's Pre-Game Program and its
// Post-Game, the roster and recruiting follow that team. Only this device, only this visit (sessionStorage: until Back to
// <our team> or the tab closes); nothing goes to the server and nothing is kept, so a guest can switch too.
//
//   viewing()              the school this device is switched to, or null (ours, or nothing stored)
//   viewingInfo()          { school, abbreviation, conference, logo, logoDark } as stored, or null
//   setViewing(info)       switch (an object with a school, or a school's name); our own school clears
//   clearViewing()         back to our team
//   onViewing(fn)          called with viewingInfo() after every change; returns the unsubscribe
//   viewRoute(route)       the route with ?team=<school> added when the page follows the switch and names no team itself
//                          (the Program and the Post-Game only bare: #program=<game id> is a game of ours, kept ours)

import { usSchool } from "./identity.js";

const KEY = "kickoff:viewing";

/** The pages that follow the switch. Our own pages (the Archive, Seasons, the season in review, Claude's runs) stay ours. */
export const FOLLOWS = new Set(["season", "roster", "recruiting", "program", "postgame", "newspaper"]); // the paper: b3-their-paper

const listeners = new Set();

const str = (value) => (typeof value === "string" ? value.trim() : "");

function clean(info) {
  const raw = typeof info === "string" ? { school: info } : info && typeof info === "object" ? info : null;
  const school = raw ? str(raw.school) : "";
  if (!school || school.length > 80) return null;
  const out = { school };
  for (const key of ["abbreviation", "conference", "logo", "logoDark", "mascot"]) {
    const value = str(raw[key]);
    if (value && value.length <= 300) out[key] = value;
  }
  return out;
}

function read() {
  try {
    const raw = globalThis.sessionStorage?.getItem(KEY);
    return raw ? clean(JSON.parse(raw)) : null;
  } catch {
    return null; // storage refused or the stored copy unreadable: ours
  }
}

let current = read();

function write(info) {
  try {
    if (info) globalThis.sessionStorage?.setItem(KEY, JSON.stringify(info));
    else globalThis.sessionStorage?.removeItem(KEY);
  } catch {
    // a private window may refuse storage: the switch still holds until the page reloads
  }
}

function tell() {
  const info = viewingInfo();
  for (const fn of [...listeners]) {
    try {
      fn(info);
    } catch (error) {
      console.error("A page did not follow the team switch.", error);
    }
  }
  try {
    document.dispatchEvent(new CustomEvent("kickoff:viewing", { detail: info }));
  } catch {
    // no document (the tests under Node)
  }
}

export function viewingInfo() {
  if (!current) return null;
  return current.school === usSchool() ? null : current;
}

export function viewing() {
  const info = viewingInfo();
  return info ? info.school : null;
}

export function setViewing(info) {
  const next = clean(info);
  if (!next || next.school === usSchool()) {
    clearViewing();
    return;
  }
  if (current && current.school === next.school && JSON.stringify(current) === JSON.stringify(next)) return;
  current = next;
  write(current);
  tell();
}

export function clearViewing() {
  if (!current) return;
  current = null;
  write(null);
  tell();
}

export function onViewing(fn) {
  if (typeof fn !== "function") return () => {};
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function viewRoute(route) {
  const school = viewing();
  if (!school || !route || typeof route !== "object" || !FOLLOWS.has(route.id)) return route;
  const params = route.params && typeof route.params === "object" ? route.params : {};
  if (str(params.team)) return route; // a page that names its team keeps it (ours too: ?team=<our school>)
  if ((route.id === "program" || route.id === "postgame") && route.arg) return route; // a game by id (the Archive, Seasons, Last/Next): our game, from our side
  if (route.id === "newspaper" && route.arg) return route; // a week's edition of our paper, opened from our line
  return { ...route, params: { ...params, team: school } };
}

/** The tests start each case from ours. */
export function _resetViewing() {
  current = null;
  listeners.clear();
}
