"""evalcard.py -- PHASE 6, THE EVAL (toolkit plan, step 10): `bp.py eval-card <name> [--fills=-|FILE] [--account=ID]`.
"Do real fills and results match the test?" The card stands on the simulator's result for ONE account (propodds.py:
sim/<account>.json -- the variant read for the account, the eval's size, the owner's attempts and fee budget of line 5.4)
and is refused until one is on file. Which account: the one named; else the one of the card on file; else the simulator
result saved last. A later look at another account does not move a card.

WITHOUT FILLS it is the card as it stands before the first live trade: lines 6.1-6.9 as the rules to follow (none judged),
and THE TABLES of the variant's own test-period trades at the simulator's size -- a Monte Carlo of whole days drawn with
replacement (montecarlo.json: its runs, its fixed seed; a run is drawn until the last read, 40 trades), read after 10, 20,
30 and 40 trades at the 50th, 75th, 90th, 95th and 99th percentile:
    DRAWDOWN   the largest fall of the run's P&L from its highest point so far (the start counts as a point)
    P&L        from the BAD side: the P&L that 50 / 75 / 90 / 95 / 99 % of the runs beat
The trades are the simulator's (propodds.ledger): the micro cost model, after the account's soft daily loss limit.

WITH FILLS (the live trades of the eval so far) the lines are read. Every 6.x line is in the result; passed null = not
judged yet, and its text says what it waits for. "Not judged yet" is never a pass: the app's idea store calls an idea
PROVEN LIVE only when 6.1-6.5 are each TRUE.
  6.1  live equals the test: every live trade against the tester's replay of it -- the same entry time (within the
       seconds of rules.json 6.1) and the same exit reason. A trade that differs, a trade the replay does not have, an
       order that was missed or rejected = a MISMATCH, listed by its number. A mismatch is a bug: once it is fixed the
       fill is sent with `fixed` (what the bug was) and the count goes on -- it is still not a clean trade.
       true = every order has its replay and none differs; null = some replay is not on file yet
  6.2  stage A, at 1 micro: the average entry slip of its trades is 2 ticks or less, and no order of it was missed or
       rejected. A missed order fails it for good: stage A is started again (the fills are sent from the restart on).
  6.3  stage A is passed after 5 CLEAN trades (filled, at 1 micro, equal to the test) with 6.2 true. From the next trade
       on the eval is at size: STAGE B, at the simulator's size.
  6.4  stage B, read after 10, 20, 30 and 40 trades at size: the live drawdown on its row of the table -- under the 75th
       percentile: carry on · at the 75th: cut size · at the 95th: THE HARD ALARM (line 6.9). Live trades are scaled to the
       table's size (net x table size / live size), so a cut size is read on the same table.
       false = a read at the 95th (the hard alarm: switched off, line 6.9); true = all four reads done, none at the 95th (a cut is
       an order that was followed, not a failed line); null = fewer than 40 trades at size, the reads so far in the text
  6.5  after 40 trades at size: the live average trade (per micro) is at least half of the test's; otherwise THE SOFT
       ALARM: the review of line 6.6
  6.6 - 6.9  stated, never judged here: the soft alarm is a review (three questions), not a switch-off by itself · only the
       size may change, never the rule · a bust inside the drawdown table does not retire the strategy, running out of the
       attempts of line 5.4 does · the hard alarm switches the strategy off and no review turns it back on: it comes back
       when the tester's replay shows the recovery of line 6.9 (the course's rule; the owner, 2026-10-06).
       (So a review the owner ends with "carry on" stays on the card as the read it was: version 1 keeps no review.)
The card is saved as the idea's eval.json through the app's idea store, which reads the status off it.
"""
from __future__ import annotations

import calendar
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

import judge as J

from . import api
from . import lines as L
from . import mc as MC
from . import propodds as PO
from . import rules as R

