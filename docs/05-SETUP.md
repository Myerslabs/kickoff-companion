# Setup on Windows, macOS and Linux

Kickoff Companion runs on a computer in your home (the host) and shows on any phone, tablet or computer on the same Wi-Fi (the viewers). The host needs to be on during games. Windows 10 or later, macOS, and Linux all work, the Steam Deck included.

To try it first with no key and no setup, run the demo (section 9).

There are two ways to get it: **the download**, a packaged program with nothing to install, and **the code**, where uv installs Python and the packages. Section 1 covers both; sections 2 and 4 say where they differ.

## 1. Get the program

**The download.** On the [Releases page](https://github.com/Myerslabs/kickoff-companion/releases), take the archive for your system. A `.sha256` file beside each archive holds its checksum.

| System | Archive | Then |
|---|---|---|
| Windows | `KickoffCompanion-<version>-windows-x64.zip` | Unzip it anywhere and double-click `KickoffCompanion.exe`. The first time, Windows says it protected your PC, because the program is not signed: **More info**, then **Run anyway**. |
| macOS | `KickoffCompanion-<version>-macos-arm64.tar.gz` | Unpack it, then right-click `KickoffCompanion`, **Open**, and **Open** again (unsigned, so once). Not yet tried on a Mac; say how it went. |
| Linux, Steam Deck | `KickoffCompanion-<version>-linux-x64.tar.gz` | Unpack it, then run `./KickoffCompanion` in a terminal, or double-click it and choose Run. |

The program is the server: the window that opens stays open during the game, and closing it stops the server. The first start also brings a Windows Security dialog, "Do you want to allow public and private networks to access this app?", with the Kickoff Companion icon and Myers Labs as the publisher: **Allow**, so phones on your Wi-Fi can reach it. That is the whole firewall step for the download. The first start opens the **demo** (below). Your files, `.env` (the key and the team), `data/` (settings, the cache, notes, the archive) and `logs/`, live in your app-data folder, so a new version of the program replaces the old folder and loses nothing:

| System | Your files |
|---|---|
| Windows | `%LOCALAPPDATA%\Kickoff Companion` (`C:\Users\<you>\AppData\Local\Kickoff Companion`) |
| macOS | `~/Library/Application Support/Kickoff Companion` |
| Linux, Steam Deck | `$XDG_DATA_HOME/kickoff-companion`, else `~/.local/share/kickoff-companion` |

Settings, About, shows the folder with an **Open the folder** button (on the server computer itself). To keep everything beside the program instead, on a USB stick say, put an empty file named `portable` next to it before the first start. `DATA_DIR` and `LOG_DIR` in `.env` still move those two folders wherever they say.

**The code.** Clone the repository with git, or download it as a ZIP from the repository page and unzip it. Every command below runs in that folder.

**The short way: double-click.** In the folder, double-click the launcher for your system:

| System | Double-click |
|---|---|
| Windows | `Kickoff Companion.cmd` |
| macOS | `Kickoff Companion.command` (if macOS says it cannot open a downloaded file: right-click it, Open, then Open again) |
| Linux, Steam Deck | `Kickoff Companion.sh` (choose Execute or Run if the file manager asks) |

The first start installs uv, Python and the app's packages for your user (no admin rights, a minute or two, once), then opens the **demo** in the browser: a made-up league with a game under way. Its welcome page explains the CFBD key; **Use my own team** there leads to the setup page (section 3). Nothing you do is sent to Myers Labs, and CFBD's paid plans are paid to CFBD. Later starts just start the server and open the app. The window that opens is the server: closing it stops the server. Sections 2 and 4 are the same steps by hand.

## 2. Install uv (the code only)

The download needs nothing here. For the code, [uv](https://docs.astral.sh/uv/) installs the right Python and every package for you. It needs no admin rights and does not change the system's Python. The launchers and the start scripts install it on the first start when it is missing.

| System | Command |
|---|---|
| Windows (PowerShell) | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| macOS, Linux, Steam Deck | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Prefer plain pip? Make a virtual environment named `.venv` in the folder and install `requirements.txt` into it; the start scripts use it the same way.

## 3. Configure (in the browser)

Nothing to edit. A fresh install opens the demo first; **Use my own team** on its welcome page (`/demo`) opens the setup page (`/welcome`). The menu's **Demo** item switches back to the demo later (the choice is kept in `data/startup.json`). The setup page:

1. **Your CFBD key.** Get one free at [collegefootballdata.com/key](https://collegefootballdata.com/key): sign up with an email address and CFBD mails it. Paste it and the page checks it with CFBD and shows your plan: calls a month, used so far, the reset date and a forecast for the month.
2. **Your home team**, from CFBD's list of FBS schools: primary team #1. The Season page, the Game program and the Live sheet follow it, and only its colors and mascot theme the app. The conference comes along.
3. **More primary teams** (a Tier 2 key, up to four): teams you follow closely. Their team pages load as soon as a device connects and sit one tap away in the menu, under My teams.
4. **Secondary teams** (a Tier 2 key): more schools, whole conferences, or every school in a state. Nothing is loaded for them until a page asks. They fill the My teams page, the My teams view of every ranked list, and the ticker when it is set to My teams.
5. **The score ticker**: National (every FBS game, the default) or My teams (a Tier 2 key).

Save, and the server restarts itself with the new setup and opens the app. The page works from a phone too (`http://kickoff.local:8642/welcome`) while no key is set; once one is, it can only be replaced from the server computer itself.

**Plans.** The free plan (1,000 calls a month) runs the app lean: data refreshes less often, the ticker every 20 minutes, and nothing is fetched that a page did not ask for. A Tier 2 key adds live play-by-play, more primary teams, secondary teams and the My teams ticker. Whatever a plan does not include stays on its page with a note saying which plan shows it. Settings, "Your CFBD plan", lists every feature.

You can still set everything in `.env` by hand; `.env.example` lists every setting with a comment.

**Radio.** No station is built in. In Settings, Radio stations, add your team's official player page, stream or web page. For a team with no station the app offers a web search, a TuneIn search and a **Request your team's radio** button, which opens a short form in the project's GitHub issues; stations people ask for are added to the app's list for everyone.

**Game notes.** The Game program has a notes band: schemes, program notes, the injury report, recruits visiting and both depth charts. To fill it, tap **Copy the prompt**, paste it into any AI chat that can search the web, wait for its answer, copy the whole answer, paste it back, **Check it**, then **Save the notes**. It works from a phone or tablet. Settings, Notes prompt, lets you change what it asks for.

## 4. Start

| System | The download | The code |
|---|---|---|
| Windows | `KickoffCompanion.exe` | `Kickoff Companion.cmd`, or `.\start.ps1` (right-click it, Run with PowerShell) |
| macOS, Linux | `./KickoffCompanion` (or double-click it) | `Kickoff Companion.command` or `Kickoff Companion.sh`, or `./start.sh` |

From the code, the first start downloads Python and the packages, which takes a minute. Then the server checks `.env`, prints the address viewers use with a QR code for it, and opens the app in this computer's browser. Keep the window open; Ctrl+C stops it. The log is in `logs/app.log` (under your files, section 1). If the download stops with a message (another copy already running, say), the window waits for Enter so you can read it.

The browser opens when you start the server by hand. Settings, "Open the app on start", changes that (always, or never), and `--no-browser` skips it once.

## 5. Let viewers reach the host (firewall)

**The download on Windows asks for itself:** the first start shows a Windows Security dialog for Kickoff Companion, publisher Myers Labs; **Allow** is the whole step. The code gets the same dialog for Python the first time it listens; the rules below are for when that was dismissed, or when the server starts at login before anyone can answer. On macOS and Linux both ways need the steps below.

The server listens on `PORT` (default 8642) for the app, and on UDP 5353 to answer for its network name (section 6).

**Windows.** In an administrator PowerShell, once:

```powershell
New-NetFirewallRule -DisplayName "Kickoff Companion" -Direction Inbound -Protocol TCP -LocalPort 8642 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "Kickoff Companion (network name)" -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow -Profile Private
```

These rules cover networks marked Private. If Windows shows your home network as Public (Settings, Network and internet, your connection), switch it to Private, or add `Public` to `-Profile`.

**macOS.** The first start may ask whether Python may accept incoming connections. Click Allow. If you missed it: System Settings, Network, Firewall, Options.

**Linux.** Most desktops have no firewall switched on, the Steam Deck included. With ufw: `sudo ufw allow 8642/tcp` and `sudo ufw allow 5353/udp`. With firewalld: `sudo firewall-cmd --permanent --add-port=8642/tcp --add-service=mdns && sudo firewall-cmd --reload`.

## 6. The address viewers use

The server announces itself on the home network as **kickoff.local**, so viewers open `http://kickoff.local:8642`. iPhone, iPad, Mac, Linux and Windows 10 or later find it by name with no router setup.

- Some Android phones do not resolve `.local` names. Use the number address the server prints (for example `http://192.168.1.20:8642`); it always works.
- Two installs on one network need different names: set `MDNS_NAME` in `.env` (for example `MDNS_NAME=den` gives `den.local`). `MDNS_NAME=off` announces nothing.
- If your router can hold local DNS names, set `LAN_HOSTNAME` to one and the server shows that name first.

The status page (`/status`) shows whether the name is announced.

## 7. Connect each phone or tablet

Nothing to install. Scan the QR code in the server window, or the one on the status page (`/status`), with the device's camera, and tap the link. Or type the address. Then add it to the home screen: Safari's Share button, Add to Home Screen; Chrome's menu, Add to Home screen. `http://kickoff.local:8642/setup` has the same steps and the code.

The app keeps the screen awake during games once you tap anywhere on it.

### HTTPS, if you want it

The app serves plain HTTP on your home network, the way most programs on a home network do, so no device has to install or accept a certificate. If you want HTTPS anyway:

- **Tailscale** (free for personal use, [tailscale.com](https://tailscale.com)): install it on the host and on each device, and turn on HTTPS certificates in the Tailscale admin console (DNS page). `tailscale serve --bg 8642` on the host gives an HTTPS address like `https://your-pc.your-tailnet.ts.net` with a real certificate, trusted everywhere with no prompts, and it works away from home too.
- **The app's own certificate:** `HTTPS=on` in `.env`. The server makes a certificate authority for your home, and each device trusts it once from `http://kickoff.local:8642/setup`, which then shows the steps for iPhone and iPad, Android, Windows, Mac, Linux and Firefox.

## 8. Start at login and a desktop icon

In the app, open Settings:

- **Start at login** starts the server when you log in. On Windows that is a shortcut in the Startup folder, on Linux a systemd user service (`~/.config/systemd/user/kickoff-companion.service`), on macOS a LaunchAgent (`~/Library/LaunchAgents/com.kickoff-companion.server.plist`). It takes effect at the next login.
- **Desktop icon** makes a double-click launcher. On Linux it also goes in the app menu.
- **Tray mode** (Windows only, the code only) hides the server window behind a tray icon. The download has no tray yet; its window stays, or minimize it.

With the download, the login item and the icon start the program itself; with the code, the start script.

## 9. Demo mode

`uv run python -m app --demo` runs the whole app against a made-up league with no key and no network, then serves it at `http://127.0.0.1:8650/`. Add `--host 0.0.0.0` to look at it from a tablet. `--demo --help` lists the options.

## 10. The Steam Deck

1. Switch to Desktop Mode (Steam button, Power, Switch to Desktop) and open Konsole.
2. `git clone` the repository into your home folder, then install uv with the curl command in section 2. It installs into `~/.local/bin`, so the read-only system is not touched.
3. Configure (section 3) and run `./start.sh`.
4. To browse on the Deck itself, open the setup page in Firefox and follow the Linux steps.
5. Start at login (section 8) installs a user service, which also runs in Game Mode once the Deck is logged in. The Deck still sleeps when idle: for game day keep it plugged in and set sleep to Never in Settings, Power.

## 11. Updating

**The download:** take the new archive from the Releases page, delete the old program folder, unpack the new one, start it. Your files are in the app-data folder (section 1) and stay. With a `portable` file beside the program, move `portable`, `.env`, `data` and `logs` into the new folder first.

**The code:** `git pull` (or download the new ZIP), then start as usual. The start script brings the environment up to date from `uv.lock`.

## 12. If something is wrong

| Symptom | Look at |
|---|---|
| `kickoff.local` does not open | Use the number address the server prints. Then check the UDP 5353 firewall rule (section 5) and the "network name" line on the status page. |
| A viewer cannot reach the host at all | The TCP firewall rule (section 5), the same Wi-Fi, the host awake. |
| Certificate warning | Open the `http://` address, not `https://`. With `HTTPS=on`, trust the certificate on that device (section 7). |
| The server will not start | The window says why; `logs/app.log` has the details. `uv run python -m app --check` (the code) or `KickoffCompanion --check` (the download) checks `.env` without starting. |
| Windows says it protected your PC | The download is not signed. **More info**, then **Run anyway**; Windows asks once per download. |
| Where are my files? | Settings, About, shows the folder and opens it; `--check` prints it too. Section 1 lists the app-data folder for each system. |
