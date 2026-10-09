// The score strip (L1): one line on wide screens, two on narrow. The broadcast owns the
// score and the clock; this only repeats them so the rest of the sheet has context.

import { el, fmtClock, isNum, period, situationText, text } from "./dom.js";
import { pill } from "./pills.js";

function timeouts(remaining, label) {
  if (!isNum(remaining)) return null;
  const dots = [];
  for (let i = 0; i < 3; i += 1) dots.push(el("span", { class: `to-dot${i < remaining ? "" : " to-dot--used"}` }));
  return el("span", { class: "strip__timeouts", title: `${label} timeouts left: ${remaining}` }, `${label} `, dots);
}

/**
 * strip({ us: {abbr, points, timeouts}, them: {abbr, points, timeouts}, possession: "us"|"them"|null,
 *         status: "pre"|"live"|"halftime"|"final", period, clock,
 *         down, distance, yardsToGoal, pill: {kind, label}, tools, sticky })
 * Returns the element with setPill(pill).
 */
export function strip(props) {
  const { us = {}, them = {}, possession = null, status = "live", tools, sticky = true } = props;
  const teamNode = (side, team) =>
    el("span", { class: `strip__team strip__team--${side}${possession === side ? " strip__team--poss" : ""}` }, text(team.abbr));
  const pts = (team, side) => el("span", { class: "strip__pts", dataset: { k: `strip:${side}` } }, isNum(team.points) ? String(team.points) : "–"); // Phase 16 wave 3: flashes when it changes

  const score = el("div", { class: "strip__score" }, teamNode("us", us), pts(us, "us"), el("span", { class: "strip__sep" }, "·"), teamNode("them", them), pts(them, "them"));

  let clockNode;
  if (status === "final") clockNode = el("span", { class: "strip__final" }, "Final");
  else if (status === "halftime") clockNode = el("span", { class: "strip__clock" }, "Halftime");
  else if (status === "pre") clockNode = el("span", { class: "strip__clock" }, props.kickoffText || "Pregame");
  else clockNode = el("span", { class: "strip__clock" }, `${period(props.period)} ${fmtClock(props.clock)}`);

  let situation = null;
  if (status === "live" && isNum(props.down)) {
    const offense = possession === "them" ? them : us;
    const defense = possession === "them" ? us : them;
    situation = el(
      "span",
      { class: "strip__situation" },
      `${text(offense.abbr)} ball · ${situationText({
        down: props.down,
        distance: props.distance,
        yardsToGoal: props.yardsToGoal,
        offenseAbbr: offense.abbr,
        defenseAbbr: defense.abbr,
      })}`,
    );
  }

  // The pill sits before an empty marker so setPill can swap it in place between redraws.
  let pillNode = props.pill ? pill(props.pill) : null;
  let pillKey = props.pill ? `${props.pill.kind}|${props.pill.label}` : "";
  const pillMark = document.createComment("pill");
  const right = el(
    "div",
    { class: "strip__right" },
    status === "live" ? [timeouts(us.timeouts, text(us.abbr)), timeouts(them.timeouts, text(them.abbr))] : null,
    pillNode,
    pillMark,
    tools || null,
  );

  const root = el("div", { class: `strip${sticky ? "" : " strip--static"}`, role: "region", "aria-label": "Score" }, score, clockNode, situation, right);
  /** setPill({kind, label}) or setPill(null): change the status pill without redrawing the strip. */
  root.setPill = (next) => {
    const key = next ? `${next.kind}|${next.label}` : "";
    if (key === pillKey) return; // the same words: leave the node, so a screen reader is not told twice
    pillKey = key;
    if (pillNode) pillNode.remove();
    pillNode = next ? pill(next) : null;
    if (pillNode) right.insertBefore(pillNode, pillMark);
  };
  return root;
}