FILLS = """THE FILLS FORMAT. `--fills=-` reads ONE JSON object on stdin, `--fills=FILE` the same from a file:
    {"fills": [ <one object per live order of the eval, oldest first> ]}
A TRADE (an order that filled and is flat again). The first eight fields are required:
    entry_time, exit_time    when the entry filled and when the trade was flat again: ISO 8601 WITH its UTC offset
                             ("2026-10-06T09:45:02-04:00"), or epoch milliseconds (the desk journal's ts x 1000)
    side                     "long" | "short" (the desk's "Buy" | "Sell" are read too)
    size                     micros traded: a whole number from 1 (stage A is 1)
    entry_price, exit_price  the average fill prices
    net                      dollars after commissions, at that size
    exit_reason              how it ended: "tp" (target), "sl" (stop), "time" | "eod" | "flat" (the clock: ONE reason),
                             or any other word, compared as it is written
    entry_slip_ticks         the entry fill against its trigger, in ticks, worse = positive (the desk's slip_ticks).
                             Left out: give trigger_price and it is counted from the two prices. Neither: line 6.2 is
                             not read
    replay                   the tester's replay of the SAME trade, once it is known: {"entry_time": ..., "exit_reason":
                             ...} -- or {"no_trade": true} when the replay did not trade there. Left out: the trade is
                             not held against the test yet (line 6.1 waits for it)
    fixed                    a sentence: this trade's mismatch was a bug, and the bug IS FIXED (the count goes on)
    note                     free words, kept with the trade
AN ORDER THAT DID NOT TRADE where the test did: {"status": "missed" | "rejected"}, with entry_time, side and replay when
they are known. It is a mismatch (6.1) and, in stage A, the end of that stage A (6.2).
A field that is not listed is refused: a misspelt field would otherwise be a line that is silently not read.
AFTER A HARD ALARM (line 6.9), beside "fills": "replay_since_stop": [ {"exit_time": ..., "net": dollars, "size": micros}, ... ]
= the tester's replay of the strategy on the days since it was switched off, one object a trade. With it line 6.9 is READ:
the variant's own test-period trades and this replay, a micro, counted back from the replay's last day -- the last 5 and
the last 12 months each above $0, and the last 3 months a month above the long-run pace of the whole record.
"""
__doc__ += "\n" + FILLS

KEYS = ("status", "entry_time", "exit_time", "side", "size", "entry_price", "exit_price", "net", "exit_reason", "entry_slip_ticks", "trigger_price", "replay",
        "fixed", "note")
NEEDED = KEYS[1:9]                                  # what a trade must say
STATUS = ("filled", "missed", "rejected")
SIDES = {"long": 1, "buy": 1, "short": -1, "sell": -1}
ENDS = {"tp": "its target", "sl": "its stop", "time": "the clock", "eod": "the clock", "flat": "the clock"}      # one exit reason in the engine's words and the desk's
ZONES = ("carry on", "cut size", "the hard alarm")


def _usd(v) -> str:
    return L._n(float(v), unit="$")


# ================================================================ the tables of its own test history

def runs(rows: list, rng=None) -> np.ndarray:
    """THE MONTE CARLO of a variant's own test-period trades -> (runs x trades) the net of each trade of each run. rows =
    its ledger at the simulator's size (propodds.ledger). A run = WHOLE DAYS drawn with replacement from the days that
    traded, each day's trades in their own order, until the last read of line 6.4 (40 trades) is reached; runs and seed
    are montecarlo.json's (rng None = a fresh generator with the fixed seed: the same table every time)."""
    by: dict = {}
    for t in rows:
        by.setdefault(t["date"], []).append(t["net"])
    pool, most = list(by.values()), max(R.need("6.4")["after_trades"])
    idx = (MC.generator() if rng is None else rng).integers(0, len(pool), size=(R.template("montecarlo")["runs"], most))       # a day has a trade: `most` days are enough
    return np.array([[v for i in run for v in pool[i]][:most] for run in idx], np.float64)


def falls(paths) -> tuple:
    """(runs x steps) the net of each step of each run -> (the run's P&L so far, its DRAWDOWN so far): the largest fall of
    the P&L from its highest point so far, the start counting as a point. The last column = the worst drawdown of the
    whole run. (The table below reads it trade by trade; `bp.py mc` day by day: quick.py.)"""
    cum = np.cumsum(np.asarray(paths, np.float64), axis=1)
    return cum, np.maximum.accumulate(np.maximum.accumulate(np.maximum(cum, 0.0), axis=1) - cum, axis=1)


def table(paths: np.ndarray) -> dict:
    """THE TABLES off the runs -> {percentiles, runs, rows [{after, drawdown [...], pnl [...]}]}: after each read of line
    6.4 (10, 20, 30, 40 trades), the percentiles of montecarlo.json `eval_card` of the DRAWDOWN so far (the largest fall
    of a run's P&L from its highest point, the start included) and of the P&L FROM THE BAD SIDE (the P&L that this share
    of the runs beat: the 75th column is the 25th percentile of the P&L). Linear between ranks, as the app's own."""
    after, pct = R.need("6.4")["after_trades"], R.template("montecarlo")["eval_card"]["percentiles"]
    cum, dd = falls(paths)
    return {"percentiles": list(pct), "runs": int(len(cum)),
            "rows": [{"after": n, "drawdown": [float(v) for v in np.percentile(dd[:, n - 1], pct)],
                      "pnl": [float(v) for v in np.percentile(cum[:, n - 1], [100 - p for p in pct])]} for n in after]}


def zone(dd: float, row: dict) -> str:
    """LINE 6.4 for ONE read: where a live drawdown sits on its row of the table -- under the 75th percentile: carry on ·
    at the 75th: cut size · at the 95th: the hard alarm. No drawdown at all is never "at" a percentile."""
    need, pct = R.need("6.4"), R.template("montecarlo")["eval_card"]["percentiles"]
    cut, pause = (row["drawdown"][pct.index(need[k])] for k in ("cut_percentile", "pause_percentile"))
    return ZONES[0] if dd <= 0 or dd < cut else ZONES[1] if dd < pause else ZONES[2]


