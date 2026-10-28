"""The ship gate (deploy/linux/vpssync.sh and vpssync_remote.sh run it ON THE SERVER, stdlib only):
    python3 vpssync_gate.py <1 when the Lab runner restarts, else 0>   -> one line, "ok" or "no: <why>"
Fails CLOSED: a Desk that does not answer, an account that is disconnected or whose caches are not seeded yet (so its
position count cannot be trusted) all wait. A disconnected account only waits while it is in the book or has a round
today: a parked, expired or removed account that nothing uses can never hold a position the Desk could lose. The runner's booked-strategy check holds whenever the market is open
(a desk day can run 18:00-04:00 too), not only weekdays 08:00-16:15."""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


def market_closed(now) -> bool:
    m = now.hour * 60 + now.minute
    wd = now.weekday()
    return (wd == 5 or (wd == 6 and m < 18 * 60) or (wd == 4 and m >= 17 * 60)
            or 17 * 60 <= m < 18 * 60)              # Fri 17:00 -> Sun 18:00 and the daily 17:00-18:00 break


FORCE_RUNNER = "/home/homebase/.homebase-sync/force_runner"       # the owner's word: restart the runner now (valid 30 min)


def forced() -> bool:
    try:
        return time.time() - os.path.getmtime(FORCE_RUNNER) < 1800
    except OSError:
        return False


def verdict(d, now, needs_runner: bool, force_runner: bool = False) -> str:
    m = now.hour * 60 + now.minute
    if 9 * 60 + 10 <= m <= 9 * 60 + 35:
        return "no: 09:10-09:35 ET"
    if not isinstance(d, dict) or not isinstance(d.get("accounts"), dict):
        return "no: the desk's status is unreadable"
    used = {r.get("account") for rows in (d.get("book") or {}).values() if isinstance(rows, list)
            for r in rows if isinstance(r, dict)}
    for s in (d.get("strategies") or {}).values():
        used |= {r.get("account") for r in (s.get("accounts") or []) if isinstance(r, dict)}
    for k, a in d["accounts"].items():
        name = a.get("label") or k
        if not a.get("connected"):
            if k not in used and not (a.get("day") or {}).get("closes"):
                continue                            # idle and gone: it holds nothing the Desk could lose
            return "no: %s is not connected (its position is unknown)" % name
        if a.get("working_orders") is None or a.get("cache_seeded") is False:
            return "no: %s is not seeded yet (its position is unknown)" % name
        if a.get("open_position_count") or a.get("working_orders"):
            return "no: %s has a position or working orders" % name
    if needs_runner and not force_runner and not market_closed(now):
        booked = [k for k, v in (d.get("book") or {}).items() if k.startswith("lab_") and v]
        if booked:
            return "no: %s is booked on an account (a runner restart would end its day)" % booked[0]
    return "ok"


def main(argv) -> str:
    now = datetime.now(ZoneInfo("America/New_York"))
    try:
        d = json.load(urllib.request.urlopen("http://127.0.0.1:8850/api/status", timeout=8))
    except Exception as e:  # noqa: BLE001
        return "no: the desk is not answering (%s)" % type(e).__name__
    return verdict(d, now, argv[1:2] == ["1"], forced())


if __name__ == "__main__":
    print(main(sys.argv))
