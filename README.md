# Kickoff Companion

A second screen for college football. Pick your team, start it on a Windows computer at home, and follow the game on any phone or tablet on your Wi-Fi: the live play-by-play a little behind your TV so nothing is spoiled, the box score, win probability, drives, the shot chart, your team's season, the next opponent's game program, a newspaper, and scores from around the country.

**Available for free from Myers Labs:** https://github.com/Myerslabs/kickoff-companion

## What it does

- **The season as one line:** a row of stops across the top steps through your season, from the preseason to the Pre-Game of the next game, In Game, the Post-Game and, at the end, the season in review. The page that matters now leads.
- **In Game:** the score, every play as it happens, team and player stats, win probability, drives, situational splits and a shot chart of your offense's passes and runs, all held back by a spoiler delay you can sync to your TV with one tap. Pick a game puts any game of the week on the same sheet.
- **Pre-Game and Post-Game Program:** the matchup, the poll path and the schedule margins of both teams, the whole series, strengths and weaknesses, the lineups drawn on a field, the weather at the stadium, the TV crew and both coaching staffs, players to watch, the injury report and what the conference race needs this week. After the final, the Post-Game keeps the program as it stood at kickoff beside what happened.
- **The Newspaper:** a front page with your team's headlines, the stories copied in to read on the page, and a Sunday paper after each game. In the off-season a new paper comes out every Monday.
- **My Team and every other team:** schedule, results, standings, polls, ratings (SP+, Elo, FPI) and the stat profile behind every rank, each rank one tap from its national list; roster, leaders, recruiting, a card for every player, and our own stat grades for each position. Any FBS team's page opens the same way, and every conference has its own page.
- **Talent Edge and the Imperialism Map:** how each roster's recruiting talent compares with its results, and a map of the country redrawn by every game's winner.
- **Seasons:** at the end of a season the app keeps its book (the season in review and every game) and moves to the next season by itself.
- **Notes:** schemes, the injury report, depth charts, the TV crew and coaches come from a prompt the app writes for any AI chat; paste the answer back and the app checks it and saves it.
- **Claude Code, if you want it:** with [Claude Code](https://claude.com/claude-code) installed on the computer, Settings can let it run the notes on a schedule, edit the newspaper and write a few pieces of its own. It is off until you turn it on, and each run uses your own Claude plan.
- **Runs at home:** a small web server on Windows, as one download with nothing to install. Phones and tablets connect by scanning a QR code. No accounts, no cloud, no ads.

**New in 2.0:** the season as one line, the Newspaper, the Post-Game Program, Talent Edge, the Imperialism Map, the conference pages, Pick a game, the lineups on a field, the seasons kept and the move to the next one, layouts for phones, and every page loading in about a second and a half. 2.0 runs on Windows only; on macOS and Linux, [1.0.1](https://github.com/Myerslabs/kickoff-companion/releases/tag/v1.0.1) (and `uvx kickoff-companion`) keeps working.

## What you need

- A Windows 10 or 11 computer that stays on during games.
- Phones or tablets on the same Wi-Fi.
- For your own team: a free key from [College Football Data](https://collegefootballdata.com/key) (CFBD). Every number in the app comes from CFBD. You can try the app first without one: it starts in a demo.

**Your data stays with you.** Kickoff Companion is free, from Myers Labs. It runs on your computer and talks to CollegeFootballData.com directly: your key, your team and everything you look at stay there, and nothing is sent to Myers Labs. A CFBD key is free. CFBD's paid plans are paid to CFBD, not to us, and they only unlock more data:

| CFBD plan | Calls a month | What the app shows |
|---|---|---|
| Free | 1,000 | Every season page, box scores and play-by-play after each game. The app runs lean so the calls last the month. |
| Tier 1 ($1 a month) | 5,000 | Adds CFBD's game weather and live scores across the country. |
| Tier 2 ($5 a month, recommended) | 30,000 | Adds live play-by-play for your game, more primary teams, secondary teams and the My teams ticker. |

Anything a plan does not include stays on its page with a note saying which plan shows it. See [CFBD's plans](https://collegefootballdata.com/api-tiers).

## Start

**The download: nothing to install.** On the [Releases page](https://github.com/Myerslabs/kickoff-companion/releases), take `KickoffCompanion-<version>-windows-x64.zip` (the `.sha256` file beside it holds its checksum). Unzip it anywhere and double-click `KickoffCompanion.exe`. Until the program is signed, Windows says it protected your PC the first time: **More info**, then **Run anyway**.

The program then runs behind a sun icon by the clock: double-click it to open the app, and Quit in its menu stops the server. The first start also brings a Windows Security dialog asking to allow public and private networks to reach the app: **Allow**, so phones on your Wi-Fi can reach it. Your key, settings, notes and archive live in your app-data folder (Settings, About, **Open the folder**), so a new version simply replaces the old program folder. A file named `portable` beside the program keeps them beside it instead.

**From the code** (for developers):

1. `git clone https://github.com/Myerslabs/kickoff-companion.git`, or **Code, Download ZIP** on this page.
2. Double-click `Kickoff Companion.cmd`. The first start installs [uv](https://docs.astral.sh/uv/), Python and the app's packages for your user (no admin rights, a minute or two, once). A clone can update itself later from Settings, About.

**Then, either way:**

1. The browser opens the **demo**: a sample season that follows one team, with invented games, players and scores and a game already under way, so you can see everything working. Its page explains what a CFBD key does.
2. When you are ready, choose **Use my own team**: paste your CFBD key, pick your team, save. The app restarts with your team. **Demo** on the menu's **Setup** page switches back to the demo any time, for showing a friend.
3. On a phone or tablet, scan the QR code in the server window (or on the app's status page).

Settings in the app can start the server when you log in, make a Desktop icon, and keep the computer awake for games. The full guide is [docs/05-SETUP.md](docs/05-SETUP.md); friends and a big screen are in [docs/07-FRIENDS-AND-THE-BIG-SCREEN.md](docs/07-FRIENDS-AND-THE-BIG-SCREEN.md).

## For developers

FastAPI and plain JavaScript modules, no front-end build step. Every external answer is validated and cached, with retries, a circuit breaker and a monthly call budget, so the app survives a game day unattended and serves the last good data, labelled stale, when CFBD is down.

| Task | Command |
|---|---|
| Install | `uv sync` |
| Run with reload | `uv run python -m app --reload` |
| The demo beside your own install (its own port, no key, no network) | `uv run python -m app --demo`, then http://127.0.0.1:8650/ |
| A live game in the demo | `uv run python tools/live_sim.py` |
| Tests (no network) | `uv run python -m pytest` |
| Lint | `uv run python -m ruff check app tools tests` |
| Every page for undefined, null or NaN (headless Edge or Chrome) | `uv run python tools/page_check.py` |
| A month of calls on a key, rehearsed | `uv run python tools/quota_rehearsal.py --tier 0` |
| Build the Windows program | `uv sync --group build`, then `uv run python tools/package/build.py` |

The tests and the demo use a test league: the FBS schools' names and colors with every game, player, coach and number invented. No CFBD data is in this repository.

## Code signing policy

Free code signing on Windows is provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org). The release workflow builds the program on GitHub's machines from this repository and submits that build for signing; nothing built anywhere else is signed. Until the first signed release ships, Windows still shows its "protected your PC" note on the first start.

- Committers and reviewers: the maintainer, [Myerslabs](https://github.com/Myerslabs).
- Approvers: the maintainer.
- Privacy: this program does not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. From your own computer it fetches only what its documentation names: the data your own CFBD key allows, team logos from CFBD, the public news feeds and the stories they link to, the weather, Wikipedia's pages for the teams, coaches and stadiums, and, in a copy cloned with git, GitHub's new commits when you check for updates. Claude Code runs only if you turn it on, with your own account. Nothing about you leaves the computer.

## Credits

Data provided by [CollegeFootballData.com](https://collegefootballdata.com). Weather from the U.S. National Weather Service. Fonts: Barlow and Barlow Condensed (SIL Open Font License).

Not affiliated with any school, conference, the NCAA, any broadcaster, or CollegeFootballData.com. See [NOTICE](NOTICE).

## License

MIT, copyright Myers Labs. See [LICENSE](LICENSE).
