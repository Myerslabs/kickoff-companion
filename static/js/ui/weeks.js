// How a game's week reads on the page (Phase 15). CFBD numbers every bowl and playoff game
// "postseason week 1", so a postseason game shows its round or "Bowl" instead of a week number.
// The server sends `postseason` (the bowl's name, or null in the regular season) and `playoffRound`.

import { text } from "./dom.js";

const ROUND_SHORT = { "First Round": "CFP R1", Quarterfinal: "CFP QF", Semifinal: "CFP SF", "National Championship": "Title", Playoff: "CFP" };

/** "wk 3", "CFP QF", "Title", "Bowl". */
export function weekShort(game) {
  if (game && (game.postseason || game.playoffRound || game.seasonType === "postseason")) {
    return ROUND_SHORT[game.playoffRound] || (game.playoffRound ? "CFP" : "Bowl");
  }
  return `wk ${text(game?.week)}`;
}

/** "Week 3", or the bowl's own name ("College Football Playoff Semifinal at the Vrbo Fiesta Bowl"). */
export function weekLong(game) {
  if (game && typeof game.postseason === "string" && game.postseason.trim()) return game.postseason.trim();
  if (game && (game.playoffRound || game.seasonType === "postseason")) return game.playoffRound || "Bowl game";
  return `Week ${text(game?.week)}`;
}

/** The week column's value in a table: the number, or the short postseason label. */
export function weekCell(game) {
  return game && (game.postseason || game.playoffRound || game.seasonType === "postseason") ? weekShort(game) : game?.week;
}