# ================================================================ the fills

def _ms(v, what: str) -> int:
    """A time of the fills -> epoch milliseconds (FILLS: ISO 8601 with its UTC offset, or epoch milliseconds)."""
    if PO._num(v):
        return int(v)
    try:
        t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        if t.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        raise J.Refuse(f"{what}: a time is ISO 8601 WITH its UTC offset (2026-10-06T09:45:02-04:00) or epoch milliseconds, not {v!r}") from None
    return int(round(t.timestamp() * 1000))


def _replay(v, who: str):
    """A fill's `replay` -> None (not known yet) | {"no_trade": True} | {entry_ms, reason}."""
    if v is None:
        return None
    if isinstance(v, dict) and v.get("no_trade") is True and set(v) == {"no_trade"}:
        return {"no_trade": True}
    if not (isinstance(v, dict) and set(v) == {"entry_time", "exit_reason"} and isinstance(v["exit_reason"], str) and v["exit_reason"].strip()):
        raise J.Refuse(f"{who}: replay is the tester's replay of the same trade, {{\"entry_time\": ..., \"exit_reason\": ...}}, or {{\"no_trade\": true}}")
    return {"entry_ms": _ms(v["entry_time"], f"{who}, replay entry_time"), "reason": v["exit_reason"].strip().lower()}


def read(raw, market: str) -> list:
    """THE LIVE ORDERS as the lines read them, from the object of FILLS. -> one row an order: {n (its number, from 1),
    status, entry_ms, exit_ms, side (+1 | -1), size, net, reason, slip (ticks | None), replay, fixed, note}. Refused: what
    is not in the format, with the fill and the field named."""
    if not isinstance(raw, dict) or not isinstance(raw.get("fills"), list):
        raise J.Refuse("the fills: ONE JSON object {\"fills\": [...]}, a list of the live orders of the eval, oldest first (bp.py eval-card --help has the format)")
    try:
        tick = float(R.template("costs")["contract"][market]["tick"])
    except KeyError:
        raise J.Refuse(f"market {market!r}: no tick size on file (costs.json)") from None
    out, last = [], None
    for n, f in enumerate(raw["fills"], 1):
        who = f"fill #{n}"
        if not isinstance(f, dict):
            raise J.Refuse(f"{who}: one object per live order ({', '.join(NEEDED)}, ...)")
        extra, status = sorted(set(f) - set(KEYS)), f.get("status", "filled")
        if extra:
            raise J.Refuse(f"{who}: {', '.join(extra)}: not a field of a fill (the fields: {', '.join(KEYS)})")
        if status not in STATUS:
            raise J.Refuse(f"{who}: status {status!r}: one of {', '.join(STATUS)}")
        row = {"n": n, "status": status, "entry_ms": None, "exit_ms": None, "side": None, "size": None, "net": None, "reason": None, "slip": None,
               "replay": _replay(f.get("replay"), who), "fixed": " ".join(str(f["fixed"]).split()) if f.get("fixed") else None, "note": f.get("note")}
        if status != "filled":
            row.update(entry_ms=None if f.get("entry_time") is None else _ms(f["entry_time"], f"{who}, entry_time"), side=SIDES.get(str(f.get("side")).lower()))
            out.append(row)
            continue
        gone = [k for k in NEEDED if f.get(k) is None]
        if gone:
            raise J.Refuse(f"{who}: a trade says its {', '.join(NEEDED)}; missing: {', '.join(gone)}")
        side = SIDES.get(str(f["side"]).lower())
        bad = ("side: long or short" if side is None else "size: micros, a whole number from 1" if type(f["size"]) is not int or f["size"] < 1 else
               next((f"{k}: a number" for k in ("entry_price", "exit_price", "net", "entry_slip_ticks", "trigger_price") if f.get(k) is not None and not PO._num(f[k])), "")
               or ("exit_reason: a word (tp, sl, time, eod, flat, ...)" if not (isinstance(f["exit_reason"], str) and f["exit_reason"].strip()) else ""))
        if bad:
            raise J.Refuse(f"{who}: {bad}")
        a, b = _ms(f["entry_time"], f"{who}, entry_time"), _ms(f["exit_time"], f"{who}, exit_time")
        if b < a or (last is not None and a < last):
            raise J.Refuse(f"{who}: " + ("its exit_time is before its entry_time" if b < a else "it was entered before the trade listed above it: the fills come oldest first"))
        last = a
        slip = f.get("entry_slip_ticks")
        if slip is None and f.get("trigger_price") is not None:
            slip = side * (f["entry_price"] - f["trigger_price"]) / tick
        row.update(entry_ms=a, exit_ms=b, side=side, size=f["size"], net=float(f["net"]), reason=f["exit_reason"].strip().lower(), slip=None if slip is None else float(slip))
        out.append(row)
    return out


