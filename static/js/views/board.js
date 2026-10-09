// The game-day board (Phase 18.6, owner 2026-10-08: "a monitor plugged into the PC", also a view a phone can cast).
// The Live sheet made for a wall: the shell's top bar and tabs and the touch controls are hidden, everything is drawn
// larger, the score, the plays and the ticker stay, and a QR code in the corner lets a friend join. It is the same
// live view underneath, so it can never disagree with the Live sheet.
//
//   createBoardView({ onStatus })   mounts the live view in board mode and puts it back when it unmounts

import { el } from "../ui/dom.js";
import { createLiveView } from "./live.js";
import { inviteBody, loadInvite } from "./invite.js";

const BOARD_CLASS = "board-mode";

/** The zoom for this screen: a tablet 1x, a laptop a little more, a 1080p or 4K television a lot. */
export function boardZoom(width) {
  if (!Number.isFinite(width) || width <= 0) return 1;
  if (width >= 3000) return 2.2;
  if (width >= 1800) return 1.6;
  if (width >= 1400) return 1.3;
  return 1;
}

export function createBoardView({ onStatus } = {}) {
  const live = createLiveView({ onStatus });
  let corner = null;
  let onResize = null;
  const apply = () => document.body.style.setProperty("--board-zoom", String(boardZoom(window.innerWidth)));
  return {
    async mount(target) {
      document.body.classList.add(BOARD_CLASS);
      apply();
      onResize = () => apply();
      window.addEventListener("resize", onResize);
      corner = el("aside", { class: "board__corner", "aria-label": "Join the game" }, el("p", { class: "board__join" }, "Scan to watch along"));
      document.body.append(corner);
      loadInvite().then((data) => { if (corner) corner.append(inviteBody({ ...data, warnings: [] })); }).catch(() => { if (corner) corner.remove(); });
      await live.mount(target);
    },
    refresh() {
      return live.refresh?.();
    },
    unmount() {
      document.body.classList.remove(BOARD_CLASS);
      document.body.style.removeProperty("--board-zoom");
      if (onResize) window.removeEventListener("resize", onResize);
      onResize = null;
      corner?.remove();
      corner = null;
      return live.unmount();
    },
  };
}
