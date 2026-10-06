"""checks.py -- THE CODE CHECK: phase 1 of BLUEPRINT.md section 2 on a store or on a plain trades file (toolkit plan, step 7).
"Does the code do what the card says?" It is asked on build days only and BEFORE any result is believed: the rest of the
blueprint guards against luck, not against a wrong test. One function per line; each takes the TRADE TABLE of what is checked
and returns {"line", "passed", "number", "need", "text"} + the trades that break it (`exceptions`, the first SHOWN):
  1.1 window        every trade is entered inside the stated session window
  1.2 one_position  one position at a time, and every trade is flat by 15:58 ET (13:13 on half days)
  1.3 count         never more trades than the stated maximum: a session and day in a store, a day in a trades file
  1.4 payoff        with a stop and a target on, a target exit pays about the target and a stop exit costs about the stop
  1.5 chart         the 10 trades the owner looks at on the chart: the first 5 and 5 drawn with a fixed seed
  1.6 reproduced    after a change to the code: the earlier trade list again, field for field
Every number is read from rules.json: the flat times and the minute a trade may still close in (1.2), "about" = within 2
ticks (1.4), the 10 trades and their seed (1.5). A half day is the engine's calendar (l2sim.EARLY_CLOSES, equity-index
markets). passed None = the line cannot be read here (the text says what is missing); phase 1 is passed on TRUE lines only.

HOW 1.4 IS READ. A trade ends at its target, at its stop, or by another exit (the clock at 15:58, a trailing / bar / book
exit). "Pays" and "costs" are the trade's net in dollars after costs, as every dollar of the blueprint.
  a target exit   must pay about the target (a limit fills at its price)                    else the trade is OFF
  a stop exit     costs about the stop, or more: a stop that is gapped costs the gap -- LISTED, not off (the fill law);
                  one that cost less than about its stop is OFF
  another exit    is listed by how many: it ends between the two
  a store with a fixed-point stop: a stop that is not the stated points is OFF (the code does not do what the card says)
A list without exit reasons is read by what each trade paid; nothing may pay more than about its target.
A STORE keeps each trade's stop distance (in whole ticks) and its cell's reward:risk, not the target price: the target is
known to (r + 1) / 2 ticks, which is added to "about". An idea that sets its OWN target level (ib fade, gap fill) shows
itself by target exits in its cells WITHOUT a target: those exits are counted and not held against a distance.

THE TRADE TABLE (load): a dict of arrays, one row per trade --
  cell (its list: a cell of the store, or the one list of a file) · date (trade-date ordinal) · entry, exit (ms; a store
  keeps the holding time in whole seconds, so an overlap or a late exit shorter than a second cannot be seen in it) · net ·
  side · qty (contracts: 1 in a store) · sess (code of library.SESS7, -1 = none) · reason (code of library.REASONS, -1 = not
  given) · stop_usd, target_usd (NaN = none / not known), slack_usd · own, stated_off, stop_pts, stated_stop · num (its
  number in its list, by entry time)
  + lists [{id, max}], sessions, window, per_session, unit, root, pv, tick, name, kind, where, label.
THE SEAL: a store whose range is not inside the build days is refused before a trade is loaded (runner.guard); any trade
dated, entered or closed on or after 2025-07-01 is refused whatever the file says (seal).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB

from . import W
from . import lines as L
from . import rules as R
from . import runner as RUN

TP, SL, OTHER = (LB.REASONS.index(k) for k in ("tp", "sl", "other"))
SHOWN = 20                                          # exceptions listed in a result (their count is always whole)
FIELDS = ("date", "entry", "exit", "net", "side", "reason", "stop_usd", "target_usd")      # what 1.6 holds against the earlier list


# ================================================================ the trade table

def _contract(market) -> tuple:
    """(dollars a point, tick) of a market (costs.json)."""
    c = R.template("costs")["contract"]
    if market not in c:
        raise J.Refuse(f"market {market!r}: one of {', '.join(c)}" if market else f"a trades file does not say its market: give --market ({', '.join(c)})")
    return float(c[market]["point_value"]), float(c[market]["tick"])


def _sessions(sessions):
    if sessions is None:
        return None
    bad = [s for s in sessions if s not in LB.SESS_CODE]
    if bad or not sessions:
        raise J.Refuse(f"session {bad[0] if bad else ''!r}: the sessions are {', '.join(LB.SESS7)}")
    return list(sessions)


def _window(window):
    """'HH:MM-HH:MM' (New York clock, the end not inside) -> (start second, end second, the words)."""
    if window is None:
        return None
    m = re.fullmatch(r"(\d\d):(\d\d)-(\d\d):(\d\d)", str(window))
    a, b = (int(m[1]) * 3600 + int(m[2]) * 60, int(m[3]) * 3600 + int(m[4]) * 60) if m else (0, 0)
    if not m or not a < b <= 86400:
        raise J.Refuse(f"window {window!r}: HH:MM-HH:MM on the New York clock, the start before the end (09:30-11:00)")
    return a, b, str(window)


def _number(t: dict) -> dict:
    """+ num: each trade's number in its list by entry time (1 = the first), as a person counts them on a chart."""
    order = np.lexsort((t["exit"], t["entry"], t["cell"]))
    c = t["cell"][order]
    first = np.r_[True, c[1:] != c[:-1]] if len(c) else np.zeros(0, bool)
    t["num"] = np.zeros(len(c), np.int64)
    t["num"][order] = np.arange(len(c)) - np.maximum.accumulate(np.where(first, np.arange(len(c)), 0)) + 1
    return t