def differs(f: dict):
    """LINE 6.1 for ONE live order: how it differs from the tester's replay of it -- '' = it equals it (the same entry
    time, within the seconds of rules.json 6.1, and the same exit reason), None = no replay on file yet. An order that
    did not trade always differs."""
    rp = f["replay"]
    if f["status"] != "filled":
        return f"the order was {f['status']}"
    if rp is None:
        return None
    if rp.get("no_trade"):
        return "the test did not trade there"
    late, why = (f["entry_ms"] - rp["entry_ms"]) / 1000.0, []
    if abs(late) > R.rule("6.1")["also"]["entry_within_s"]:
        why.append(f"entered {f'{abs(late):.3f}'.rstrip('0').rstrip('.')} s {'after' if late > 0 else 'before'} the test")
    if ENDS.get(f["reason"], f["reason"]) != ENDS.get(rp["reason"], rp["reason"]):
        said = lambda x: f"{ENDS[x]} ({x})" if x in ENDS else x  # noqa: E731
        why.append(f"ended by {said(f['reason'])}, the test by {said(rp['reason'])}")
    return "; ".join(why)


def close(orders: list) -> tuple:
    """LINE 6.2 on the orders of stage A -> (passed, the average entry slip in ticks | None, the orders that were missed or
    rejected, the trades without a slip on record). passed: False = an order did not trade, or the average is over the
    line's ticks; None = no trade yet, or a trade whose slip is not on record; else True."""
    need, op = R.need("6.2"), R.OPS[R.rule("6.2")["op"]]
    trades, lost = [f for f in orders if f["status"] == "filled"], [f for f in orders if f["status"] != "filled"]
    have = [f["slip"] for f in trades if f["slip"] is not None]
    avg, blind = (sum(have) / len(have) if have else None), len(trades) - len(have)
    bad = not op(len(lost), need["missed_or_rejected"]) or (avg is not None and not op(avg, need["entry_slip_ticks"]))
    return (False if bad else None if not trades or blind else True), avg, lost, blind


def stages(fills: list) -> dict:
    """STAGE A AND STAGE B of the orders (lines 6.2, 6.3): stage A = the orders up to and with the 5th CLEAN trade -- a
    trade that filled, at the stage A size (sizes.json: 1 micro), equal to the tester's replay -- provided line 6.2 holds
    on them; everything after it is stage B, at size. -> {a (orders), b (trades at size), clean, passed, slip = close(a)}"""
    need, micro, clean, cut = R.need("6.3")["clean_trades"], R.template("sizes")["stage_a"], 0, None
    for i, f in enumerate(fills):
        f["clean"] = f["status"] == "filled" and f["size"] == micro and differs(f) == ""
        clean += f["clean"]
        if clean >= need and close(fills[:i + 1])[0] is True:
            cut = i + 1
            break
    a = fills if cut is None else fills[:cut]
    return {"a": a, "b": [] if cut is None else [f for f in fills[cut:] if f["status"] == "filled"], "clean": sum(f["clean"] for f in a), "passed": cut is not None,
            "slip": close(a)}


# ================================================================ the card

