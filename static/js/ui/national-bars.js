// GX-04 (owner look, Phase 16 NV): how far a team is from #1 and from the middle, at a glance. On the
// national list the value cell gets an Excel-style data bar behind the number (neutral fill, ours
// orange, the next opponent's --opp) with a faint FBS-median tick, a Pctl column reads "88th", and a
// one-line strip above the table draws every team as a 2 px tick with ours tall, in the accent color and labelled.
// Player lists get the bars too. Nothing here fetches; the scale comes from the list's own values.
//
//   percentile(rank, of)                 0-100 (the share of the list ranked below), or null.
//   pctlText(p)                          "88th", or a dash.
//   median(values)                       the median of the finite values, or null.
//   barScale(values, { higher, zero })   { lo, hi, median, frac(v) } or null when no value is finite. frac is the
//                                        value's place between the worst and the best (0 to 1, reversed when
//                                        lower is better); zero: true anchors the scale at 0 (top-N lists, where
//                                        the rest of the population is not in the answer).
//   barCell(row, { scale, format })      the value cell: bar, median tick and the formatted number.
//   distributionStrip(data, scale)       the strip, or null for player and poll lists or fewer than 3 values.

import { DASH, el, fmtStat, isNum, ordinal, text } from "./dom.js";

export function percentile(rank, of) {
  if (!isNum(rank) || !isNum(of) || of < 2 || rank < 1 || rank > of) return null;
  return Math.round((100 * (of - rank)) / (of - 1));
}

export function pctlText(p) {
  return isNum(p) ? ordinal(p) : DASH;
}

export function median(values) {
  const finite = (Array.isArray(values) ? values : []).filter(isNum).sort((a, b) => a - b);
  if (!finite.length) return null;
  const mid = Math.floor(finite.length / 2);
  return finite.length % 2 ? finite[mid] : (finite[mid - 1] + finite[mid]) / 2;
}

export function barScale(values, { higher = true, zero = false } = {}) {
  const finite = (Array.isArray(values) ? values : []).filter(isNum);
  if (!finite.length) return null;
  let lo = Math.min(...finite);
  let hi = Math.max(...finite);
  if (zero) {
    lo = Math.min(0, lo);
    hi = Math.max(0, hi);
  }
  const frac = (v) => {
    if (!isNum(v)) return null;
    if (hi === lo) return 1;
    const f = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
    return higher === false ? 1 - f : f;
  };
  const mid = median(finite);
  return { lo, hi, median: mid, frac, medianFrac: zero ? null : frac(mid) };
}

function pct(f) {
  return `${Math.round(f * 1000) / 10}%`;
}

function tone(row) {
  if (row?.isUs === true) return " nat-bar--us";
  if (row?.isNext === true) return " nat-bar--next";
  return "";
}

export function barCell(row, { scale, format } = {}) {
  const value = row?.value;
  const shown = fmtStat(value, format);
  const f = scale ? scale.frac(value) : null;
  if (!isNum(f)) return el("span", { class: "nat-bar nat-bar--none" }, el("span", { class: "nat-bar__value" }, shown));
  return el(
    "span",
    { class: `nat-bar${tone(row)}`, style: { "--bar": pct(f), "--mid": isNum(scale.medianFrac) ? pct(scale.medianFrac) : null } },
    el("span", { class: "nat-bar__fill", "aria-hidden": "true" }),
    isNum(scale.medianFrac) ? el("span", { class: "nat-bar__median", "aria-hidden": "true" }) : null,
    el("span", { class: "nat-bar__value" }, shown),
  );
}

function edge(f) {
  if (f > 0.8) return " nat-strip__label--end";
  if (f < 0.2) return " nat-strip__label--start";
  return "";
}

export function distributionStrip(data, scale) {
  const d = data && typeof data === "object" ? data : {};
  if (!scale || d.unit === "player" || d.family === "poll") return null;
  const rows = (Array.isArray(d.rows) ? d.rows : []).filter((r) => r && typeof r === "object" && isNum(r.value));
  if (rows.length < 3) return null;
  const format = typeof d.format === "string" ? d.format : "2f";
  const us = rows.find((r) => r.isUs === true);
  const them = rows.find((r) => r.isNext === true && r.isUs !== true);
  const ticks = rows.filter((r) => r !== us && r !== them).map((r) => el("span", { class: "nat-strip__tick", style: { left: pct(scale.frac(r.value)) } }));
  const best = rows.reduce((a, r) => (scale.frac(r.value) > scale.frac(a.value) ? r : a), rows[0]);
  const worst = rows.reduce((a, r) => (scale.frac(r.value) < scale.frac(a.value) ? r : a), rows[0]);
  const marks = [];
  if (isNum(scale.medianFrac)) marks.push(el("span", { class: "nat-strip__median", style: { left: pct(scale.medianFrac) } }));
  if (them) marks.push(el("span", { class: "nat-strip__tick nat-strip__tick--next", style: { left: pct(scale.frac(them.value)) } }));
  if (us) {
    const f = scale.frac(us.value);
    marks.push(el("span", { class: "nat-strip__tick nat-strip__tick--us", style: { left: pct(f) } }, el("span", { class: `nat-strip__label${edge(f)}` }, `${text(us.team)} ${fmtStat(us.value, format)}`)));
  }
  const spoken = [us ? `${text(us.team)} ${fmtStat(us.value, format)}` : null, isNum(scale.median) ? `median ${fmtStat(scale.median, format)}` : null, `best ${text(best.team)} ${fmtStat(best.value, format)}`].filter(Boolean).join(", ");
  return el(
    "div",
    { class: "nat-strip", role: "img", "aria-label": `Every team on one line: ${spoken}` },
    el("div", { class: "nat-strip__axis", "aria-hidden": "true" }, ticks, marks),
    el(
      "div",
      { class: "nat-strip__ends", "aria-hidden": "true" },
      el("span", {}, `${fmtStat(worst.value, format)} ${text(worst.team)}`),
      isNum(scale.median) ? el("span", { class: "nat-strip__mid" }, `median ${fmtStat(scale.median, format)}`) : null,
      el("span", {}, `${text(best.team)} ${fmtStat(best.value, format)}`),
    ),
  );
}
