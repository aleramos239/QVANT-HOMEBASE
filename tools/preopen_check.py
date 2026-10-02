"""Pre-open health check: one read-only screen of what went wrong silently on 2026-10-02.

    .venv/bin/python -m tools.preopen_check [--json]

Exit 0 = nothing to look at, 1 = something to look at (WARN), 2 = fix before the open (FAIL).

It reads only: both services' status endpoints, today's tick and depth archive files, the Mac's clock, power and load.
It places nothing, writes nothing and never calls a write endpoint. Run it before 08:15 and 09:00 ET, and any time
a chart looks wrong. What it looks for, and why:
  - thin candles: minutes holding almost no trades between normal ones (a feed gap the recorder did not mark);
  - depth stamps behind the clock (the liquidity heat map then draws left of the candles);
  - the chart service running out of file descriptors, the machine loaded so the recorder is starved;
  - the Mac's clock, battery, and the desk's own readiness blockers (unconnected paper accounts, power)."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

OK, WARN, FAIL = "OK", "WARN", "FAIL"
ET = ZoneInfo("America/New_York")
DESK, CHARTS = "http://127.0.0.1:8850", "http://127.0.0.1:8852"
TRADED_ROOTS = ("NQ", "GC", "ES")
DEPTH_ROOTS = ("NQ", "ES")
CHARTS_PLIST = Path.home() / "Library/LaunchAgents/com.ramosquant.homebase-charts.plist"


# ------------------------------------------------------------------ the judgements (pure, tested)
def thin_stretches(counts: dict, first: int, last: int, *, thin: int = 3, baseline: int = 25, radius: int = 15,
                   skip=()) -> list:
    """Stretches [(start_minute, end_minute)] of consecutive THIN minutes: at most `thin` trades in a minute whose
    neighbours (`radius` minutes either side) have a median of at least `baseline`. Quiet hours are never flagged
    (their neighbours are quiet too). A single thin minute is ignored unless it has no trade at all. `counts` is
    {epoch_minute: trades}; `skip` is minutes already marked as gaps."""
    skipped = set(skip)
    bad = []
    for m in range(first, last + 1):
        if m in skipped or counts.get(m, 0) > thin:
            continue
        around = [counts.get(k, 0) for k in range(m - radius, m + radius + 1) if k != m]
        if around and statistics.median(around) >= baseline:
            bad.append(m)
    out = []
    for m in bad:
        if out and m == out[-1][1] + 1:
            out[-1][1] = m
        else:
            out.append([m, m])
    # one quiet minute is just a lull; two in a row, or a minute with no trade at all, is a gap
    return [(a, b) for a, b in out if b > a or counts.get(a, 0) == 0]


def minutes_in_gaps(gaps) -> set:
    """Epoch minutes covered by marked gaps [[start_ms, end_ms], ...]."""
    out = set()
    for g in gaps or []:
        try:
            a, b = int(g[0]) // 60000, int(g[1]) // 60000
        except (TypeError, ValueError, IndexError):
            continue
        out.update(range(a, b + 1))
    return out


def depth_lag_level(lag_s: float) -> str:
    return OK if lag_s <= 60 else WARN


def fd_level(used: int, limit: int) -> str:
    r = used / limit if limit else 0
    return FAIL if r >= 0.8 else WARN if r >= 0.5 else OK


def load_level(load1: float, ncpu: int) -> str:
    r = load1 / max(1, ncpu)
    return FAIL if r >= 1.5 else WARN if r >= 0.8 else OK


def clock_level(offset_s: float) -> str:
    return OK if abs(offset_s) <= 1 else WARN if abs(offset_s) <= 5 else FAIL


def power_level(on_battery: bool, minutes_left, minutes_to_close: float) -> str:
    """On the charger: fine. On battery: a warning, and a failure when it will not last until the close."""
    if not on_battery:
        return OK
    return FAIL if minutes_left is not None and minutes_left < minutes_to_close else WARN


# ------------------------------------------------------------------ collectors (read only)
def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # GET only
        return json.loads(r.read().decode("utf-8", "replace"))


def _sh(*cmd: str, timeout: float = 20.0) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def et_of_minute(m: int) -> str:
    return dt.datetime.fromtimestamp(m * 60, ET).strftime("%H:%M")


def check_services(now: dt.datetime) -> list:
    out = []
    for name, base in (("desk", DESK), ("chart service", CHARTS)):
        try:
            st = _get(base + "/api/status")
        except Exception as e:  # noqa: BLE001
            out.append((FAIL, name, f"not answering ({type(e).__name__})"))
            continue
        if name == "desk":
            rd = (st.get("readiness") or {}).get("checks") or []
            bad = [c for c in rd if c.get("level") in ("bad", "warn")]
            out.append((OK if not bad else (FAIL if any(c.get("level") == "bad" for c in bad) else WARN), "desk readiness",
                        "ready" if not bad else "; ".join(f"{c.get('label')}: {c.get('detail')}" for c in bad)))
            out.append((OK, "desk mode", "ARMED" if st.get("armed") else "disarmed"))
        else:
            out.append((OK if st.get("connected") else FAIL, "chart service", f"md {st.get('md')}, connected={st.get('connected')}, "
                        f"{st.get('reconnects')} reconnects since it started"))
            for what in ("recorder", "depth_recorder"):
                r = st.get(what) or {}
                out.append((OK if not r.get("error") else FAIL, what.replace("_", " "),
                            f"error: {r['error']}" if r.get("error") else f"{r.get('written')} written, {r.get('dropped', 0)} dropped"))
            for root, d in (st.get("depth") or {}).items():
                if d.get("error") and root in DEPTH_ROOTS:
                    out.append((WARN, f"depth {root}", d["error"]))
                if d.get("stamp_skew_s"):
                    out.append((WARN, f"depth {root} stamps", f"the feed's stamps are {d['stamp_skew_s']:+d} s from the clock (corrected to arrival time)"))
                if d.get("mode"):
                    out.append((WARN, f"depth {root} mode", f"subscribed in {d['mode']!r} mode, not real time"))
    return out


def check_fds() -> list:
    pid = _sh("lsof", "-nP", "-iTCP:8852", "-sTCP:LISTEN", "-t").split()
    if not pid:
        return [(WARN, "file descriptors", "chart service pid not found")]
    used = max(0, len(_sh("lsof", "-nP", "-p", pid[0]).splitlines()) - 1)
    limit = 256                                       # launchd's default soft limit
    try:
        v = _sh("plutil", "-extract", "SoftResourceLimits.NumberOfFiles", "raw", str(CHARTS_PLIST)).strip()
        limit = int(v) if v.isdigit() else limit
    except Exception:  # noqa: BLE001
        pass
    return [(fd_level(used, limit), "file descriptors", f"chart service has {used} of {limit} open")]


def check_load() -> list:
    load1, ncpu = os.getloadavg()[0], os.cpu_count() or 1
    lvl = load_level(load1, ncpu)
    detail = f"load {load1:.1f} on {ncpu} cores"
    if lvl != OK:
        top = [ln.split(None, 1) for ln in _sh("ps", "-Ao", "pcpu,comm", "-r").splitlines()[1:6]]
        detail += "; busiest: " + ", ".join(f"{os.path.basename(c)} {p}%" for p, c in (t for t in top if len(t) == 2))
        detail += " (the chart service runs at low priority on purpose, so a loaded machine starves its recorder)"
    return [(lvl, "machine load", detail)]


def check_clock() -> list:
    m = re.search(r"([+-]\d+\.\d+) \+/-", _sh("sntp", "time.apple.com", timeout=15))
    if not m:
        return [(WARN, "clock", "could not reach the time server")]
    off = float(m.group(1))
    return [(clock_level(off), "clock", f"{off:+.2f} s from internet time")]


def check_power(now: dt.datetime) -> list:
    s = _sh("pmset", "-g", "batt")
    on_batt = "Battery Power" in s
    pct = re.search(r"(\d+)%", s)
    left = re.search(r"(\d+):(\d+) remaining", s)
    mins_left = int(left.group(1)) * 60 + int(left.group(2)) if left else None
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    to_close = max(0.0, (close - now).total_seconds() / 60)
    lvl = power_level(on_batt, mins_left, to_close)
    detail = "plugged in" if not on_batt else f"ON BATTERY {pct.group(1) if pct else '?'}%, {mins_left // 60}h{mins_left % 60:02d} left" if mins_left is not None else "ON BATTERY"
    return [(lvl, "power", detail + ("" if lvl == OK else " — plug in"))]


def check_ticks(now: dt.datetime) -> list:
    from homebase.charts.session import session_date
    from homebase.charts.store import ARCHIVE, TickStore
    store, out = TickStore(ARCHIVE), []
    now_ms = int(now.timestamp() * 1000)
    for root in TRADED_ROOTS:
        sess = store.load(root, session_date(now_ms, root))
        if sess is None or not sess.ticks:
            out.append((WARN, f"ticks {root}", "no ticks recorded for this session"))
            continue
        counts = Counter(t.ts_ms // 60000 for t in sess.ticks)
        first, last = max(min(counts), now_ms // 60000 - 600), now_ms // 60000 - 1
        marked = minutes_in_gaps(sess.gaps)
        thin = thin_stretches(counts, first, last, skip=marked)
        gap_text = f"{len(sess.gaps)} marked gap(s)" if sess.gaps else "no marked gaps"
        if thin:
            out.append((WARN, f"ticks {root}", "thin candles (unmarked data gap): " + ", ".join(
                f"{et_of_minute(a)}" + (f"-{et_of_minute(b)}" if b != a else "") for a, b in thin[-6:]) + f" ET; {gap_text}"))
        else:
            out.append((OK, f"ticks {root}", f"{len(sess.ticks)} ticks, no thin candles in the last 10 h; {gap_text}"))
    return out


def check_depth_stamps(now: dt.datetime) -> list:
    from homebase.charts.depth import read_depth
    out = []
    d = (now + dt.timedelta(days=1)).date() if now.time() >= dt.time(18, 0) else now.date()
    for root in DEPTH_ROOTS:
        files = sorted((Path.home() / "futures_depth" / root / str(d.year)).glob(f"{d.isoformat()}_*.depth.jsonl.gz"),
                       key=lambda p: p.stat().st_mtime)
        if not files:
            out.append((WARN, f"depth {root}", "no depth file for this session"))
            continue
        if time.time() - files[-1].stat().st_mtime > 300:
            out.append((OK, f"depth {root}", "not being written right now (market closed or recorder idle): lag not checked"))
            continue
        rows = read_depth(files[-1])
        if not rows:
            out.append((WARN, f"depth {root}", "depth file is empty"))
            continue
        lag = time.time() - rows[-1]["t"] / 1000
        lvl = depth_lag_level(lag)
        out.append((lvl, f"depth {root} stamps", f"newest recorded book is {lag:.0f} s behind the clock"
                    + ("" if lvl == OK else " — the heat map will draw that far left of the candles")))
    return out


def run() -> list:
    now = dt.datetime.now(ET)
    results = []
    for name, fn in (("services", lambda: check_services(now)), ("file descriptors", check_fds), ("machine load", check_load),
                     ("clock", check_clock), ("power", lambda: check_power(now)),
                     ("ticks", lambda: check_ticks(now)), ("depth", lambda: check_depth_stamps(now))):
        try:
            results.extend(fn())
        except Exception as e:  # noqa: BLE001 — one failed check must never hide the others
            results.append((WARN, name, f"check failed: {type(e).__name__}: {e}"))
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    results = run()
    worst = max((r[0] for r in results), key=(OK, WARN, FAIL).index, default=OK)
    if a.json:
        print(json.dumps({"worst": worst, "checks": [{"level": l, "name": n, "detail": d} for l, n, d in results]}, indent=1))
    else:
        print(f"Pre-open check, {dt.datetime.now(ET):%a %H:%M} ET")
        for lvl, name, detail in results:
            print(f"  [{lvl:<4}] {name}: {detail}")
        warns, fails = sum(r[0] == WARN for r in results), sum(r[0] == FAIL for r in results)
        print(f"{'ALL CLEAR' if worst == OK else f'{fails} to fix, {warns} to look at'}")
    return {OK: 0, WARN: 1, FAIL: 2}[worst]


if __name__ == "__main__":
    sys.exit(main())