def _back(d: dt.date, months: int) -> dt.date:
    """The same day `months` calendar months earlier (the month's last day when it has no such day)."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    return dt.date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def since_stop(raw) -> list:
    """`replay_since_stop` of the fills object -> [(the trade's New York date, its net A MICRO)], oldest first. Refused:
    what is not a list of {exit_time, net, size}."""
    if not isinstance(raw, list) or not raw or not all(isinstance(t, dict) and set(t) == {"exit_time", "net", "size"} for t in raw):
        raise J.Refuse("replay_since_stop: the tester's replay of the days since the strategy was switched off, a list of {\"exit_time\": ..., \"net\": dollars, "
                       "\"size\": micros}, one object a trade (bp.py eval-card --help)")
    out = []
    for i, t in enumerate(raw, 1):
        if not PO._num(t["net"]) or type(t["size"]) is not int or t["size"] < 1:
            raise J.Refuse(f"replay_since_stop, trade {i}: net is dollars and size is micros, a whole number from 1")
        day = dt.datetime.fromtimestamp(_ms(t["exit_time"], f"replay_since_stop, trade {i}, exit_time") / 1000, ZoneInfo("America/New_York")).date()
        out.append((day, float(t["net"]) / t["size"]))
    return sorted(out)


def recovery(history: list, since: list) -> dict:
    """LINE 6.9 READ: has the strategy recovered since its hard alarm? history = [(date, net a micro)] of the variant's own
    test-period trades, since = the same of the tester's replay since the stop. Counted back from the replay's last day,
    in calendar months: the last 5 months and the last 12 months each above $0, and the last 3 months a month above the
    long-run pace = the whole record a month. -> {passed (None: the record is shorter than the longest window), end,
    start, months, positive {months: net a micro}, pace {recent, long_run: a micro a month}}"""
    need = R.need("6.9")
    rows = sorted([*history, *since])
    end, start = max(d for d, _ in since), rows[0][0]
    net = lambda k: float(sum(v for d, v in rows if d > _back(end, k)))  # noqa: E731
    months = (end - start).days / 30.4375
    got = {"end": end.isoformat(), "start": start.isoformat(), "months": months, "positive": {str(k): net(k) for k in need["positive_months"]},
           "pace": {"recent": net(need["above_pace_months"]) / need["above_pace_months"], "long_run": float(sum(v for _, v in rows)) / months if months > 0 else 0.0}}
    whole = start <= _back(end, max(need["positive_months"]))
    return {**got, "passed": (all(v > 0 for v in got["positive"].values()) and got["pace"]["recent"] > got["pace"]["long_run"]) if whole else None}


def simmed(name, root=None, account=None) -> dict:
    """THE SIMULATOR'S RESULT THE CARD STANDS ON (sim/<account>.json of an idea whose test passed). account None = the
    account of the card on file, else the simulator result saved last. Refused: none on file (for that account)."""
    d = PO.proven(name, root)
    account = account or ((PO._json(d / "eval.json") or {}).get("account") or {}).get("id")
    files = sorted((d / "sim").glob("*.json"), key=lambda p: p.stat().st_mtime_ns)
    f = next((p for p in files if p.stem == account), None) if account else files[-1] if files else None
    s = PO._json(f) if f is not None else None
    if not (s and s.get("ok") is not False and isinstance(s.get("chosen"), dict) and isinstance(s.get("account"), dict)):
        raise J.Refuse(f"{name}: the simulator's result " + (f"for account {account} " if account else "") + "is not on file: the eval card stands on phase 5 -- the "
                       f"account, its size, the attempts and the fee budget (bp.py sim {name} --account=ID --attempts=N --fee-budget=USD)")
    return s


def card(name, fills=None, root=None, account=None) -> dict:
    """`bp.py eval-card <name> [--fills=-|FILE] [--account=ID]`: PHASE 6 (module docstring). fills None = the card before
    the first live trade; else the object of FILLS, and lines 6.1-6.5 are read on it. Saved as the idea's eval.json
    (every 6.x line in it; null = not judged yet, its text says why); the status follows from it.
    Beyond the agreed keys: idea, account, variant, size {stage_a, stage_b}, attempts, fee_budget, history {trades, days,
    avg_trade, avg_trade_micro}, table (+ variant, size), live {trades, orders, net, stage_a {trades, clean, passed,
    slip}, stage_b {trades, drawdown, pnl, avg_trade_micro, reads [{after, drawdown, cut, pause, zone}]}}, mismatches
    [{trade, why, fixed}], notes, fills (the orders that were read, as they were sent: kept with the card), lab.
    Refused: no simulator result on file; fills that are not in the format."""
    IS, sim = api.ideastore(), simmed(name, root, account)
    acct, ch = sim["account"], sim["chosen"]
    size, micro = int(ch["eval"]["size"]), R.template("sizes")["stage_a"]
    h, r = PO.handed(name, root), PO.app().load_rules(acct["id"])
    led = PO.ledger(PO.cell(h, ch["variant"]), size, r)
    tb = {**table(runs(led)), "variant": ch["variant"], "size": size}
    hist = {"trades": len(led), "days": len({t["date"] for t in led}), "avg_trade": float(np.mean([t["net"] for t in led]))}
    hist["avg_trade_micro"] = hist["avg_trade"] / size
    n2, n3, n4, n5 = (R.need(f"6.{i}") for i in range(2, 6))
    after, pct, within = n4["after_trades"], tb["percentiles"], R.rule("6.1")["also"]["entry_within_s"]
    half = n5["share_of_history"] * hist["avg_trade_micro"]
    orders = [] if fills is None else read(fills, h["market"])
    st = stages(orders)
    trades, B = [f for f in orders if f["status"] == "filled"], st["b"]
    # ---- 6.1 live equals the test
    diff = [(f, differs(f)) for f in orders]
    miss = [{"trade": f["n"], "why": why, "fixed": f["fixed"]} for f, why in diff if why]
    open_, blind = [m for m in miss if not m["fixed"]], sum(why is None for _, why in diff)
    rule1 = f"same entry time (within {within} s), same exit reason"
    rows = [L._row("6.1", None, None, None, f"not judged yet (no live trade): every day of the eval each live trade is held against the tester's replay of that day -- {rule1}. "
                                            "A mismatch is a bug: it is fixed before the count goes on") if not orders else
            L._row("6.1", False, len(open_), None, f"{len(open_)} of the {len(orders)} live orders do{'es' * (len(open_) == 1)} not equal the test ({rule1}): "
                   + "; ".join(f"#{m['trade']} {m['why']}" for m in open_) + ". A mismatch is a bug: it is fixed before the count goes on") if open_ else
            L._row("6.1", None, 0, None, f"not judged yet: {blind} of the {len(orders)} live orders ha{'s' if blind == 1 else 've'} no replay on file (the tester's replay of "
                                         f"that day); the other {len(orders) - blind} equal the test") if blind else
            L._row("6.1", True, 0, None, f"{len(orders) - len(miss)} live trades, each equal to the tester's replay of it ({rule1})"
                   + (f"; {len(miss)} mismatch{'es' * (len(miss) != 1)} that {'was' if len(miss) == 1 else 'were'} a bug, fixed" if miss else ""))]
    # ---- 6.2, 6.3 stage A
    ok2, avg, lost, noslip = st["slip"]
    a_trades = [f for f in st["a"] if f["status"] == "filled"]
    rule2 = f"average entry slip {n2['entry_slip_ticks']} ticks or less, no missed or rejected order"
    said2 = ("" if avg is None else f"average entry slip {avg:.2f} ticks over {len(a_trades) - noslip} trade{'s' * (len(a_trades) - noslip != 1)}") \
        + "".join(f"; {k} {w} order{'s' * (k != 1)}" for w in STATUS[1:] for k in [sum(f['status'] == w for f in lost)] if k)
    rows.append(L._row("6.2", None, None, n2, f"not judged yet (no live trade): stage A, the first days at {micro} micro -- {rule2}") if not orders else
                L._row("6.2", ok2, avg, n2, (f"not judged yet: {noslip} of stage A's {len(a_trades)} trades ha{'s' if noslip == 1 else 've'} no entry slip on record "
                                             f"(entry_slip_ticks, or trigger_price); " if ok2 is None else "") + f"stage A, {len(a_trades)} trades at {micro} micro: "
                       + said2.lstrip("; ") + f" (need {rule2})"))
    off = sum(f["status"] == "filled" and f["size"] != micro for f in st["a"])
    rows.append(L._row("6.3", True if st["passed"] else None, st["clean"], n3["clean_trades"],
                       (f"stage A is passed: {n3['clean_trades']} clean trades; from trade #{len(st['a']) + 1} on the size is {size} micros (the simulator's size)"
                        if st["passed"] else
                        f"not judged yet ({st['clean']} of {n3['clean_trades']} clean trades): stage A is passed after {n3['clean_trades']} clean trades -- filled, at {micro} "
                        f"micro, equal to the test -- then the size goes to {size} micros (the simulator's size)"
                        + ("; it waits for line 6.2 (the fills are not close to the test)" if st["clean"] >= n3["clean_trades"] else ""))
                       + (f"; {off} trade{'s' * (off != 1)} before it {'was' if off == 1 else 'were'} not at {micro} micro and do{'es' * (off == 1)} not count" if off else "")))
    # ---- 6.4, 6.5 stage B
    scaled = np.array([f["net"] * size / f["size"] for f in B], np.float64)
    cum = np.cumsum(scaled)
    dd = np.maximum.accumulate(np.maximum.accumulate(np.maximum(cum, 0.0)) - cum) if len(B) else cum
    by = {x["after"]: x for x in tb["rows"]}
    reads = [{"after": n, "drawdown": float(dd[n - 1]), "cut": by[n]["drawdown"][pct.index(n4["cut_percentile"])],
              "pause": by[n]["drawdown"][pct.index(n4["pause_percentile"])], "zone": zone(float(dd[n - 1]), by[n])} for n in after if len(B) >= n]
    rule4 = (f"stage B, read after {', '.join(str(n) for n in after[:-1])} and {after[-1]} trades at size against the drawdown table -- under the {n4['cut_percentile']}th "
             f"percentile: carry on · at the {n4['cut_percentile']}th: cut size · at the {n4['pause_percentile']}th: the hard alarm (line 6.9)")
    said4 = "; ".join(f"after {x['after']} trades {_usd(x['drawdown'])} ({n4['cut_percentile']}th {_usd(x['cut'])}, {n4['pause_percentile']}th {_usd(x['pause'])}): "
                      f"{x['zone']}" for x in reads)
    paused = any(x["zone"] == ZONES[2] for x in reads)
    rows.append(L._row("6.4", None, None, None, f"not judged yet ({len(B)} of {after[0]} trades at size): {rule4}") if not reads else
                L._row("6.4", False if paused else True if len(B) >= after[-1] else None, reads[-1]["drawdown"], {"cut": reads[-1]["cut"], "pause": reads[-1]["pause"]},
                       ("" if paused or len(B) >= after[-1] else f"not judged yet ({len(B)} of {after[-1]} trades at size): ") + f"the live drawdown at {size} micros, {said4}"))
    live5 = float(np.mean([f["net"] / f["size"] for f in B[:n5["after_trades"]]])) if len(B) >= n5["after_trades"] else None
    rule5 = f"at least half of the test's ({_usd(hist['avg_trade_micro'])} a micro a trade; half = {_usd(half)} a micro, {_usd(half * size)} at {size} micros)"
    rows.append(L._row("6.5", None, None, half, f"not judged yet ({len(B)} of {n5['after_trades']} trades at size): after {n5['after_trades']} trades the average trade "
                                                f"is {rule5}; otherwise the soft alarm (line 6.6)") if live5 is None else
                L._row("6.5", bool(R.OPS[R.rule("6.5")["op"]](live5, half)), live5, half,
                       f"after {n5['after_trades']} trades at size the average trade is {L._n(live5, half, '$')} a micro (need {rule5})"))
    # ---- 6.6 - 6.9 stated
    n9 = R.need("6.9")
    rule9 = (f"last {n9['positive_months'][0]} months positive · last {n9['positive_months'][1]} months positive · last {n9['above_pace_months']} months above "
             "its long-run pace")
    rows += [L._row("6.6", None, None, R.need("6.6"), "a rule to follow: the soft alarm is a review, not a switch-off by itself -- has this happened in the test history, "
                                                      "can it be explained, is it inside normal behaviour; three yes: carry on · otherwise: stop until it recovers (line 6.9)"),
             L._row("6.7", None, None, None, "a rule to follow: during the eval only the size may change, never the rule"),
             L._row("6.8", None, None, None, f"a rule to follow: a bust inside the drawdown table does not retire the strategy; running out of the {sim['attempts']} "
                                             f"attempt{'s' * (sim['attempts'] != 1)} of line 5.4 (total fee budget {PO.usd(sim['fee_budget'])}) does"),
             L._row("6.9", None, None, n9, "a rule to follow: the hard alarm switches the strategy off and no review turns it back on; a stop is not a deletion -- it "
                                           f"comes back when the tester's replay of the days since shows it has recovered: {rule9}")]
    rec = None
    if isinstance(fills, dict) and fills.get("replay_since_stop") is not None:      # line 6.9 READ on the tester's replay since the stop
        rec = recovery([(dt.date.fromisoformat(t["date"]), t["net"] / size) for t in led], since_stop(fills["replay_since_stop"]))
        a, b = (rec["positive"][str(k)] for k in n9["positive_months"])
        said9 = (f"the tester's replay since the stop, to {rec['end']} (with the variant's test-period trades: {rec['months']:.1f} months on record): last "
                 f"{n9['positive_months'][0]} months {_usd(a)} a micro, last {n9['positive_months'][1]} months {_usd(b)} a micro (need both above $0); last "
                 f"{n9['above_pace_months']} months {_usd(rec['pace']['recent'])} a micro a month against a long-run pace of {_usd(rec['pace']['long_run'])} (need above it)")
        rows[-1] = L._row("6.9", rec["passed"], rec["pace"]["recent"], n9, said9 if rec["passed"] is not None else
                          f"not judged: the record is {rec['months']:.1f} months long, shorter than the {max(n9['positive_months'])} months the line looks back over -- "
                          + said9, recovery=rec)
    live = {"trades": len(trades), "orders": len(orders) - len(trades), "net": float(sum(f["net"] for f in trades)),
            "stage_a": {"trades": len(a_trades), "clean": st["clean"], "passed": st["passed"], "slip": avg},
            "stage_b": {"trades": len(B), "drawdown": float(dd[-1]) if len(B) else 0.0, "pnl": float(cum[-1]) if len(B) else 0.0,
                        "avg_trade_micro": float(np.mean([f["net"] / f["size"] for f in B])) if B else None, "reads": reads}}
    mark = {x["line"]: x["passed"] for x in rows}
    failed5 = [x["line"] for x in sim.get("lines") or [] if x.get("passed") is False]
    notes = ([f"the simulator's line{'s' * (len(failed5) != 1)} {', '.join(failed5)} did not pass for this account: its odds are under one strategy's bar, and the law buys "
              "no eval on them (line 5.5)"] if failed5 else [])
    d = IS.idea_dir(name, root)
    col = lambda v: f"{_usd(v):>9s}"  # noqa: E731
    head = f"{'':<16s}" + "".join(f"{str(p) + 'th':>9s}" for p in pct)
    text = [f"EVAL CARD of {name} (phase 6) · {acct['label']} [{acct['id']}] · variant {ch['variant']} ({h['market']} {h['session']}, {h['bar']}-minute bars)",
            f"Written before the first eval (line 5.4): {sim['attempts']} attempt{'s' * (sim['attempts'] != 1)}, total fee budget {PO.usd(sim['fee_budget'])}. "
            f"Stage A: {micro} micro until {n3['clean_trades']} clean trades. Stage B: {size} micros, the simulator's size.",
            *[x["text"] for x in rows],
            f"DRAWDOWN TABLE of its own test history at {size} micros ({tb['runs']:,} runs of whole days drawn with replacement; a column = the share of the runs with a "
            "drawdown no larger than this):", head, *[f"{'after ' + str(x['after']) + ' trades':<16s}" + "".join(col(v) for v in x["drawdown"]) for x in tb["rows"]],
            "P&L of the same runs, from the bad side (a column = the share of the runs that made MORE than this):", head,
            *[f"{'after ' + str(x['after']) + ' trades':<16s}" + "".join(col(v) for v in x["pnl"]) for x in tb["rows"]],
            *([f"LIVE SO FAR: {len(trades)} trade{'s' * (len(trades) != 1)}"
               + (f" and {live['orders']} order{'s' * (live['orders'] != 1)} that did not trade" if live["orders"] else "")
               + f", net {_usd(live['net'])} · stage A {len(a_trades)} trades, {st['clean']} clean · at size {len(B)} trades"
               + (f", P&L {_usd(live['stage_b']['pnl'])} and drawdown {_usd(live['stage_b']['drawdown'])} at {size} micros" if B else "")] if orders else []),
            *[f"MISMATCH #{m['trade']}: {m['why']}" + (f" -- FIXED: {m['fixed']}" if m["fixed"] else "") for m in miss],
            *[f"NOTE: {x}." for x in notes]]
    res = api.result("eval-card", name, lines=rows, saved=[str(d / "eval.json")], idea=name, account=acct, variant=ch["variant"], size={"stage_a": micro, "stage_b": size},
                     attempts=sim["attempts"], fee_budget=sim["fee_budget"], history=hist, table=tb, live=live, mismatches=miss, notes=notes,
                     fills=[] if fills is None else fills["fills"])
    send = f"bp.py eval-card {name} --fills=- (the format: bp.py eval-card --help)"
    res["next"] = (
        f"Buy the first eval and trade stage A at {micro} micro; after each trading day send the live fills with the tester's replay of that day: {send}" if not orders else
        "THE HARD ALARM stands on this card (line 6.4), and the tester's replay since shows the recovery of line 6.9: the strategy may come back -- as a new "
        "attempt of its eval, with its own card" if mark["6.4"] is False and rec is not None and rec["passed"] is True else
        f"THE HARD ALARM (line 6.4: the drawdown is at the {n4['pause_percentile']}th percentile): SWITCH THE STRATEGY OFF. No review turns it back on; it comes "
        f"back when the tester's replay of the days since shows it has recovered (line 6.9: {rule9}"
        + (")" if rec is None else "; the replay sent does not show it yet)") if mark["6.4"] is False else
        "THE SOFT ALARM (line 6.5: the average trade is under half of the test's): a review, not a switch-off by itself (line 6.6) -- has this happened in the test "
        "history, can it be explained, is it inside normal behaviour; three yes: carry on · otherwise: stop until it recovers (line 6.9)" if mark["6.5"] is False else
        f"The fills are not close to the test (line 6.2): stay at {micro} micro, find out why, and start stage A again -- send the fills from the restart on"
        if mark["6.2"] is False else
        "A mismatch is a bug: fix it before the count goes on, then send that fill with `fixed` (what the bug was)" if mark["6.1"] is False else
        f"{blind} live order{'s' * (blind != 1)} ha{'s' if blind == 1 else 've'} no replay on file: replay those days in the tester and send the fills with `replay` "
        "(line 6.1 is read on every trade)" if blind else
        f"Every line that is read on live trades is true: {name} is PROVEN LIVE" if all(mark[k] is True for k in IS.LIVE_LINES) else
        f"Stage A goes on at {micro} micro ({st['clean']} of {n3['clean_trades']} clean trades): {send}" if not st["passed"] else
        f"CUT THE SIZE (line 6.4: the drawdown is at the {n4['cut_percentile']}th percentile) and carry on; the next read is after "
        f"{next((n for n in after if n > len(B)), after[-1])} trades at size" if reads and reads[-1]["zone"] == ZONES[1] and len(B) < after[-1] else
        f"Stage A is passed: trade {size} micros, the simulator's size; the drawdown is read after {', '.join(str(n) for n in after)} trades at size ({len(B)} so far): {send}")
    res["text"] = "\n".join(text)
    for _ in range(2):                              # the status is read off the saved card: saved, read, and saved with it
        res["status"] = IS.status(name, root)
        try:
            IS.write_eval(name, res, root)
        except ValueError as e:
            raise J.Refuse(str(e)) from None
    res["status"] = IS.status(name, root)
    from . import records                           # (the idea's copy in the Lab is the record's to bring up to date)
    res["lab"], lab, _ = records._lab(name, root)
    res["text"] = "\n".join([*text, *lab])
    return res
