"""GET /api/deploy-status: which commit the server runs, and why a ship waits (the Settings card "Server updates").

Read-only. The Mac's launchd job (deploy/linux/vpssync.sh) writes homebase/.state/vpssync.log, one line a try; this reads
that log, the gate-wait counter beside it and `git` for main. It never ships, restarts, asks the server (no ssh) or writes
a file. On a machine that is not a Mac checkout (the server's Desk has no .git) it answers {available: false}."""
from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

LABEL = "com.ramosquant.homebase-vpssync"
LOG_BYTES = 65536                   # the tail of the log that is read: ~150 lines
SHOW = 15                           # lines of it the card shows
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (?:([0-9a-f]{8}): )?(.*)$")
# The gate's and the plan's own sentences (deploy/linux/vpssync_gate.py, vpssync_plan.py, vpssync.sh) in plain words.
WORDS = [
    (r"09:10-09:35 ET", "it is 09:10-09:35 ET, the Desk is busy at the open"),
    (r"(.+) is booked on an account", r"a Lab strategy (\1) is booked on an account: a restart would end its day"),
    (r"(.+) has a position or working orders", r"an account is not flat: \1 has a position or working orders"),
    (r"(.+) is not connected", r"account \1 is not connected, so its position is unknown"),
    (r"(.+) is not seeded yet", r"account \1 is not ready yet, so its position is unknown"),
    (r"the desk's status is unreadable", "the server's Desk status could not be read"),
    (r"the desk is not answering", "the server's Desk is not answering"),
    (r"requirements\.txt changed", "new Python packages must be installed on the server by hand first"),
    (r"it does not import: (.+)", r"the commit does not import (\1)"),
]


def _git(repo: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _last_shipped(log: Path):
    """The newest "-- shipped" row of the whole log, for a wait that has pushed it out of the tail."""
    row = None
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.match(line.rstrip("\n"))
                if m and m.group(2) and "-- shipped" in m.group(3):
                    row = m.groups()
    except OSError:
        pass
    return row


def plain(why: str) -> str:
    why = re.sub(r"^(?:waits: )*no: ", "", why.strip())
    for pat, to in WORDS:
        m = re.search(pat, why)
        if m:
            return m.expand(to)
    return why


def read(repo: Path, state: Path, plist: Path, git=_git) -> dict:
    """The panel's whole answer. Never raises: a missing or odd file is a state, not an error."""
    if not (repo / ".git").exists():
        return {"available": False, "reason": "Not on this machine: only the Mac's checkout updates the server"}
    log = state / "vpssync.log"
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - LOG_BYTES))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        text = None
    lines = (text or "").splitlines()
    rows = [m.groups() for m in map(LINE.match, lines) if m]
    out = {"available": True, "state": "unknown", "reason": "", "main": None, "server": None, "ahead": None,
           "last_attempt": rows[-1][0] if rows else None, "waiting_min": None, "log": [x[:300] for x in lines[-SHOW:]]}
    if text is None and not plist.exists():
        return {**out, "state": "not_set_up", "reason": "the update timer is not installed on this Mac"}
    head = git(repo, "log", "-1", "--format=%H%x09%s", "refs/heads/main")
    if not head:
        return {**out, "reason": "main could not be read"}
    main, _, subject = head.partition("\t")
    out["main"] = {"hash": main[:8], "subject": subject[:120]}
    shipped = next((r for r in reversed(rows) if "-- shipped" in r[2] and r[1]), None) or _last_shipped(log)
    if shipped:
        out["server"] = {"hash": shipped[1], "time": shipped[0]}
        n = git(repo, "rev-list", "--count", f"{shipped[1]}..{main}")
        out["ahead"] = int(n) if n and n.isdigit() else None
    if shipped and main.startswith(shipped[1]):
        return {**out, "state": "shipped", "ahead": 0}
    mine = next((r for r in reversed(rows) if r[1] == main[:8]), None)
    if mine is None:                        # no line for this commit: the timer has not tried it yet (or a try could not start)
        last = rows[-1][2] if rows and not rows[-1][1] else ""     # "server not reachable", "no main branch"
        return {**out, "state": "waiting", "reason": last or "not tried yet: the timer looks every 2 minutes"}
    what = mine[2]
    why = re.split(r"-- (?:waits: |FAILED: |NOT SHIPPED -- |waits -- )|^waits -- ", what, maxsplit=1)[-1]
    if "FAILED" in what or "NOT SHIPPED" in what:
        return {**out, "state": "failed", "reason": plain(why)}
    try:                                    # the gate's "no" counter: 2 minutes a pass
        w = (state / "vpssync.gatewait").read_text().splitlines()
        if len(w) > 1 and what.endswith(w[0]):
            out["waiting_min"] = int(w[1]) * 2
    except (OSError, ValueError):
        pass
    return {**out, "state": "waiting", "reason": plain(why)}


def register(app, *, STATIC) -> None:

    @app.get("/api/deploy-status")
    async def deploy_status():
        repo = STATIC.parent.parent
        plist = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        return await asyncio.to_thread(read, repo, repo / "homebase" / ".state", plist)
