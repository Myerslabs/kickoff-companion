// The situational grid (L4): third down, fourth down, red zone, turnovers, penalties,
// time of possession, yards per play. Both teams, the better side in chalk.

import { el, fmtNum, isNum, text } from "./dom.js";

function pair(made, of) {
  return isNum(made) && isNum(of) ? `${made}-${of}` : "–";
}

function rate(made, of) {
  return isNum(made) && isNum(of) && of > 0 ? made / of : null;
}

/** rows: [{label, us, them, usValue, themValue, higherIsBetter}] where values are display strings */
function rowsFor(us, them) {
  const u = us.box || {};
  const t = them.box || {};
  return [
    { label: "Third down", us: pair(u.thirdDown?.made, u.thirdDown?.of), them: pair(t.thirdDown?.made, t.thirdDown?.of), usValue: rate(u.thirdDown?.made, u.thirdDown?.of), themValue: rate(t.thirdDown?.made, t.thirdDown?.of), higherIsBetter: true },
    { label: "Fourth down", us: pair(u.fourthDown?.made, u.fourthDown?.of), them: pair(t.fourthDown?.made, t.fourthDown?.of), usValue: rate(u.fourthDown?.made, u.fourthDown?.of), themValue: rate(t.fourthDown?.made, t.fourthDown?.of), higherIsBetter: true },
    { label: "Red zone", us: pair(u.redZone?.scores, u.redZone?.trips), them: pair(t.redZone?.scores, t.redZone?.trips), usValue: rate(u.redZone?.scores, u.redZone?.trips), themValue: rate(t.redZone?.scores, t.redZone?.trips), higherIsBetter: true },
    { label: "Turnovers", us: fmtNum(u.turnovers), them: fmtNum(t.turnovers), usValue: u.turnovers, themValue: t.turnovers, higherIsBetter: false },
    { label: "Penalties", us: pair(u.penalties?.count, u.penalties?.yards), them: pair(t.penalties?.count, t.penalties?.yards), usValue: u.penalties?.yards, themValue: t.penalties?.yards, higherIsBetter: false },
    { label: "Time of possession", us: text(u.possessionTime), them: text(t.possessionTime), usValue: null, themValue: null },
    { label: "Yards per play", us: fmtNum(u.yardsPerPlay, 1), them: fmtNum(t.yardsPerPlay, 1), usValue: u.yardsPerPlay, themValue: t.yardsPerPlay, higherIsBetter: true },
    { label: "Total yards", us: fmtNum(u.totalYards), them: fmtNum(t.totalYards), usValue: u.totalYards, themValue: t.totalYards, higherIsBetter: true },
  ];
}

function tone(row, side) {
  if (!isNum(row.usValue) || !isNum(row.themValue) || row.usValue === row.themValue || row.higherIsBetter === undefined) return "";
  const usLeads = row.higherIsBetter ? row.usValue > row.themValue : row.usValue < row.themValue;
  const leads = side === "us" ? usLeads : !usLeads;
  return leads ? " sit__val--lead" : " sit__val--trail";
}

/** situationGrid({ us: {abbr, box}, them: {abbr, box} }) */
export function situationGrid({ us = {}, them = {} }) {
  const rows = rowsFor(us, them);
  const half = Math.ceil(rows.length / 2);
  const grid = (subset) =>
    el(
      "div",
      { class: "sit", role: "table" },
      el("div", { class: "sit__head sit__head--label" }, ""),
      el("div", { class: "sit__head" }, text(us.abbr)),
      el("div", { class: "sit__head" }, text(them.abbr)),
      subset.map((row) => [
        el("div", { class: "sit__label" }, row.label),
        el("div", { class: `sit__val${tone(row, "us")}` }, row.us),
        el("div", { class: `sit__val${tone(row, "them")}` }, row.them),
      ]),
    );
  return el("div", { class: "sit-wrap" }, grid(rows.slice(0, half)), grid(rows.slice(half)));
}

export function situationSkeleton() {
  return el("div", { class: "sit-wrap" }, el("div", {}, Array.from({ length: 4 }, () => el("div", { class: "skel skel--row" }))), el("div", {}, Array.from({ length: 4 }, () => el("div", { class: "skel skel--row" }))));
}
