// Where Claude Code is not installed on the server computer (Kickoff Companion 2.0, owner 2026-11-16: "Have something that
// says get claude cli, and then instructions or take them to anthropic's website"): what it adds, how to get it, and that
// copy and paste works without it.
//
//   getClaudeCode({ compact }) -> element   the steps and the link; compact: one line with the link, for a band's foot

import { el } from "./dom.js";

export const CLAUDE_CODE_URL = "https://claude.com/claude-code";

const link = (label) => el("a", { href: CLAUDE_CODE_URL, target: "_blank", rel: "noopener" }, label);

export function getClaudeCode({ compact = false } = {}) {
  if (compact) {
    return el("p", { class: "note claude-get claude-get--compact" }, "Claude Code can write this for you: ", link("get Claude Code from Anthropic"), ", then turn it on in Profile, Claude and loading data.");
  }
  return el(
    "div",
    { class: "claude-get" },
    el("p", { class: "claude-get__lead" }, "Get Claude Code to let the app load the notes and write for the paper by itself. It's optional: every prompt also works by copy and paste on the Load data page."),
    el(
      "ol",
      { class: "claude-get__steps" },
      el("li", {}, link("Get Claude Code from Anthropic"), " and install it on the computer that runs Kickoff Companion."),
      el("li", {}, "Open PowerShell, type ", el("code", {}, "claude"), " and sign in once with your Claude account."),
      el("li", {}, "Restart Kickoff Companion (Profile, Server Settings, Restart the server), then turn on Run the prompts by themselves here."),
    ),
    el("p", { class: "note" }, "Each run uses your own Claude plan. If Claude Code is installed somewhere the app doesn't look, set CLAUDE_COMMAND in the .env file to its full path."),
  );
}