def from_store(d: Path, sessions=None, window=None, max_per_day=None) -> dict:
    """The trade table of a store (library.write_unit's format), every cell a list. What the store states is read from it:
    the sessions it was run in, each cell's maximum of entries a session and day (max_tr), its stop and reward:risk. What
    the caller states (sessions, window, max_per_day) wins. The range is read first: runner.guard."""
    label = f"{d.parent.name}/{d.name}"
    try:
        meta = json.loads((d / "run.json").read_text())
    except (OSError, ValueError) as e:
        raise J.Refuse(f"store {label}: {e}") from None
    RUN.guard(meta, label)
    u = LB.load_unit(d.name, d.parent)
    pv, tick = _contract(meta.get("root"))
    cells = meta["cells"]
    cell = np.repeat(np.arange(len(cells)), np.diff(u["off"]))
    ex = [c.get("exit") or {} for c in cells]
    r = np.array([float(x.get("tgt_r") or 0.0) for x in ex])[cell]
    vi, reason = np.array([int(c.get("vi") or 0) for c in cells])[cell], u["reason"].astype(np.int64)
    risk = np.where(np.array([bool(c.get("info")) for c in cells])[cell], np.nan, u["risk"].astype(np.float64))      # an author cell: its own exits
    own = np.isin(vi, np.unique(vi[(r == 0) & (reason == TP)]))                 # target exits in a cell without a target
    pts = np.array([x.get("stop_mode") == "pts" for x in ex])[cell]
    stated = np.array([float(x.get("stop_val") or 0.0) for x in ex])[cell]
    stated_by = sessions or meta.get("sessions") or meta.get("passes") or ([meta["sess_instance"]] if meta.get("sess_instance") else list(LB.SESS7))
    entry = u["entry_ms"].astype(np.int64)
    return _number({
        "name": meta.get("idea") or meta.get("key") or d.name, "kind": "store", "where": str(d), "label": label, "root": meta.get("root"), "pv": pv, "tick": tick,
        "lists": [{"id": c["id"], "max": (c.get("inputs") or {}).get("max_tr") if max_per_day is None else max_per_day} for c in cells],
        "cell": cell, "date": u["date"].astype(np.int64), "entry": entry, "exit": entry + u["dur_s"].astype(np.int64) * 1000,
        "net": u["net"].astype(np.float64), "side": u["side"].astype(np.int64), "qty": np.ones(len(cell)), "sess": u["sess"].astype(np.int64), "reason": reason,
        "stop_usd": risk * pv, "target_usd": np.where((r > 0) & ~own, r * risk * pv, np.nan), "slack_usd": (r + 1.0) / 2.0 * tick * pv, "own": own,
        "stop_pts": risk, "stated_stop": stated, "stated_off": pts & np.isfinite(risk) & (np.abs(risk - stated) > tick / 2.0),
        "sessions": _sessions(stated_by), "window": window, "per_session": True, "unit": "a session and day"})


