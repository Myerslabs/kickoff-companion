"""Play text in the grammar of the play-by-play feed: "(14:54) Shotgun #23 J.Cobb rush middle for 7
yards gain to the AUB32 (#1 B.Thornton)". The app reads the play type for almost everything; the
text supplies the clock for recaps, "1ST DOWN", "NO PLAY", " sacked " and " rush " for the live box
score, and "15 yard" for the penalty badge, so those markers are written exactly that way."""

from __future__ import annotations

from collections.abc import Callable

from app.demo.sim import Play

Who = Callable[[int], tuple[int, str]]  # player -> (jersey, "F.Last")

ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def clock_text(seconds: int | None) -> str:
    if seconds is None:
        return ""
    return f"({seconds // 60:02d}:{seconds % 60:02d}) "


def spot(ytg: int, off_abbr: str, def_abbr: str) -> str:
    """A field position from the offense's view: IOWA32 is the 32 on Iowa's side."""
    ytg = max(0, min(100, ytg))
    if ytg > 50:
        return f"{off_abbr}{100 - ytg:02d}"
    return f"{def_abbr}{ytg:02d}"


def _yards(n: int) -> str:
    return "1 yard" if abs(n) == 1 else f"{abs(n)} yards"


def play_text(p: Play, who: Who, abbr: tuple[str, str], school: tuple[str, str]) -> str:
    """`abbr` and `school` are (home, away)."""
    off = abbr[p.side]
    dfn = abbr[1 - p.side]
    d = p.d
    head = clock_text(p.clock)

    def name(pid: int | None) -> str:
        if pid is None:
            return "TEAM"
        jersey, short = who(pid)
        return f"#{jersey} {short}"

    def tackles(ids: list[int] | None) -> str:
        return f" ({', '.join(name(t) for t in ids)})" if ids else ""

    def xp() -> str:
        if "xp" not in d:
            return ""
        clock = f", clock {p.clock // 60:02d}:{p.clock % 60:02d}" if p.clock is not None else ""
        made = "good" if d["xp"] else "MISSED"
        return f" TOUCHDOWN{clock} {name(d.get('kicker'))} kick attempt {made} (H: {name(d.get('holder'))}, LS: {name(d.get('snapper'))})"

    t = p.ptype
    if t in ("End Period", "End of Half"):
        return f"End of {ORDINAL.get(d.get('ended', p.period), str(p.period))} quarter."
    if t == "End of Game":
        return "End of 4th quarter." if p.period <= 4 else "End of game."
    if t == "Timeout":
        taker = school[d.get("team", p.side)]
        clock = f", clock {p.clock // 60:02d}:{p.clock % 60:02d}" if p.clock is not None else ""
        return f"Timeout {taker}{clock}"
    if t in ("Kickoff", "Kickoff Return Touchdown"):
        kick = d.get("kick", 65)
        land = max(0, 65 - kick)
        recv_abbr = dfn
        base = f"{head}{name(d.get('kicker'))} kickoff {kick} yards to the {recv_abbr}{land:02d}"
        if d.get("touchback"):
            return base + ", Touchback"
        if d.get("fair_catch"):
            return base + f", fair catch by {name(d.get('returner'))}"
        ret = d.get("ret", 0)
        end = land + ret
        if t == "Kickoff Return Touchdown":
            return base + f" {name(d.get('returner'))} return {_yards(100 - land)} to the {off}00 TOUCHDOWN" + xp()
        to = f"{recv_abbr}{end:02d}" if end <= 50 else f"{off}{100 - end:02d}"
        return base + f" {name(d.get('returner'))} return {_yards(ret)} to the {to}{tackles(d.get('tacklers'))}"
    if t == "Punt":
        kick = d.get("kick", 40)
        land = p.ytg - kick
        if d.get("touchback"):
            return f"{head}{name(d.get('punter'))} punt {kick} yards to the {dfn}00, Touchback"
        at = spot(land, off, dfn) if land >= 0 else f"{dfn}00"
        base = f"{head}{name(d.get('punter'))} punt {kick} yards to the {at}"
        if d.get("fair_catch"):
            return base + f" fair catch by {name(d.get('returner'))} at {at}"
        if d.get("downed"):
            return base + f", downed by {off}"
        ret = d.get("ret", 0)
        end = spot(land + ret, off, dfn)
        return base + f" {name(d.get('returner'))} return {_yards(ret)} to the {end}{tackles(d.get('tacklers'))}"
    if t in ("Field Goal Good", "Field Goal Missed"):
        verdict = "GOOD" if t == "Field Goal Good" else f"MISSED {d.get('miss', 'wide right')}"
        clock = f", clock {p.clock // 60:02d}:{p.clock % 60:02d}" if p.clock is not None else ""
        return f"{head}{name(d.get('kicker'))} field goal attempt from {d.get('kick', p.ytg + 17)} yards {verdict} (H: {name(d.get('holder'))}, LS: {name(d.get('snapper'))}){clock}"
    if t == "Penalty":
        flagged = abbr[d.get("flag", p.side)]
        frm = spot(d.get("from", p.ytg), off, dfn)
        to = spot(d.get("to", p.ytg), off, dfn)
        first = ", 1ST DOWN" if d.get("first") else ""
        return f"{head}PENALTY {flagged} {d.get('name', 'Penalty')} {_yards(d.get('yards', 5))} from {frm} to {to}{first}. NO PLAY"
    if t == "Safety":
        if d.get("sack"):
            return f"{head}{d.get('form', '')}{name(d.get('passer'))} sacked in the end zone for a SAFETY{tackles(d.get('sackers'))}"
        return f"{head}{d.get('form', '')}{name(d.get('rusher'))} rush {d.get('dir', 'middle')} tackled in the end zone for a SAFETY{tackles(d.get('tacklers'))}"
    if t == "Two Point Pass":
        made = "GOOD" if d.get("two") else "FAILED"
        return f"{name(d.get('passer'))} pass to {name(d.get('target'))} TWO-POINT CONVERSION ATTEMPT {made}"
    form = d.get("form", "")
    first = ", 1ST DOWN" if d.get("first") else ""
    end_spot = spot(p.ytg - p.gained, off, dfn)
    if d.get("sack"):
        text = f"{head}{form}{name(d.get('passer'))} sacked for loss of {_yards(-p.gained)} to the {end_spot}{tackles(d.get('sackers'))}"
        return text + _fumble(d, name, abbr, p, off, dfn)
    if "rusher" in d:
        if d.get("kneel"):
            return f"{head}{name(d['rusher'])} rush {d.get('dir', 'middle')} for {_yards(p.gained)} loss to the {end_spot} (kneel)"
        if p.gained > 0:
            gain = f"for {_yards(p.gained)} gain"
        elif p.gained == 0:
            gain = "for no gain"
        else:
            gain = f"for {_yards(p.gained)} loss"
        text = f"{head}{form}{name(d['rusher'])} rush {d.get('dir', 'middle')} {gain} to the {end_spot}"
        if t == "Rushing Touchdown":
            return text + xp()
        return text + _fumble(d, name, abbr, p, off, dfn) + tackles(d.get("tacklers")) + first
    if "passer" in d:
        passer = name(d["passer"])
        where = f"{d.get('depth', 'short')} {d.get('dir', 'middle')}"
        target = name(d.get("target"))
        caught_at = spot(p.ytg - d.get("air", 0), off, dfn)
        if "interceptor" in d:
            picker = name(d["interceptor"])
            at = spot(d.get("at", p.ytg), off, dfn)
            text = f"{head}{form}{passer} pass intercepted by {picker} at {at}"
            ret = d.get("ret", 0)
            if t == "Interception Return Touchdown":
                return text + f" {picker} return {_yards(ret)} to the {off}00 TOUCHDOWN" + xp()
            if ret <= 0:
                return text + ", End Of Play"
            back = 100 - d.get("at", p.ytg)
            to = spot(back - ret, dfn, off)
            return text + f" {picker} return {_yards(ret)} to the {to}{tackles(d.get('tacklers'))}"
        if d.get("complete"):
            text = f"{head}{form}{passer} pass complete {where} to {target} caught at {caught_at}, for {_yards(p.gained)} to the {end_spot}"
            if t == "Passing Touchdown":
                return text + xp()
            return text + _fumble(d, name, abbr, p, off, dfn) + tackles(d.get("tacklers")) + first
        text = f"{head}{form}{passer} pass incomplete {where} to {target} thrown to {caught_at}"
        if d.get("broken_up"):
            text += f", broken up by {name(d['broken_up'])}"
        return text
    return f"{head}{t}"


def _fumble(d: dict, name, abbr: tuple[str, str], p: Play, off: str, dfn: str) -> str:
    if "fumble" not in d:
        return ""
    side = d.get("recovered", p.side)
    team = abbr[side]
    at = spot(p.ytg - p.gained, off, dfn)
    return f" {name(d['fumble'])} FUMBLES, recovered by {team} {name(d.get('recoverer'))} at the {at}"
