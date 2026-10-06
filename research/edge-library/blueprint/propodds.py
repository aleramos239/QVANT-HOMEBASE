"""propodds.py -- PHASE 5, BEFORE THE EVAL IS BOUGHT (toolkit plan, step 9): `bp.py sim <name> --account=ID --attempts=N
--fee-budget=USD`. "Is the account worth buying?" -- the app's prop simulator (homebase/backtest/propsim: its rule files,
its walks, its "live is worse" rows) on the TEST-PERIOD trades of an idea that passed its out-of-sample test.

THIS SIMULATOR COUNTS OPEN LOSSES. The firm's drawdown is breached by an open loss, not only by a closed day (owner,
2026-10-02): a day whose WORST POINT -- where the account stood at the day's start, minus the day's worst open loss -- is at
or under the floor in force busts the account, whatever the day closes at. The tester page's own Monte Carlo and prop tile
use the END-OF-DAY rule (a bust only when a day CLOSES at or under the floor): theirs are the friendlier odds, and every
result here says which rule it is (LABEL). With an open loss of zero the walks ARE the app's, path for path (locked by
tests/test_blueprint_propodds.py against propsim.run_eval and run_funded).

WHAT IS RUN, for one account (a rule file of the app):
  THE SURVIVING VARIANTS (BLUEPRINT.md section 7) = the locked variants profitable on build, on the test and with worse
        fills: the lock's own survivors (frozen before the read: they make money on build and on build with worse fills)
        that also make money on the test days and on the test days with worse fills. Each is read at every pre-set size
        step; the account's stop and target are chosen among them here.
  A SIZE (sizes.json, in micros; a step above the account's own maximum is left out -- for the funded account that is the
        size its scaling plan starts at) = the library's micro cost model (library.sized, one size for every trade).
  A DAY  = a session day of the test range, as the read's own store lists them (`calendar`: the days that were replayed;
        a day without a trade is a day of $0 -- the app's weekday grid without its holidays), after the account's soft
        daily loss limit (propsim.limit_trades), + the day's worst open loss (library._worst_open on each trade's MAE
        and commission; never more than the daily limit, where there is one).
  THE PLAIN ROW and THE "LIVE IS WORSE" ROW (line 5.2: propsim.degrade with win rate -5 points and winners -15 %; a day it
        turns into a loss takes the open loss of the losing day it was drawn from).
  THE ODDS: the app's number of paths and seed, whole days drawn with replacement; the eval is walked for the days of line
        5.3 (pass within 10 trading days), the funded account from a flat start for its days (the MAXIMUM payout within
        20). Every size, both rows and every variant of a pool are raced on the SAME paths. The interval is Wilson's 95 %:
        Monte Carlo noise only -- 15 months of trades and days drawn independently are the larger doubt (the app's caveat).
THE LINES
  5.1  both phases run, each at its own best size from the pre-set steps: the highest odds on the "live is worse" row --
       and, between two sizes whose confidence intervals overlap, the smaller
  5.2  both are read on the "live is worse" row; the plain row is shown beside it
  5.3  the owner's bar on that row, at each phase's best size: eval 60 % or more, maximum payout 75 % or more
  5.4  the attempts and the total fee budget, written down: the owner's numbers, inputs -- refused when one is missing
The variant read for the account is the surviving variant NEAREST THE BAR ON ITS WEAKER PHASE: the one with the largest
margin = min(eval odds / the eval's bar, payout odds / the payout's bar). The result also says how the middle variant
reads, because the best of many is flattered.

THE TEST-PERIOD TRADES are where the one read left them (oos.py, runner.run_test); nothing is run and no tape is opened:
    lock.json   home {market, session, bar}, variants (the locked list), survivors, test_range, hash
    test.json   lock (the hash of the read's lock), stores [{key, kind, path}]: kind "unit" | "filter" = the locked variants
                on the test days, "worse" = the same with worse fills
Both stores pass the seal of the test days (runner.guard_test: the frozen range, this lock's read) before a trade is read.
Refused: an idea whose out-of-sample test is not on file or did not pass (the app's idea store reads that off the saved
results), a test result or a lock that does not name those stores, a store that is not of this lock's read, no surviving
variant.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

import judge as J
import library as LB

from . import api
from . import lines as L
from . import rules as R
from . import runner as RUN

PASS, BUST = 1, 2                                   # an eval walk's verdict (0 = neither inside its days)
PHASES = (("eval", "EVAL: pass"), ("payout", "FUNDED: maximum payout"))
RULE = "open losses count"
LABEL = ("THIS SIMULATOR COUNTS OPEN LOSSES: a day whose worst open point is at or under the drawdown floor busts the account, whatever it closes at. "
         "The tester page's own Monte Carlo and prop tile use the END-OF-DAY rule: their odds are the friendlier ones, and the two are not the same number.")


def app():
    """The app's prop simulator, homebase/backtest/propsim (the rule files, the weekday grid, the soft daily loss limit;
    its `engine` = the walks, degrade, the Wilson interval), imported from the repo by its path like the idea store: read,
    never changed, and no bytecode is written into homebase/."""
    api.ideastore()
    from homebase.backtest import propsim
    return propsim


def _json(path):
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _pc(v) -> str:
    return f"{100 * v:.1f} %"


def usd(v) -> str:
    """Dollars as they are written: whole when they are whole ($345), else with cents."""
    return ("-" if v < 0 else "") + (f"${abs(v):,.0f}" if float(v).is_integer() else f"${abs(v):,.2f}")


def _block(c: dict) -> str:
    """One phase of a table row: the plain row's odds, the "live is worse" row's with its interval, its busts."""
    w = c["worse"]
    mid = f"{_pc(w['p'])} ({100 * w['ci'][0]:.1f}-{100 * w['ci'][1]:.1f})"
    return f"{_pc(c['plain']['p']):>7s}  {mid:<29s}  {_pc(w['bust']):>7s}"


# ================================================================ a size, a day

def sized(x: dict, size: int) -> dict:
    """A variant's trades (a cell's packed arrays: 1 contract after costs) at `size` MICROS, by the library's micro cost
    model -- library.sized with ONE size for every trade: net = size x (the 1-contract gross / 10 - the micro's
    commission); the worst open point (MAE) scales alike. -> {date, entry_ms, exit_ms, net, mae, cost (a trade's commission)}"""
    div, ent = R.template("sizes")["micros_per_contract"], np.asarray(x["entry_ms"], np.int64)
    return {"date": np.asarray(x["date"], np.int64), "entry_ms": ent, "exit_ms": ent + np.asarray(x["dur_s"], np.int64) * 1000,
            "net": size * ((np.asarray(x["net"], np.float64) + LB.COMM_RT) / div - LB.MICRO_RT_USD),
            "mae": size * np.abs(np.asarray(x["mae"], np.float64)) / div, "cost": size * LB.MICRO_RT_USD}


def ledger(x: dict, size: int, r: dict) -> list:
    """The trades at a size as the app's ledger rows ({date, net, mae_usd, commission, entry_ms, exit_ms}, by exit time: the
    engine's order), AFTER THE ACCOUNT'S SOFT DAILY LOSS LIMIT (propsim.limit_trades: the trade whose worst moment takes the
    day to the limit is closed at the limit and the day's later trades are dropped; a rule file without one: unchanged)."""
    z = sized(x, size)
    return app().limit_trades([{"date": dt.date.fromordinal(int(z["date"][i])).isoformat(), "net": float(z["net"][i]), "mae_usd": float(z["mae"][i]),
                                "commission": z["cost"], "entry_ms": int(z["entry_ms"][i]), "exit_ms": int(z["exit_ms"][i])}
                               for i in np.lexsort((z["entry_ms"], z["exit_ms"], z["date"]))], r)


def days(rows: list, r: dict, calendar=()) -> tuple:
    """THE DAY POOL of a ledger -> (net, traded, open, dates), one entry a day: the session days of `calendar` (the days
    the read of the test days replayed, as its store lists them) -- a day without a trade = $0, and a date that traded is
    never dropped. On a calendar of every weekday this IS the app's weekday grid (propsim.weekday_grid). open = the day's
    WORST OPEN LOSS in dollars (library._worst_open: at each entry, what the day has realised minus the open trade's MAE
    and commission), never more than the account's daily loss limit: a day that reached the limit was closed there."""
    by: dict = {}
    for t in rows:
        by.setdefault(t["date"], []).append(t)
    dates, dll = sorted(set(calendar) | set(by)), app().engine._dll(r)
    worst = [LB._worst_open([(t["entry_ms"], t["exit_ms"], t["net"], t["mae_usd"] + t["commission"]) for t in by.get(d, ())]) + 0.0 for d in dates]
    return (np.array([sum((t["net"] for t in by.get(d, ())), 0.0) for d in dates]), np.array([d in by for d in dates]),
            np.array([min(w, dll) if dll else w for w in worst]), dates)


def worse(pnl, traded, open_) -> tuple:
    """THE "LIVE IS WORSE" ROW of a day pool (line 5.2) -> (net, open): the app's own degradation (propsim.degrade, its
    fixed seed) with the line's numbers -- winning days 15 % smaller, 5 points of the trading days turned from winners
    into losers drawn from the losing days. A day turned into a loss takes the OPEN LOSS of the losing day it was drawn
    from (the first with that P&L; with no losing day to draw from: at least the loss itself). A winner keeps its own."""
    need, pnl, open_ = R.need("5.2"), np.asarray(pnl, np.float64), np.asarray(open_, np.float64)
    out = np.array(app().engine.degrade(pnl.tolist(), [bool(t) for t in traded], need["win_rate"], -need["winners"]))
    opn = open_.copy()
    for i in np.flatnonzero((pnl > 0) & (out <= 0)):
        src = np.flatnonzero(pnl == out[i])
        opn[i] = open_[src[0]] if len(src) else max(open_[i], -out[i])
    return out, opn


# ================================================================ the walks: the app's, + the open-loss rule

@lru_cache(maxsize=8)
def draws(days_: int, paths: int, horizon: int, seed: int) -> np.ndarray:
    """(paths x horizon) day numbers: whole days drawn with replacement from a pool of `days_` days, as the app draws them
    (independently). ONE fixed matrix per pool length: every size, both rows and every variant are raced on the same
    paths, so two rows differ by what is traded and never by the draw (the app's degradation rows share a stream too)."""
    idx = np.random.default_rng(seed).integers(0, days_, size=(paths, horizon))
    idx.setflags(write=False)
    return idx


def _start(pnl, r: dict) -> tuple:
    n, dll = len(pnl), app().engine._dll(r)
    return np.zeros(n), np.zeros(n), np.full(n, -float(r["trailing_mll"])), np.ones(n, bool), (lambda p: np.maximum(p, -dll)) if dll else (lambda p: p)


def _floor(up, profit, peak, floor, r: dict) -> tuple:
    """propsim._floor where the end-of-day peak rose: the trailing line, locked at `lock_floor` from `lock_at` on."""
    peak = np.where(up, profit, peak)
    return peak, np.where(up, np.where(peak >= r["lock_at"], float(r["lock_floor"]), peak - r["trailing_mll"]), floor)


def eval_walk(pnl, traded, open_, r: dict) -> dict:
    """propsim.run_eval for many paths at once, WITH THE OPEN-LOSS RULE. pnl, traded, open_ = (paths x days): each day's
    P&L, whether it traded, its worst open loss. A day is walked as the app walks it (the daily cap, the bust at or under
    the floor, the floor trailing the end-of-day peak and locking, the pass with its minimum days and consistency) -- but
    FIRST the open-loss rule: start-of-day profit minus the day's worst open loss at or under the floor = a bust that
    day. -> {outcome (PASS | BUST | 0 = neither inside the days), day (of the verdict; the days walked), trade_days}"""
    pnl, traded, open_ = np.asarray(pnl, np.float64), np.asarray(traded, bool), np.asarray(open_, np.float64)
    profit, peak, floor, live, cap = _start(pnl, r)
    big, tdays, out, day, cons = np.zeros(len(pnl)), np.zeros(len(pnl), np.int64), np.zeros(len(pnl), np.int8), np.zeros(len(pnl), np.int64), r.get("consistency")
    for d in range(pnl.shape[1]):
        p, o = cap(pnl[:, d]), open_[:, d]
        day += live
        tdays += live & traded[:, d]
        hit = live & (o > 0) & (profit - o <= floor)                     # THE OPEN-LOSS RULE
        go = live & ~hit
        profit = np.where(go, profit + p, profit)
        big = np.where(go, np.maximum(big, p), big)
        bust = go & (profit <= floor)
        ok = go & ~bust
        peak, floor = _floor(ok & (profit > peak), profit, peak, floor, r)
        won = ok & (profit >= r["eval_target"]) & (tdays >= r["eval_min_days"]) & (True if cons is None else big <= cons * profit)
        out[hit | bust], out[won] = BUST, PASS
        live = ok & ~won
    return {"outcome": out, "day": day, "trade_days": tdays}


def funded_walk(pnl, open_, r: dict) -> dict:
    """propsim.run_funded for many paths at once (a funded account from a flat start, the first payout only), WITH THE
    OPEN-LOSS RULE as in eval_walk. -> {payout_at, max_payout_at, bust_at (the day; 0 = not reached), cheque (NaN = none)}"""
    pnl, open_ = np.asarray(pnl, np.float64), np.asarray(open_, np.float64)
    profit, peak, floor, live, cap = _start(pnl, r)
    wins, cheque = np.zeros(len(pnl), np.int64), np.full(len(pnl), np.nan)
    pay, top, bust_at = (np.zeros(len(pnl), np.int64) for _ in range(3))
    for d in range(pnl.shape[1]):
        p, o = cap(pnl[:, d]), open_[:, d]
        hit = live & (o > 0) & (profit - o <= floor)                     # THE OPEN-LOSS RULE
        go = live & ~hit
        profit = np.where(go, profit + p, profit)
        wins += go & (p >= r["win_day"])
        bust = go & (profit <= floor)
        ok = go & ~bust
        peak, floor = _floor(ok & (profit > peak), profit, peak, floor, r)
        due = ok & (wins >= r["payout_win_days"])
        first, most = due & (pay == 0) & (profit > 0), due & (profit >= r["max_payout_profit"])
        pay[first], top[most], bust_at[hit | bust] = d + 1, d + 1, d + 1
        cheque = np.where(first, np.minimum(r["payout_share"] * profit, r["payout_cap"]), cheque)
        live = ok & ~most
    return {"payout_at": pay, "max_payout_at": top, "bust_at": bust_at, "cheque": cheque}


def odds(pnl, traded, open_, r: dict, paths=None, seed=None, funded: bool = True) -> dict:
    """THE ODDS of one day pool (one size, one row): {eval: {p = pass within the eval's days, ci, bust}, payout: {p = the
    MAXIMUM payout within the funded account's days, ci, bust}}. The days are line 5.3's; paths and seed default to the
    app's own (propsim.N_PATHS, SEED); ci = its Wilson interval (95 %: Monte Carlo noise, not the doubt about the days).
    funded False = the funded account is not walked (a size it may not trade)."""
    PS, need = app(), R.need("5.3")
    n, de, dp = int(paths or PS.N_PATHS), need["eval"]["days"], need["payout"]["days"]
    idx = draws(len(pnl), n, max(de, dp), PS.SEED if seed is None else int(seed))
    P, T, O = np.asarray(pnl, np.float64)[idx], np.asarray(traded, bool)[idx], np.asarray(open_, np.float64)[idx]

    def said(hit, bust) -> dict:
        return {"p": int(hit.sum()) / n, "ci": list(PS.engine.wilson_ci(int(hit.sum()), n)), "bust": int(bust.sum()) / n}

    e = eval_walk(P[:, :de], T[:, :de], O[:, :de], r)
    f = funded_walk(P[:, :dp], O[:, :dp], r) if funded else None
    return {"eval": said(e["outcome"] == PASS, e["outcome"] == BUST), "payout": said(f["max_payout_at"] > 0, f["bust_at"] > 0) if f else None}


# ================================================================ the table of one variant, its best sizes

def steps(r: dict) -> tuple:
    """The pre-set size steps an account may trade (sizes.json; a step above the account's own maximum is left out) ->
    (the eval's, the funded account's). The eval: up to the account's contract limit. The funded account: up to the size
    its SCALING PLAN starts at, where it has one -- a size the plan allows only after a profit is not a size the account
    can be run at from its first day (the plan's later steps are not simulated)."""
    all_ = R.template("sizes")["steps"]
    cap = r.get("cap_micros") or max(all_)
    return [s for s in all_ if s <= cap], [s for s in all_ if s <= min(cap, (r.get("scaling_micros") or {}).get("start") or cap)]


def table(x: dict, r: dict, calendar=(), paths=None, seed=None) -> list:
    """ONE VARIANT, size by size: [{size, eval: {plain, worse}, payout: {plain, worse} | None (a step the funded account
    may not trade), days, traded (the pool: its days, and those with a trade), flipped (the winning days the "live is worse"
    row turned into losing days)}], each cell = odds()."""
    ev, fu = steps(r)
    out = []
    for size in ev:
        net, traded, opn, _ = days(ledger(x, size, r), r, calendar)
        wnet, wopn = worse(net, traded, opn)
        plain, bad = odds(net, traded, opn, r, paths, seed, size in fu), odds(wnet, traded, wopn, r, paths, seed, size in fu)
        out.append({"size": size, "eval": {"plain": plain["eval"], "worse": bad["eval"]}, "payout": {"plain": plain["payout"], "worse": bad["payout"]} if size in fu else None,
                    "days": len(net), "traded": int(traded.sum()), "flipped": int(((net > 0) & (wnet <= 0)).sum())})
    return out


def best(rows: list, phase: str) -> dict:
    """LINE 5.1: a phase's best size from the pre-set steps, read on the "live is worse" row -- the highest odds; and,
    BETWEEN TWO SIZES WHOSE CONFIDENCE INTERVALS OVERLAP, THE SMALLER: the smallest step whose interval reaches the best
    one's. rows = a variant's table, smallest size first; a step the phase may not trade is not read."""
    have = [x for x in rows if x[phase]]
    lo = max(have, key=lambda x: x[phase]["worse"]["p"])[phase]["worse"]["ci"][0]
    return next(x for x in have if x[phase]["worse"]["ci"][1] >= lo)


def bar(ch: dict) -> bool:
    """LINE 5.3 on a variant's two best sizes ({eval: {p}, payout: {p}}): each phase's odds held against its own number
    with the line's own comparison."""
    need, op = R.need("5.3"), R.OPS[R.rule("5.3")["op"]]
    return bool(op(ch["eval"]["p"], need["eval"]["odds"]) and op(ch["payout"]["p"], need["payout"]["odds"]))


def read(vid: str, rows: list) -> dict:
    """A variant as the account reads it: its best size of each phase with the odds there ("live is worse": p, ci; the
    plain row's p beside it) and its MARGIN = min(eval odds / the eval's bar, payout odds / the payout's bar) -- 1 or more
    = it meets the owner's bar on both phases."""
    need = R.need("5.3")
    out = {"id": vid}
    for phase, _ in PHASES:
        b = best(rows, phase)
        out[phase] = {"size": b["size"], "p": b[phase]["worse"]["p"], "ci": b[phase]["worse"]["ci"], "bust": b[phase]["worse"]["bust"], "plain": b[phase]["plain"]["p"]}
    return {**out, "margin": min(out[p]["p"] / need[p]["odds"] for p, _ in PHASES)}


# ================================================================ what the test hands over

def proven(name, root=None) -> Path:
    """The idea's folder -- with its out-of-sample test ON FILE AND PASSED, or refused. The app's idea store says so, off
    the saved results alone (homebase/ideastore.py: proven on history = a lead whose test.json passed every 4.x line)."""
    IS = api.ideastore()
    try:
        d = IS.idea_dir(name, root)
    except ValueError as e:
        raise J.Refuse(str(e)) from None
    if not d.is_dir():
        raise J.Refuse(f"no idea {name} in {IS.ideas_root(root)}")
    st = IS.status(name, root)
    if st not in ("proven_on_history", "proven_live"):
        raise J.Refuse(f"{name} is {st.replace('_', ' ').upper()}: " + (
            "its out-of-sample test on file did not pass (or is not finished) -- the prop simulator is run on the test-period trades of an idea that is PROVEN ON "
            "HISTORY, and of no other"
            if (d / "test.json").is_file() else
            f"its out-of-sample test is not on file -- phase 5 is run on the test-period trades of a PASSED test (the phases before it come first: bp.py test {name})"))
    return d


def handed(name, root=None) -> dict:
    """WHAT THE FREEZE AND THE ONE READ LEAVE for phase 5 (module docstring) -> {market, session, bar, lock (its hash),
    store (the locked variants on the test days, as the judge reads a store), where, span (start, end), calendar (the
    session days the read replayed), variants [{id, test, worse (its net on the test days, plain and with worse fills),
    frozen (a survivor of the lock: it makes money on build and on build with worse fills)}], survivors (the ids
    profitable on all of them)}. Refused: module docstring."""
    d = proven(name, root)
    lock, test = _json(d / "lock.json") or {}, _json(d / "test.json") or {}
    try:
        h, rng = lock["home"], lock["test_range"][lock["home"]["market"]]
        ids, frozen = [str(v) for v in lock["variants"]], {str(v) for v in lock["survivors"]}
        at = {("worse" if s["kind"] == "worse" else "table"): Path(s["path"]) for s in test["stores"] if s["kind"] in ("unit", "filter", "worse")}
        whole = bool(ids) and all(isinstance(h[k], str) and h[k] for k in ("market", "session", "bar")) and set(at) == {"table", "worse"} and bool(lock["hash"])
        span = (str(rng["start"]), str(rng["end"]))
    except (KeyError, TypeError):
        whole = False
    if not whole:
        raise J.Refuse(f"{name}: its lock and its test result do not say where the test-period trades are: lock.json = home {{market, session, bar}}, variants, "
                       "survivors, test_range, hash; test.json = stores [{key, kind, path}] with the locked variants on the test days (kind unit or filter) and "
                       "the same with worse fills (kind worse) -- as bp.py lock and bp.py test save them")
    if test.get("lock") != lock["hash"]:
        raise J.Refuse(f"{name}: the test result on file is of lock {test.get('lock') or '?'}, the lock on file is {lock['hash']}: phase 5 reads the read of ITS lock")
    opened = {}
    for which, p in at.items():
        meta, where = _json(p / "run.json"), f"{p.parent.name}/{p.name}"
        if meta is None or not (p / "cells.npz").exists():
            raise J.Refuse(f"{name}: no store {p} (run.json and cells.npz): the test-period trades of its read are not there")
        RUN.guard_test(meta, where, *span, lock["hash"])
        opened[which] = (J.store({"dir": p.parent, "key": p.name}), meta, where)
    (st, meta, where), (wst, _, wwhere) = opened["table"], opened["worse"]
    gone = next(((v, w) for s, w in ((st, where), (wst, wwhere)) for v in ids if v not in s["_idx"]), None)
    cal = meta.get("calendar")
    if gone or not (isinstance(cal, list) and cal):
        raise J.Refuse(f"{name}: store {gone[1]} lacks the locked variant {gone[0]}: it is not the read of this lock" if gone else
                       f"{name}: store {where} does not say which session days were replayed (calendar): it is not read")
    net = lambda s, v: float(J.cellx(s, v, h["session"])["net"].sum())  # noqa: E731
    rows = [{"id": v, "test": net(st, v), "worse": net(wst, v), "frozen": v in frozen} for v in ids]
    return {"market": h["market"], "session": h["session"], "bar": str(h["bar"]), "lock": lock["hash"], "store": st, "where": where, "span": span,
            "calendar": [str(x) for x in cal], "variants": rows,
            "survivors": [v["id"] for v in rows if v["frozen"] and L._profitable(v["test"]) and L._profitable(v["worse"])]}


def cell(h: dict, vid: str) -> dict:
    """The test-period trades of one variant in the home session (the judge's cell of the handed store), or refused."""
    try:
        x = J.cellx(h["store"], vid, h["session"])
    except KeyError:
        raise J.Refuse(f"store {h['where']} has no variant {vid}: it is not the home table the test handed over") from None
    if not len(x["net"]):
        raise J.Refuse(f"store {h['where']}: variant {vid} has no trade in the {h['session']} session")
    return x


# ================================================================ the command

def sim(name, account, attempts, fee_budget, root=None, paths=None, seed=None) -> dict:
    """`bp.py sim <name> --account=ID --attempts=N --fee-budget=USD`: PHASE 5 for one account (module docstring). Prints
    the table of the variant read for the account -- size by size, the odds of passing the eval within 10 trading days
    and of the maximum payout within 20, on the plain row and on the "live is worse" row -- and lines 5.1-5.4; saves the
    result as the idea's sim/<account>.json through the app's idea store (the eval card stands on it).
    Beyond the agreed keys: idea, account {id, name, label, confirmed}, attempts, fee_budget, rule, label, paths, seed,
    lock, range, pool, days, locked, survivors, variants [each surviving variant: read()], middle, meeting, chosen
    {variant, eval, payout, margin}, table, caveat, lab. paths / seed = the Monte Carlo's (tests; default: the app's own).
    Refused, with nothing written: a missing or unreadable attempts / fee budget (line 5.4), an account the app has no
    rule file for, an idea whose test is not on file and passed, whatever handed() and cell() refuse."""
    if type(attempts) is not int or attempts < 1:
        raise J.Refuse("the attempts are the owner's number and are written down before the first eval (line 5.4): --attempts=N, a whole number from 1 "
                       "(how many evals he will buy at most)")
    if not _num(fee_budget) or fee_budget < 0:
        raise J.Refuse("the total fee budget is the owner's number and is written down before the first eval (line 5.4): --fee-budget=USD, 0 or more")
    PS = app()
    if not isinstance(account, str) or not account:
        raise J.Refuse(f"sim needs the account in question: --account=ID, a rule file of the app's prop simulator ({', '.join(x['id'] for x in PS.list_rules())})")
    try:
        r = PS.load_rules(account)
    except ValueError:
        raise J.Refuse(f"account {account!r}: the app's prop simulator has no such rule file (it has {', '.join(x['id'] for x in PS.list_rules())})") from None
    IS, h, need = api.ideastore(), handed(name, root), R.need("5.3")
    if not h["survivors"]:
        raise J.Refuse(f"{name}: no variant of the {len(h['variants'])} locked is profitable on build, on the test and with worse fills: there is no surviving "
                       "variant to size (BLUEPRINT.md section 7)")
    tables = {v: table(cell(h, v), r, h["calendar"], paths, seed) for v in h["survivors"]}
    reads = [read(v, rows) for v, rows in tables.items()]
    ch = max(reads, key=lambda v: v["margin"])                           # ties: the first in the table's order
    mid = sorted(reads, key=lambda v: v["margin"])[(len(reads) - 1) // 2]
    rows, n = tables[ch["id"]], int(paths or PS.N_PATHS)
    label = r.get("name") if r.get("confirmed") is not False else f"{r.get('name')} · unconfirmed rules"
    at = next(x for x in rows if x["size"] == ch["eval"]["size"])
    once = 1.0 - (1.0 - ch["eval"]["p"]) ** attempts
    said = {p: f"{_pc(ch[p]['p'])} (need {L._pc(need[p]['odds'])} or more)" for p, _ in PHASES}
    lines = [
        L._row("5.1", True, {p: ch[p]["size"] for p, _ in PHASES}, None,
               f"both phases run, each at its own best size of the pre-set steps: the eval at {ch['eval']['size']} micros ({_pc(ch['eval']['p'])} to pass within "
               f"{need['eval']['days']} trading days), the funded account at {ch['payout']['size']} micros ({_pc(ch['payout']['p'])} for the maximum payout within "
               f"{need['payout']['days']})"),
        L._row("5.2", True, None, R.need("5.2"),
               f"both are read on the \"live is worse\" row: win rate {100 * R.need('5.2')['win_rate']:g} points ({at['flipped']} of the {at['traded']} trading days "
               f"turned from a winning day into a losing one) and winners {100 * R.need('5.2')['winners']:g} %; the plain row reads {_pc(ch['eval']['plain'])} and "
               f"{_pc(ch['payout']['plain'])}"),
        L._row("5.3", bar(ch), {p: ch[p]["p"] for p, _ in PHASES}, need,
               f"eval pass within {need['eval']['days']} trading days {said['eval']}; maximum payout within {need['payout']['days']} trading days {said['payout']}"),
        L._row("5.4", True, {"attempts": attempts, "fee_budget": float(fee_budget)}, None,
               f"written down for the eval card: {attempts} attempt{'s' * (attempts != 1)}, total fee budget {usd(fee_budget)} ({usd(fee_budget / attempts)} an attempt); "
               f"at these odds at least one of {attempts} attempt{'s' * (attempts != 1)} passes {_pc(once)} of the time")]
    met = sum(v["margin"] >= 1 for v in reads)
    head = [f"SIM of {name} (phase 5) on {label} [{account}]: its test-period trades {h['span'][0]} .. {h['span'][1]} ({h['market']} {h['session']}, "
            f"{h['bar']}-minute bars; {at['days']} trading days, the sessions the read replayed), {n:,} runs of whole days drawn with replacement.",
            LABEL,
            f"SURVIVING VARIANTS: {len(reads)} of the {len(h['variants'])} locked (profitable on build, on the test and with worse fills). Read for this account: "
            f"{ch['id']}, the one nearest the bar on its weaker phase" + (f"; the middle one ({mid['id']}) reads eval {_pc(mid['eval']['p'])} and payout "
            f"{_pc(mid['payout']['p'])}, and {met} of the {len(reads)} meet the bar -- the best of many is flattered" if len(reads) > 1 else "") + ".",
            f"{'':>6s}  " + "  ".join(f"{words + ' within ' + str(need[p]['days']) + ' trading days':<47s}" for p, words in PHASES).rstrip(),
            f"{'micros':>6s}  " + "  ".join(f"{'plain':>7s}  {'live is worse (95 % interval)':<29s}  {'bust':>7s}" for _ in PHASES)]
    body = [f"{x['size']:>6d}  {_block(x['eval'])}  " + (_block(x["payout"]) if x["payout"] else "above the size the funded account starts at") for x in rows]
    d = IS.idea_dir(name, root)
    res = api.result("sim", name, status=IS.status(name, root), lines=lines, saved=[str(d / "sim" / f"{account}.json")], idea=name,
                     account={"id": account, "name": r.get("name"), "label": label, "confirmed": r.get("confirmed") is not False}, attempts=attempts,
                     fee_budget=float(fee_budget), rule=RULE, label=LABEL, paths=n, seed=PS.SEED if seed is None else int(seed),
                     lock=h["lock"], range={"start": h["span"][0], "end": h["span"][1]}, pool={"days": at["days"], "traded": at["traded"]},
                     days={p: need[p]["days"] for p, _ in PHASES}, locked=len(h["variants"]), survivors=len(reads),
                     variants=reads, middle=mid["id"], meeting=int(met), chosen={"variant": ch["id"], **{k: ch[k] for k in ("eval", "payout", "margin")}}, table=rows,
                     caveat=PS.CAVEAT)
    text = [*head, *body, "(bust = the share of the runs that lost the account inside those days, on the \"live is worse\" row)", *[x["text"] for x in lines],
            f"The interval is Monte Carlo noise only. {PS.CAVEAT}"]
    res["next"] = (f"The odds meet the owner's bar for this account: write the eval card before the first eval is bought (bp.py eval-card {name})" if lines[2]["passed"] else
                   f"The odds do not meet the owner's bar for this account: the eval is not bought on them -- another account (bp.py sim {name} --account=...), or none")
    res["text"] = "\n".join(text)
    try:
        IS.write_sim(name, account, res, root)
    except ValueError as e:
        raise J.Refuse(str(e)) from None
    from . import records                           # (the idea's copy in the Lab is the record's to bring up to date)
    res["lab"], lab, _ = records._lab(name, root)
    res["text"] = "\n".join([*text, *lab])
    return res
