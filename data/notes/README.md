# Per-game notes

One file per game of ours, named `<game_id>.json` (the id from the schedule; `/api/program/next` shows it).
The easy way: the Game program's notes band copies a prompt for an AI chat and saves the answer you paste
back (public release Phase 6). Claude Code on the server can write it from the same prompt, or write the
file by hand. `_example.json` shows every field; all of them are optional. An edited prompt is kept here as
`PROMPT.md` (Settings, Notes prompt).
The app validates the file (`app/services/notes.py`), drops a bad entry, and shows a readable error on the program page when the file itself is broken.

Sections: `schemes` (offense and defense labels for the matchup card), `sections` (program notes), `availability` (injury report), `visitors` (recruits at the game), `lineups` (both teams' published depth charts, `us` and `them`; the first name at each slot is the starter. The program shows the starters and the folded full chart, the Live sheet has a Lineups button).
