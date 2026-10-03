#!/usr/bin/env bash
# Kickoff Companion for Linux and the Steam Deck: double-click to start (choose Execute or Run if asked).
# A double-click starts without a window, so this opens a terminal for the server: closing it stops the server.
# The first start installs uv, Python and the app's packages for this user, then opens the setup page.
cd "$(dirname "$0")" || exit 1
if [ -t 1 ] || [ "${KICKOFF_IN_TERMINAL:-}" = "1" ]; then
  exec ./start.sh "$@"
fi
export KICKOFF_IN_TERMINAL=1
here="$(pwd)/start.sh"
for term in konsole gnome-terminal xfce4-terminal x-terminal-emulator mate-terminal lxterminal kitty alacritty xterm; do
  if command -v "$term" >/dev/null 2>&1; then
    case "$term" in
      gnome-terminal) exec "$term" -- "$here" "$@" ;;
      *) exec "$term" -e "$here" "$@" ;;
    esac
  fi
done
exec ./start.sh "$@"  # no terminal program found: run here
