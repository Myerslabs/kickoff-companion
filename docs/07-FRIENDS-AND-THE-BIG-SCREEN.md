# Friends and the big screen (Phase 18.6)

What this adds, how to use it, and how to set up the venue sign-in page.

## Host and guests

- With no host PIN set, every device on the network can change settings (how the app has always worked).
- Set a PIN (Settings > Friends and the big screen, from the server computer; 4 to 8 digits). From then on:
  - the server computer is always the host;
  - your own tablet becomes the host once: open the app, tap "I'm the host" at the top, enter the PIN (a cookie keeps it for a year);
  - every other device is a guest: it sees every page and the live game and can change nothing (the server answers 403 "view-only").
- Five wrong PINs from one address lock that address out for a minute.
- Changing the PIN signs every device out. Removing it (host only) makes every device the host again.
- The PIN is kept as a salted hash in `data/host.json`.

## Invite friends

Menu > More > Invite friends (`#invite`): a full-screen QR code by IP number, the address, a warning when the computer looks to be on a public network or sharing a hotspot, and a guide for watching away from home. The Live sheet has a small "Invite" button that shows the same code.

A new guest sees one welcome sheet: they can look at anything, only the host changes settings. The "Get your own copy" button appears only after the project is public (`REPO_IS_PUBLIC` in `app/__init__.py`).

## The game-day board (a monitor on the server computer)

`#board` is the Live sheet made for a wall: top bar, tabs and touch controls hidden, everything drawn larger (the zoom follows the screen's width), a QR code in the corner. It is the same live view, so it never disagrees with the Live sheet.

- Settings > Friends and the big screen > Big screen: pick a monitor, "Open the board there". The server starts Edge (or Chrome) in kiosk mode, full screen, on that monitor, with its own profile folder (`data/kiosk-profile`). Alt+F4 on it, or "Close the board", leaves.
- This works from the server computer only; a window cannot be opened on the computer from another device.
- The board runs in real time. Use the Live sheet's Spoiler delay to match the television.
- Casting: open `http://<address>/#board` in any browser and cast that tab or window to a television.

## Watching away from home

- Friend's house: run the server on a laptop on their Wi-Fi; everyone scans the code.
- Bar or guest Wi-Fi: many venues isolate devices from each other, so phones cannot reach the laptop. Either turn on the laptop's own hotspot (Windows: Settings > Network > Mobile hotspot) and have friends join it, or bring a travel router.

## A sign-in page for a venue (captive portal)

A captive portal is the "sign in to this Wi-Fi" screen a phone shows when it joins. It can only be set up on a network you control: a travel router, or a managed home router with a guest portal. The app serves a one-button page for it at `http://<address>:<port>/portal`.

Travel router (GL.iNet, or any OpenWrt router with a splash page such as openNDS):

1. Join the venue's Wi-Fi with the router (repeater mode) and make a Wi-Fi named "Game Day" for your friends.
2. In the router's captive portal or splash page settings, set the splash page to redirect to the server's `/portal` address (use the laptop's IP number on the router's network, shown on the Invite friends page).
3. Add the laptop's address to the router's allowed list (walled garden) so the page loads before sign-in.

A managed home router with guest-portal support: in its guest or hotspot portal settings, choose an external or redirect portal and enter the `/portal` address.

The page has one button, "Open the game". On a phone the sign-in window is a small browser; the button works there, and the page asks guests to choose "Open in browser" so the game keeps running.
