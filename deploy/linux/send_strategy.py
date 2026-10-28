#!/usr/bin/env python3
"""Send a promoted Lab strategy from this Mac's Desk to the server's Desk (the owner, 2026-10-28: "fully add it to the VPS
desk from the Mac desk, impossible to mess up").

    deploy/linux/send_strategy.py NAME [NAME ...]               dry run: says what would happen, writes nothing
    deploy/linux/send_strategy.py NAME [NAME ...] --go          send it
    ... --replace        also replace a DIFFERENT version the server has (only while it is OFF with no account)
    ... --even-if-behind send while the server still runs older code than main (vpssync has not caught up)

It sends the one record the Lab froze when you put the strategy on the Desk (code, settings, window, costs), and it
lands on the server switched OFF with no account. Nothing else moves: the server's days, journal, accounts, limits and
config are its own. Never a backtest on the server. Strategy CODE in homebase/ still travels by vpssync (committed main).

What it checks, in this order -- any "no" stops that strategy and nothing is written:
  this Mac: it is on the Desk, its code still matches its hash; a warning when this Mac's copy is ON or has accounts
            (both Desks trade the same broker accounts: do not book it on both);
  the server: answers; runs the same commit as main (else --even-if-behind); can take the record (the receiver is
            homebase/labrun/receive.py: no hash match, no known market, in its Archive, a different version, ON, or booked =
            refused); the store it writes is /home/homebase/.homebase/desklab;
  after --go: read back from the server's disk: same hash, OFF.
Host: $HOMEBASE_SERVER, else root@144.202.51.163 (as deploy/linux/vpssync.sh).
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from homebase.labrun import store  # noqa: E402  (stdlib + homebase.core only)

HOST = os.environ.get("HOMEBASE_SERVER", "root@144.202.51.163")
DEST = "/home/homebase/ramos-quant-homebase"
SERVER_STORE = "/home/homebase/.homebase/desklab"
REV = "/home/homebase/.homebase-sync/rev"
# runuser keeps HOME=/root: without HOME the receiver would write into root's folder
RECEIVE = f"cd {DEST} && runuser -u homebase -- env HOME=/home/homebase ./.venv/bin/python -m homebase.labrun.receive"


def ssh(cmd: str, stdin: str | None = None) -> tuple[int, str]:
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, cmd], input=stdin,
                       capture_output=True, text=True, timeout=90)
    return p.returncode, p.stdout.strip()


def main_rev() -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "refs/heads/main"], capture_output=True, text=True).stdout.strip()


def server_ready(run=ssh, behind_ok: bool = False) -> str | None:
    """None when the server can take a record; else the plain reason it cannot."""
    rc, out = run(f"cat {REV} 2>/dev/null; echo; {RECEIVE} --check 2>&1 | tail -1")
    lines = out.splitlines()
    if rc != 0 or len(lines) < 2:
        return "The server did not answer. Is it up, and is this Mac's ssh key accepted?"
    rev, check = lines[0].strip(), lines[-1]
    try:
        info = json.loads(check)
    except ValueError:
        return "The server does not have the receiving code yet (it arrives with the next vpssync of main). Wait a few minutes and run again."
    if info.get("store") != SERVER_STORE:
        return f"The receiver would write to {info.get('store')}, not the server's own store. Nothing was sent."
    if rev != main_rev() and not behind_ok:
        return (f"The server runs {rev[:8]}, main is {main_rev()[:8]}: vpssync has not caught up (it ships every 2 min, and waits while "
                "an account holds a position or a Lab strategy is booked in market hours). A record made by newer code may need "
                "newer code there. Wait, or run with --even-if-behind if you know the record needs nothing new.")
    return None


def send(name: str, go: bool = False, replace: bool = False, run=ssh, mac_at=None) -> tuple[bool, list[str]]:
    """(sent_or_fine, the lines to print). `run` is the ssh (a test passes its own)."""
    say: list[str] = []
    rec = store.get(name, mac_at) if store.NAME_RE.fullmatch(name) else None
    if rec is None:
        return False, [f"{name}: not on this Mac's Desk. Put it on the Desk in the Lab first (Promote), then send it."]
    if hashlib.sha256(str(rec.get("source")).encode("utf-8")).hexdigest() != rec.get("sha256"):
        return False, [f"{name}: its frozen code no longer matches its hash. Promote it again in the Lab."]
    if rec.get("enabled") is True or store.booked(name, mac_at):
        say.append(f"{name}: WARNING this Mac's copy is " + ("ON" if rec.get("enabled") is True else "OFF")
                   + (" with accounts booked" if store.booked(name, mac_at) else "")
                   + ". Both Desks trade the same broker accounts: do not book it on both.")
    flags = (["--go"] if go else []) + (["--replace"] if replace else [])
    rc, out = run(f"{RECEIVE} {shlex.quote(name)} {' '.join(flags)}", json.dumps(rec))
    try:
        got = json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return False, say + [f"{name}: the server's answer could not be read ({out[-200:] or 'nothing'}). Nothing is known to have changed: check with --show."]
    if got.get("verdict") == "refused":
        return False, say + [f"{name}: NOT SENT. {got.get('why')}"]
    if got.get("verdict") == "same":
        return True, say + [f"{name}: {got.get('why')}"]
    if not go:
        return True, say + [f"{name}: would be sent. {got.get('why')} (dry run: add --go to send)"]
    rc, out = run(f"{RECEIVE} {shlex.quote(name)} --show")
    try:
        seen = json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        seen = {}
    if not got.get("wrote") or seen.get("sha256") != rec.get("sha256") or seen.get("enabled") is not False:
        return False, say + [f"{name}: the write could not be confirmed on the server ({out[-200:]}). Check the server Desk."]
    return True, say + [f"{name}: SENT. On the server it is OFF, with no account. Next, on the server Desk: group and accounts, "
                        "limits, then switch it on."]


def main(argv: list[str]) -> int:
    go, replace, behind = ("--go" in argv, "--replace" in argv, "--even-if-behind" in argv)
    names = [a for a in argv if not a.startswith("--")]
    if not names or any(a.startswith("--") and a not in ("--go", "--replace", "--even-if-behind") for a in argv):
        print(__doc__)
        return 2
    why = server_ready(ssh, behind)
    if why:
        print(why)
        return 1
    ok = True
    for n in names:
        fine, lines = send(n, go, replace)
        ok &= fine
        print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