def from_trades(rows, market, sessions=None, window=None, max_per_day=None, name: str = "trades", where: str = "") -> dict:
    """The trade table of a plain trade list (the engine's and the tester's row: side, entry_ms, exit_ms, net; with date,
    entry_price, sl, tp, exit_reason, qty when it has them). ONE list: one position at a time over the whole of it, the
    maximum is a day's. What a list does not state -- its window, its maximum, its stops -- the caller states, or the line
    is not read. A row without `date` is dated by its entry (from 18:00 New York time on: the next day)."""
    if not isinstance(rows, list) or not all(isinstance(x, dict) for x in rows):
        raise J.Refuse(f"{where or name}: a trades file is a JSON list of trades (or an object with that list under \"trades\")")
    miss = sorted({k for x in rows for k in ("side", "entry_ms", "exit_ms", "net") if k not in x})
    if miss:
        raise J.Refuse(f"{where or name}: a trade row needs side, entry_ms, exit_ms and net; missing: {', '.join(miss)}")
    pv, tick = _contract(market)
    entry = np.array([int(x["entry_ms"]) for x in rows], np.int64)

    def day(x) -> int:
        if x.get("date"):
            return S._date(x["date"]).toordinal()
        a = dt.datetime.fromtimestamp(int(x["entry_ms"]) / 1000, S.ET)
        return a.date().toordinal() + (a.hour >= 18)

    qty = np.array([float(x.get("qty") or 1) for x in rows], np.float64)

    def dist(x, k) -> float:
        return abs(float(x["entry_price"]) - float(x[k])) * pv * float(x.get("qty") or 1) if x.get("entry_price") is not None and x.get(k) is not None else np.nan

    why = [x.get("exit_reason") for x in rows]
    n = len(rows)
    return _number({
        "name": name, "kind": "trades", "where": where, "label": Path(where).name if where else name, "root": market, "pv": pv, "tick": tick,
        "lists": [{"id": name, "max": max_per_day}], "cell": np.zeros(n, np.int64), "date": np.array([day(x) for x in rows], np.int64), "entry": entry,
        "exit": np.array([int(x["exit_ms"]) for x in rows], np.int64), "net": np.array([float(x["net"]) for x in rows], np.float64),
        "side": np.array([1 if x["side"] in ("long", 1) else -1 for x in rows], np.int64), "qty": qty, "sess": LB.session_code(entry).astype(np.int64),
        "reason": np.array([-1 if k is None else LB.REASONS.index(k) if k in LB.REASONS else OTHER for k in why], np.int64),
        "stop_usd": np.array([dist(x, "sl") for x in rows], np.float64), "target_usd": np.array([dist(x, "tp") for x in rows], np.float64),
        "slack_usd": np.zeros(n), "own": np.zeros(n, bool), "stop_pts": np.full(n, np.nan), "stated_stop": np.zeros(n), "stated_off": np.zeros(n, bool),
        "sessions": sessions, "window": window, "per_session": False, "unit": "a day"})


