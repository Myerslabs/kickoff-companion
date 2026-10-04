# Kickoff Companion

A second screen for college football. Pick your team, start it on a computer at home, and follow the game on any phone or tablet on your Wi-Fi: the live play-by-play a little behind your TV so nothing is spoiled, the box score, win probability, drives, the shot chart, your team's season, the next opponent's game program, and scores from around the country.

**Available for free from Myers Labs:** https://github.com/Myerslabs/kickoff-companion

## What it does

- **Live sheet:** the score, every play as it happens, team and player stats, win probability, drives, situational splits and a shot chart of your offense's passes and runs, all held back by a spoiler delay you can sync to your TV with one tap.
- **Game program:** the matchup, weather at the stadium, the TV crew and both coaching staffs, players to watch, the injury report, starting lineups and season stats side by side.
- **Season:** schedule, results, standings, polls, ratings (SP+, Elo, FPI) and the stat profile behind every rank, each rank one tap from its national list.
- **People:** roster, leaders, recruiting, a card for every player, and our own stat grades for each position.
- **Your teams:** one home team themes the app with its colors; with a Tier 2 key you can follow more primary teams and whole conferences or states, and set the score ticker to just your teams.
- **Notes:** schemes, the injury report, depth charts, the TV crew and coaches come from a prompt the app writes for any AI chat; paste the answer back and the app checks it and saves it.
- **Runs at home:** a small web server on Windows, macOS or Linux (the Steam Deck too). Phones and tablets connect by scanning a QR code. No accounts, no cloud, no ads.

## What you need

- A computer that stays on during games: Windows 10 or later, macOS, or Linux.
- Phones or tablets on the same Wi-Fi.
- For your own team: a free key from [College Football Data](https://collegefootballdata.com/key) (CFBD). Every number in the app comes from CFBD. You can try the whole app first without one: it starts in a demo.

**Your data stays with you.** Kickoff Companion is free, from Myers Labs. It runs on your computer and talks to CollegeFootballData.com directly: your key, your team and everything you look at stay there, and nothing is sent to Myers Labs. A CFBD key is free. CFBD's paid plans are paid to CFBD, not to us, and they only unlock more data:

| CFBD plan | Calls a month | What the app shows |
|---|---|---|
| Free | 1,000 | Every season page, box scores and play-by-play after each game. The app runs lean so the calls last the month. |
| Tier 1 ($1 a month) | 5,000 | Adds CFBD's game weather and live scores across the country. |
| Tier 2 ($5 a month, recommended) | 30,000 | Adds live play-by-play for your game, more primary teams, secondary teams and the My teams ticker. |

Anything a plan does not include stays on its page with a note saying which plan shows it. See [CFBD's plans](https://collegefootballdata.com/api-tiers).

## Start

1. Get the code: **Code, Download ZIP** on this page (then unzip it), or `git clone https://github.com/Myerslabs/kickoff-companion.git`.
2. Double-click the launcher for your system:

   | System | Double-click |
   |---|---|
   | Windows | `Kickoff Companion.cmd` |
   | macOS | `Kickoff Companion.command` |
   | Linux, Steam Deck | `Kickoff Companion.sh` |

   The first start installs [uv](https://docs.astral.sh/uv/), Python and the app's packages for your user (no admin rights, a minute or two, once). macOS may say it cannot open a downloaded file: right-click the launcher, Open, then Open again.
3. The browser opens the **demo**: a made-up league with a game already under way, so you can see everything working. Its welcome page explains what a CFBD key does.
4. When you are ready, choose **Use my own team** on that page (or the banner at the top): paste your CFBD key, pick your team, save. The app restarts with your team. The menu's **Demo** item switches back to the demo any time, for showing a friend.
5. On a phone or tablet, scan the QR code in the server window (or on the app's status page). The window that opened is the server: keep it open during the game, close it to stop.

Settings in the app can start the server when you log in, make a Desktop icon, and keep the screen awake. The full guide, including the firewall on each system and the Steam Deck, is [docs/05-SETUP.md](docs/05-SETUP.md).

## The demo on its own

A fresh install starts in the demo. To run it beside your own install (on its own port, no key, no network), with the made-up league of 136 schools like the Swampwater Tech Mudpuppies:

```
uv run python -m app --demo
```

Then open http://127.0.0.1:8650/. `uv run python tools/live_sim.py` starts it with a game already under way.

## For developers

FastAPI and plain JavaScript modules, no front-end build step. Every external answer is validated and cached, with retries, a circuit breaker and a monthly call budget, so the app survives a game day unattended and serves the last good data, labelled stale, when CFBD is down.

| Task | Command |
|---|---|
| Install | `uv sync` |
| Run with reload | `uv run python -m app --reload` |
| Tests (no network) | `uv run python -m pytest` |
| Lint | `uv run python -m ruff check app tools tests` |
| Every page for undefined, null or NaN (headless Edge or Chrome) | `uv run python tools/page_check.py` |

The tests and the demo use the made-up league, generated from the shape of CFBD's answers with every name and number invented; no CFBD data is in this repository.

## Credits

Data provided by [CollegeFootballData.com](https://collegefootballdata.com). Weather from the U.S. National Weather Service. Fonts: Barlow and Barlow Condensed (SIL Open Font License).

Not affiliated with any school, conference, the NCAA, any broadcaster, or CollegeFootballData.com. See [NOTICE](NOTICE).

## License

MIT, copyright Myers Labs. See [LICENSE](LICENSE).