def seal(t: dict) -> dict:
    """THE SEAL: a table that holds a trade dated, entered or closed on or after the first test day is refused whole. The
    code check reads build days only (BLUEPRINT.md phase 1: "never on the test period")."""
    start = R.template("ranges")["test"]["start"]
    day = S._date(start)
    if len(t["date"]) and (int(t["date"].max()) >= day.toordinal() or int(max(t["entry"].max(), t["exit"].max())) >= S.et_ns(day, "00:00") // 1_000_000):
        raise J.Refuse(f"{t['label']} holds a trade on or after {start}: the code check reads build days only, never the test period")
    return t


def find(source, out=None) -> Path:
    """Where a store or a trades file is: a path as it is given; else a store KEY in the store folder (`out`, runs_bp/
    unless told); else a path under the edge-library folder, as the library names a store (runs/orb-NQ-tf15)."""
    p = Path(str(source)).expanduser()
    for c in ([p] if p.is_absolute() else [(RUN.RUNS if out is None else Path(out)) / p, W / p, Path.cwd() / p]):
        if c.exists():
            return c
    raise J.Refuse(f"no store and no trades file {source}" + ("" if p.is_absolute() else f" (looked in {RUN.RUNS.name if out is None else out}/ and under {W.name}/)"))


def load(store=None, trades=None, out=None, market=None, sessions=None, window=None, max_per_day=None) -> dict:
    """The sealed trade table of a store (its key or path) or of a trades file (a JSON list, an object with `trades`, or a
    folder with trades.json; an engine bundle's run.json names the market when the caller does not)."""
    sessions, window = _sessions(sessions), _window(window)
    if store is not None:
        d = find(store, out)
        if not ((d / "run.json").exists() and (d / "cells.npz").exists()):
            raise J.Refuse(f"{d} is not a store (run.json and cells.npz)")
        return seal(from_store(d, sessions, window, max_per_day))
    f = find(trades, out)
    f = f / "trades.json" if f.is_dir() else f
    try:
        rows = json.loads(f.read_text())
        if market is None and (f.parent / "run.json").exists():
            market = json.loads((f.parent / "run.json").read_text()).get("root")
    except (OSError, ValueError) as e:
        raise J.Refuse(f"trades file {f}: {e}") from None
    return seal(from_trades(rows.get("trades") if isinstance(rows, dict) else rows, market, sessions, window, max_per_day, f.stem, str(f)))


# ================================================================ the lines

def _et(ms, fmt: str = "%H:%M:%S") -> str:
    return dt.datetime.fromtimestamp(int(ms) / 1000, S.ET).strftime(fmt)


def _s(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _usd(v) -> str:
    return L._n(float(v), unit="$")


def _when(t: dict, i: int, ms) -> str:
    """A moment of trade i on the New York clock: the time -- with its own date when that is not the trade date (an evening
    entry belongs to the next trade date; an overnight hold ends after its own)."""
    day = dt.date.fromordinal(int(t["date"][i])).isoformat()
    return _et(ms) if _et(ms, "%Y-%m-%d") == day else _et(ms, "%Y-%m-%d %H:%M:%S")


def _who(t: dict, i: int) -> dict:
    """A trade as an exception names it: its list, its number in the list, its trade date and its entry time."""
    return {"list": t["lists"][int(t["cell"][i])]["id"], "trade": int(t["num"][i]), "date": dt.date.fromordinal(int(t["date"][i])).isoformat(),
            "entry_et": _when(t, i, t["entry"][i])}


def _first(t: dict, mask) -> np.ndarray:
    """The first SHOWN trades of a mask, by list and number."""
    idx = np.flatnonzero(mask)
    return idx[np.lexsort((t["num"][idx], t["cell"][idx]))][:SHOWN]


def window(t: dict) -> dict:
    """1.1 Every trade is entered inside the stated session window: the sessions the idea states (a store: the sessions it
    was run in) and / or a window on the New York clock. Not stated = not read."""
    n = len(t["net"])
    if t["sessions"] is None and t["window"] is None:
        return L._row("1.1", None, None, 0, "the stated window is not known: give --sessions or --window")
    codes = None if t["sessions"] is None else [LB.SESS_CODE[s] for s in t["sessions"]]
    out = np.zeros(n, bool) if codes is None else ~np.isin(t["sess"], codes)
    if t["window"] is not None:
        sec = np.array([(lambda a: a.hour * 3600 + a.minute * 60 + a.second)(dt.datetime.fromtimestamp(int(m) / 1000, S.ET)) for m in t["entry"]], np.int64)
        out |= ~((t["window"][0] <= sec) & (sec < t["window"][1]))
    said = " and ".join(x for x in ("" if codes is None else f"sessions {', '.join(t['sessions'])}", "" if t["window"] is None else f"{t['window'][2]} ET") if x)

    def what(i) -> str:
        if codes is not None and t["sess"][i] not in codes:
            return "entered outside every session" if t["sess"][i] < 0 else f"entered in session {LB.SESS7[int(t['sess'][i])]}"
        return f"entered at {_et(t['entry'][i])} ET"

    k = int(out.sum())
    return L._row("1.1", k == 0, k, 0, (f"every one of the {n:,} trades is entered" if not k else f"{k:,} of the {n:,} trades {'is' if k == 1 else 'are'} entered")
                  + f" {'inside' if not k else 'outside'} the stated window ({said})", exceptions=[{**_who(t, i), "what": what(i)} for i in _first(t, out)])


def one_position(t: dict) -> dict:
    """1.2 One position at a time, and every trade is flat by 15:58 ET (13:13 on half days). An overlap = a trade entered
    while an earlier one of its list was still open -- in a store: of its list AND session (the library runs a cell as one
    instance per session, a judged unit is one session). Late = still open one minute after the flat time of its own trade
    date (rules.json: the engine flattens on the first print from 15:58:00 on); an overnight hold is late."""
    need, within = R.need("1.2"), R.rule("1.2")["also"]["flat_within_s"]
    n = len(t["net"])
    days, inv = np.unique(t["date"], return_inverse=True)
    half = np.array([dt.date.fromordinal(int(o)) in S.EARLY_CLOSES and t["root"] in S.EQUITY_INDEX_ROOTS for o in days], bool)
    last = np.array([S.et_ns(dt.date.fromordinal(int(o)), need["flat_et_half_day" if h else "flat_et"]) // 1_000_000 for o, h in zip(days, half)], np.int64) + within * 1000
    late = t["exit"] >= last[inv]
    gid = t["cell"] * 8 + (t["sess"] + 1 if t["per_session"] else 0)
    order = np.lexsort((t["exit"], t["entry"], gid))
    g, e = gid[order], t["entry"][order]
    top = np.maximum.accumulate((g << 44) + t["exit"][order])       # the latest exit so far, group by group (an exit in ms fits 44 bits)
    over = np.zeros(n, bool)
    over[order[1:]] = (g[1:] == g[:-1]) & (((g[1:] << 44) + e[1:]) < top[:-1])

    def blocker(i) -> int:
        m = (gid == gid[i]) & (t["entry"] <= t["entry"][i]) & (t["exit"] > t["entry"][i])
        m[i] = False
        return int(t["num"][np.flatnonzero(m)[np.argmax(t["exit"][m])]])

    exc = [{**_who(t, i), "what": f"still open at {_et(last[inv][i], '%H:%M')} ET of its trade date{', a half day' if half[inv][i] else ''} "
                                  f"(closed {_et(t['exit'][i], '%Y-%m-%d %H:%M:%S')} ET)"} for i in _first(t, late)]
    exc += [{**_who(t, i), "what": f"entered while trade {blocker(i)} was still open"} for i in _first(t, over)]
    a, b = int(over.sum()), int(late.sum())
    cnt = lambda k, word: f"no {word}" if not k else _s(k, word)  # noqa: E731
    return L._row("1.2", a + b == 0, a + b, need, f"one position at a time and flat by {need['flat_et']} ET ({need['flat_et_half_day']} on half days): "
                  f"{cnt(a, 'overlap')} and {cnt(b, 'late exit')} in {n:,} trades", overlaps=a, late=b, exceptions=exc[:SHOWN])


def count(t: dict) -> dict:
    """1.3 The number of trades is what the rule implies: never more than the stated maximum -- in a store each cell's own
    max_tr, counted per session and day (an instance trades one session); in a trades file the caller's maximum a day. A
    list without any trade is not what a rule implies either. Not stated = not read."""
    n, k = len(t["net"]), len(t["lists"])
    if not n:
        return L._row("1.3", False, 0, None, "no trade at all: a rule that never trades is not what any idea implies")
    mx = np.array([-1 if x["max"] is None else int(x["max"]) for x in t["lists"]], np.int64)
    if (mx < 0).all():
        return L._row("1.3", None, None, None, "the stated maximum is not known: give --max-per-day")
    key = (t["cell"] << 28) + (t["date"] << 4) + (t["sess"] + 1 if t["per_session"] else 0)
    _, first, cnt = np.unique(key, return_index=True, return_counts=True)
    lim = mx[t["cell"][first]]
    over = (lim >= 0) & (cnt > lim)
    most, lo, hi = int(cnt[lim >= 0].max()), int(mx[mx >= 0].min()), int(mx.max())
    said = str(hi) if lo == hi else f"{lo} to {hi}"
    exc = [{"list": t["lists"][int(t["cell"][i])]["id"], "date": dt.date.fromordinal(int(t["date"][i])).isoformat(),
            **({"session": LB.SESS7[int(t["sess"][i])] if t["sess"][i] >= 0 else None} if t["per_session"] else {}), "what": _s(int(c), "trade")}
           for i, c in zip(first[over][:SHOWN], cnt[over][:SHOWN])]
    bad = int(over.sum())
    return L._row("1.3", bad == 0, most, hi, f"never more than the stated maximum of {said} {t['unit']}: the most is {most} ({n:,} trades in {_s(k, 'list')})" if not bad
                  else f"the most is {most} (need at most {said}): {bad:,} over", exceptions=exc)


def payoff(t: dict) -> dict:
    """1.4 With a stop and a target on, winners pay about the target and losers cost about the stop, in dollars; exceptions
    are listed. How it is read: module docstring. number = the trades that are OFF; the gapped stops are listed with them."""
    ticks = R.rule("1.4")["also"]["within_ticks"]
    one, eps = ticks * t["tick"] * t["pv"], 1e-6
    tol = one * t["qty"]                            # "about" is 2 ticks a contract
    net, stop, tgt, r = t["net"], t["stop_usd"], t["target_usd"], t["reason"]
    on = np.isfinite(stop)
    if not on.any():
        return L._row("1.4", None, None, 0, "no stop and target on the trades (a list without their prices cannot be held against them)")
    known, wide = np.isfinite(tgt), tol + t["slack_usd"] + eps
    with np.errstate(invalid="ignore"):
        near = known & (np.abs(net - tgt) <= wide)
        stated = on & t["stated_off"]
        ok = on & ~stated
        tp = ok & ((r == TP) | ((r < 0) & near))                    # ended at its target (said, or read from what it paid)
        sl = ok & ~tp & ((r == SL) | ((r < 0) & (-net >= stop - tol - eps)))
        other = ok & ~tp & ~sl
        own = tp & (t["own"] | ~known)                              # its target is the idea's own level: no distance to hold it against
        at_t, off_t = tp & ~own & near, tp & ~own & ~near
        at_s, gap, off_s = sl & (np.abs(-net - stop) <= tol + eps), sl & (-net > stop + tol + eps), sl & (-net < stop - tol - eps)
        off_m = other & (r < 0) & known & (net > tgt + wide)
    off = stated | off_t | off_s | off_m

    def what(i) -> str:
        if stated[i]:
            return f"its stop is {t['stop_pts'][i]:g} points from the entry, not the stated {t['stated_stop'][i]:g}"
        if off_t[i]:
            return f"ended at its target and paid {_usd(net[i])}, not about the target of {_usd(tgt[i])}"
        if off_s[i]:
            return f"ended at its stop and cost {_usd(-net[i])}, less than about the stop of {_usd(stop[i])}"
        if off_m[i]:
            return f"paid {_usd(net[i])}, more than about its target of {_usd(tgt[i])}"
        return f"its stop was gapped: it cost {_usd(-net[i])} against a stop of {_usd(stop[i])}"

    worst = np.flatnonzero(gap)
    worst = worst[np.argsort(-(-net[worst] - stop[worst]), kind="stable")]
    exc = [{**_who(t, i), "ended": LB.REASONS[int(r[i])] if r[i] >= 0 else None, "net": round(float(net[i]), 2), "stop_usd": round(float(stop[i]), 2),
            "target_usd": round(float(tgt[i]), 2) if known[i] else None, "what": what(i)} for i in [*_first(t, off), *worst][:SHOWN]]
    k, a, b, g, o, w = (int(x.sum()) for x in (off, at_t, at_s, gap, other, own))
    listed = ([f"{_s(g, 'stop')} gapped (the worst cost {_usd(-net[worst[0]] - stop[worst[0]])} more than its stop)"] if g else []) \
        + ([f"{o:,} closed by the clock or another exit"] if o else []) + ([f"{_s(w, 'target exit')} at the idea's own level, not held against a distance"] if w else [])
    text = (f"{_s(k, 'trade')} {'is' if k == 1 else 'are'} off ({exc[0]['what']}); " if k else "") + \
        f"{_s(a, 'trade')} ended at the target and paid about it, {b:,} at the stop and cost about it (within {ticks} ticks = {_usd(one)})" + \
        ("; listed: " + ", ".join(listed) if listed else "")
    return L._row("1.4", k == 0, k, 0, text, at_target=a, at_stop=b, gapped=g, other=o, own_target=w, tolerance_usd=float(one), exceptions=exc, exceptions_total=k + g)


def chart(t: dict, looked: bool = False, cell=None) -> dict:
    """1.5 10 trades are looked at on the chart (the first 5 and 5 at random): entry and exit sit where the rule says. The
    tool names them -- of ONE list (a store: `cell`, else its first cell with 10 trades), the same 10 for the same list
    (the fixed seed of rules.json) -- and the owner looks: the line is true only with `looked`. `look` = the 10 trades."""
    need, seed, ids = R.need("1.5"), R.rule("1.5")["also"]["seed"], [x["id"] for x in t["lists"]]
    if cell is not None and cell not in ids:
        raise J.Refuse(f"{cell!r} is not a list of {t['label']} (it has {', '.join(ids[:6])}{' ...' if len(ids) > 6 else ''})")
    size = np.bincount(t["cell"], minlength=len(ids))
    li = ids.index(cell) if cell is not None else next((i for i, k in enumerate(size) if k >= need["trades"]), int(size.argmax()))
    idx = np.flatnonzero(t["cell"] == li)
    idx = idx[np.argsort(t["num"][idx])]
    n, of = len(idx), (f" of {ids[li]}" if t["kind"] == "store" else "")
    rest = np.arange(need["first"] + 1, n + 1)
    picks = list(range(1, min(n, need["first"]) + 1)) + (sorted(np.random.default_rng(seed).choice(rest, min(need["random"], len(rest)), replace=False).tolist()) if len(rest) else [])

    def one(k: int) -> dict:
        i = idx[k - 1]
        return {**_who(t, i), "exit_et": _when(t, i, t["exit"][i]), "side": "long" if t["side"][i] > 0 else "short",
                "session": LB.SESS7[int(t["sess"][i])] if t["sess"][i] >= 0 else None, "ended": LB.REASONS[int(t["reason"][i])] if t["reason"][i] >= 0 else None}

    how, nums = f"the first {need['first']} and {need['random']} at random", ", ".join(f"#{k}" for k in picks)
    if n < need["trades"]:
        return L._row("1.5", False, len(picks) if looked else 0, need["trades"], f"only {_s(n, 'trade')}{of}: {need['trades']} are looked at on the chart ({how})",
                      look=[one(k) for k in picks])
    return L._row("1.5", bool(looked), len(picks) if looked else 0, need["trades"],
                  (f"the owner looked at {len(picks)} trades{of} on the chart ({how}): {nums}" if looked else
                   f"the owner has not looked yet: look at these {len(picks)} trades{of} on the chart ({how}), then run it again with --looked: {nums}"),
                  look=[one(k) for k in picks])


def reproduced(t: dict, earlier=None) -> dict:
    """1.6 After any change to the code, the earlier trade list is reproduced exactly before a new run counts. `earlier` =
    the trade table of the earlier store or file: every list of it must be in the new one (a store: by cell id; two plain
    lists: one against the other), trade for trade in entry order, FIELDS for FIELDS. No earlier list = not read."""
    if earlier is None:
        return L._row("1.6", None, None, 0, "no earlier trade list was given (after a change to the code: --same-as <the earlier store or file>)")
    now, plain = {x["id"]: i for i, x in enumerate(t["lists"])}, len(t["lists"]) == len(earlier["lists"]) == 1
    bad, n = [], 0

    def rows(x, i):
        idx = np.flatnonzero(x["cell"] == i)
        return idx[np.argsort(x["num"][idx])]

    for j, x in enumerate(earlier["lists"]):
        i = 0 if plain else now.get(x["id"])
        if i is None:
            bad.append(f"{x['id']} is missing")
            continue
        a, b = rows(earlier, j), rows(t, i)
        n += len(a)
        if len(a) != len(b):
            bad.append(f"{x['id']}: {len(a):,} trades earlier, {len(b):,} now")
            continue
        for k in FIELDS:
            p, q = earlier[k][a].astype(np.float64), t[k][b].astype(np.float64)
            d = np.flatnonzero(~((p == q) | (np.isnan(p) & np.isnan(q))))
            if len(d):
                bad.append(f"{x['id']}: trade {int(d[0]) + 1} differs in {k}")
                break
    k = len(earlier["lists"])
    return L._row("1.6", not bad, len(bad), 0, f"the earlier trade list is reproduced exactly: {n:,} trades in {_s(k, 'list')} ({earlier['label']})" if not bad
                  else f"{len(bad):,} of {_s(k, 'list')} differ{'s' if len(bad) == 1 else ''} from {earlier['label']}: {bad[0]}", differ=bad[:SHOWN])
