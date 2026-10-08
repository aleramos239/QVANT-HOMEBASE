"""pipe_stages.py -- THE STAGES OF THE PIPELINE, one function a stage (pipeline plan A, task 5: stages 0 to 4; the design's
sections 2 and 3). A stage calls the TOOLKIT (records, runner, tables, api) for everything that is run or read, judges what
comes back with the pipeline's own gates (pipe_gates.py) and returns ONE STAGE CARD. It decides nothing else: the runner
(pipe_runner.py) writes the card and the idea's state, and says what a refusal means.

    stage_n(name, ctx, progress=None) -> stage card          STAGES = {n: stage_n}
      name      the pipeline idea (its card.json is on file: pipe_store.add)
      ctx       {"root": the pipeline root | None, "tiny": None | {"days": [...], "cells": [...], "workers": 1, "draws": 200}}
                tiny = a run on named build days and a few exit cells (the tests): never a verdict
      progress  a callable told what a run is doing (runner.run_build's)

    THE STAGE CARD   {"stage", "name", "passed": True | False, "result", "lines": [rows of lines._row], "text", "picked",
                      "tries", "rules": the numbers it was judged by, "utc", "seconds"} + "code_problem": True ONLY when
                     the stage stopped on the code and not on the idea (a wrong trade, a strategy error)
      picked    the heat map that moves on: {"sub": its toolkit idea, "bar", "way", "filter": None | "<block>_<side>"}
      tries     the heat maps judged for the idea so far (a way on a bar size at stage 1, an indicator at stage 3)

  stage0  THE CARD      pipe_card.check again (lines P0.1-P0.4), then every heat map's card saved in the toolkit
                        (records.card under the pipeline's own ideas root). result pass | fail. + "subs": their names
  stage1  RAW HEAT MAP  the HOME store of every heat map, in one run (runner.run_build, stage "units": one tape pass a bar
                        size for all the ways; no control pool), each judged by pipe_gates.raw. lines = rows P1.1-P1.3 of
                        every heat map, its name in front. result = strict | low of the ONE that moves on (pipe_gates.rank)
                        | fail (every one failed: passed False). tries = the heat maps judged. + "tables": one line each
  stage2  MACHINE CHECK on the heat map that moved on: lines 1.1-1.4 of the code check on its home store (api.code_check:
                        saved as the sub-idea's check.json, which the lock reads), then P2.5, the PRICE CHECK (below).
                        A line that is False = passed False AND code_problem. result pass | fail
  stage3  INDICATORS    first the other-market stores of the heat map (its card's neighbors), and `others` = the net of the
                        average box of each such table that is not the home table's trades again (records.run's reading).
                        After a STRICT pass: pipe_gates.strict_extra (P3.4, P3.6) -- none False: result "skipped", passed
                        True, nothing else is run; one False: fail. After a LOW pass: each indicator of the card ALONE, in
                        the card's order, as a toolkit idea of its own `<sub>f<k>` (k from 1: its card = the heat map's with
                        that one filter and the neighbors pipe_card.neighbors gives for it). Its HOME stores alone are run
                        (the table plain and with the indicator on: one tape pass; its other-market stores are left to
                        records.build, for the one that reaches the lock), then the six rows of pipe_gates.indicator (its
                        name in front) against the raw home table and the RAW heat map's `others` -- those of the markets
                        the indicator runs on too (Level 2: none, and P3.6 does not apply). The one that passes with the
                        biggest average trade moves on: picked.sub = `<sub>f<k>`, picked.filter = "<block>_<side>"; none
                        passes: passed False. tries = stage 1's + the indicators judged. result skipped | pass | fail.
                        + "indicators": one line each
  stage4  PROOF         on picked.sub: pipe_gates.reshuffle (P4.1); only when it holds, the control pool of the home's market
                        and bar size (stage "pools": linked from the toolkit's own, never run twice) and pipe_gates.random on
                        the share of the random heat maps the table beats, at the bar of the idea's `tries` (P4.2).
                        result pass | fail

THE PRICE CHECK (P2.5). The middle box of the heat map (records.middle: the middle of the boxes that made money; when none
did, the box with the most trades, and the row says so) is run again for its prices (runner.cell_trades: a store keeps
none), held against the store (the same number of trades and the same net, or the code changed since), and every trade's
entry and exit price is held against the 1-MINUTE BAR that contains its time: the low .. high of the prints of that minute,
from the session's own tape (l2sim.load_tape under the build switch, which never opens 2025-07-01 on; levels.session_arrays,
the swing bars' own builder, at 1 minute). The slack is the engine's slippage (costs.json `normal`: 1 tick). A minute
without a print holds no fill: such a trade is off. passed None, with the reason: rows without prices, or a day without
a tape. HOW A LIMIT IS READ: the engine fills a resting limit at ITS OWN price and never better (a target; a limit entry),
on the first print through it -- after a jump the minute of that print may not hold the price. Such a fill is WORSE for
the trade than any print of its minute; it is counted and listed, not off (as line 1.4 lists a gapped stop). A price
BETTER than its minute ever traded, by more than the slack, is off -- whatever the order.

WHAT EVERY TOOLKIT CALL GETS (_kw: one place): root = pipe_store.ideas_root, out = pipe_store.runs (the control pools are
links there), ledger = the idea's own, and with `tiny` its days, cells and workers (+ its draws for the random tables).
A sub-idea is read as the toolkit has it on file (its spec.json: what records.build will read at the lock's stage).
WHAT IS NOT CAUGHT: judge.Refuse and the other api.REFUSALS of the toolkit (the no-start window, a store of other inputs,
the ledger's cap, a thin pool, a card the toolkit does not take at stage 3) go up to the runner. A store row with `ok`
False (a strategy error: no store was written) is a stage card with passed False and code_problem.
WRITES NOTHING of the pipeline's state (no stage card, no state.json); the toolkit writes its own stores, ledger rows,
sub-idea cards and check.json. EVERY GATE NUMBER IS READ (pipe_rules, rules.json, costs.json): none is typed here.
Locked by tests/test_pipe_stages.py.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import time

import numpy as np

import judge as J
import l2sim as S
import run_menus as RM

from . import api
from . import lines as L
from . import pipe_card as PC
from . import pipe_gates as G
from . import pipe_rules as PR
from . import pipe_store as PS
from . import records as REC
from . import rules as R
from . import runner as RUN
from . import tables as T

NAMES = {0: "idea card", 1: "raw heat map", 2: "machine check", 3: "indicators", 4: "proof"}
CHECKED = ("1.1", "1.2", "1.3", "1.4")              # the lines of the code check a machine reads alone (1.5 is a look at a chart, 1.6 waits for a change to the code)
SHOWN = 20                                          # trades listed in a row (their count is always whole)


# ================================================================ what every stage shares

def _kw(name: str, ctx: dict) -> dict:
    """What every toolkit call of an idea's stage gets (module docstring): the ONE place that reads `ctx`."""
    root, tiny = ctx.get("root"), ctx.get("tiny") or {}
    return {"root": PS.ideas_root(root), "out": PS.runs(root), "ledger": PS.ledger(name, root),
            "days": tiny.get("days"), "cells": tiny.get("cells"), "workers": tiny.get("workers"), "draws": tiny.get("draws")}


def _card(n: int, t0: float, passed, result: str, rows: list, text: str, picked=None, tries: int = 0, rules=None, **more) -> dict:
    """A stage card (module docstring). `more`: code_problem, and what a stage adds for the reader."""
    return {"stage": n, "name": NAMES[n], "passed": passed, "result": result, "lines": rows, "text": text, "picked": picked, "tries": tries,
            "rules": rules or {}, "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "seconds": round(time.monotonic() - t0, 1), **more}


def _before(name: str, ctx: dict, n: int) -> dict:
    """The card of an earlier stage, which this one builds on: on file and passed, or refused."""
    c = PS.stages(name, ctx.get("root")).get(n)
    if not c or c.get("passed") is not True or not c.get("picked"):
        raise J.Refuse(f"{name}: stage {n} ({NAMES[n]}) has no passed card on file: the stages run in their order")
    return c


def _idea(sub: str, kw: dict) -> tuple:
    """A sub-idea as the toolkit has it on file -> (its spec, the plan of its tables, the engine's settings of its stores:
    the home's first). Refused: no card on file (stage 0 saves it), a card that is no longer whole."""
    spec = REC._spec(sub, REC._json(REC._carded(sub, kw["root"]) / "spec.json"))
    rows, plan = REC.card_lines(spec)
    if plan is None:
        raise J.Refuse(f"the card of {sub} on file is no longer whole ({next(x['text'] for x in rows if x['passed'] is False)})")
    return spec, plan, [RUN.checked(e) for e in REC.engine(spec, plan, sub)]


def _run(specs: list, kw: dict, stage: str, progress) -> str:
    """Run what is missing of these stores (runner.run_build: a store that is there is never run again) -> "" or, when a
    pass dropped sessions by a strategy error (no store was written), what to say of it. No store named: nothing is run."""
    if not specs:
        return ""
    rows = RUN.run_build(specs, kw["workers"], kw["out"], ledger=kw["ledger"], days=kw["days"], cells=kw["cells"], progress=progress, stage=stage)
    bad = [s for s in rows if s["ok"] is False]
    return f"{bad[0]['key']}: sessions were dropped by a strategy error ({bad[0].get('error')}): no store was written; the family has to be fixed first" if bad else ""


def _table(spec: dict, plan: dict, kw: dict, filt=None, control: bool = False) -> dict:
    """The table data of a sub-idea's HOME table (tables.built), with the card's sides on it (the gates read line 2.6 by them)."""
    return {**T.built(spec, plan["home"]["table"], filt, kw["out"], kw["days"], 1, control=control), "sides": plan["sides"]}


@contextlib.contextmanager
def _draws(n):
    """The draws of the random tables while the block runs (a tiny run only: records.run does the same)."""
    keep = J.RULE["draws"]
    try:
        if n:
            J.RULE["draws"] = int(n)
        yield
    finally:
        J.RULE["draws"] = keep


def _named(rows: list, who: str, **more) -> list:
    """Rows with the heat map (or the indicator) they are of in front of their text."""
    return [{**x, **more, "text": f"{who}: {x['text']}"} for x in rows]


def _error(n: int, t0: float, why: str, rows: list, picked, tries: int, rules: dict) -> dict:
    """The card of a stage that stopped on a strategy error."""
    return _card(n, t0, False, "fail", rows, f"CODE PROBLEM: {why}", picked, tries, rules, code_problem=True)


# ================================================================ stage 0: the card

def stage0(name: str, ctx: dict, progress=None) -> dict:
    """The card is read again and each of its heat maps becomes a toolkit idea with its card on file (module docstring)."""
    t0, kw = time.monotonic(), _kw(name, ctx)
    card = {k: v for k, v in PS.card(name, ctx.get("root")).items() if k != "subs"}
    rows, subs = PC.check(card)
    for s in subs or []:
        got = REC.card(s["name"], copy.deepcopy(s["spec"]), kw["root"])
        if not got["ok"]:
            rows[1], subs = L._row("P0.2", False, rows[1]["number"], rows[1]["need"], f"{s['name']}: the toolkit does not take its card -- {got['error']}"), None
            break
    ok = subs is not None
    return _card(0, t0, ok, "pass" if ok else "fail", rows, f"the card is whole: {len(subs)} heat map{'s' * (len(subs) != 1)} to run ({', '.join(s['name'] for s in subs)})"
                 if ok else "the card is not whole: " + "; ".join(x["text"] for x in rows if x["passed"] is False), rules={"card": PR.need("card")},
                 subs=[s["name"] for s in subs or []])


# ================================================================ stage 1: the raw heat map

def stage1(name: str, ctx: dict, progress=None) -> dict:
    """The home table of every heat map of the card, raw (no indicator): which one moves on (module docstring)."""
    t0, kw = time.monotonic(), _kw(name, ctx)
    card = PS.card(name, ctx.get("root"))
    subs = [(s, *_idea(s["name"], kw)) for s in card["subs"]]
    rules = {"raw": PR.need("raw"), "floor": R.need("2.2", card["market"])}
    why = _run([specs[0] for _, _, _, specs in subs], kw, "units", progress)      # the home stores alone: one tape pass a bar size, no pool
    if why:
        return _error(1, t0, why, [], None, 0, rules)
    res = [G.raw(_table(specs[0], plan, kw)) for _, _, plan, specs in subs]
    rows = [x for (s, *_), r in zip(subs, res) for x in _named(r["lines"], s["name"], sub=s["name"])]
    tables = [{"sub": s["name"], "way": s["way"], "bar": s["bar"], "result": r["result"], "avg_trade": r["avg_trade"], "text": r["text"]} for (s, *_), r in zip(subs, res)]
    i = G.rank(res)
    if i is None:
        return _card(1, t0, False, "fail", rows, f"every one of the {len(res)} raw heat maps failed: the idea is dropped", None, len(res), rules, tables=tables)
    s = subs[i][0]
    return _card(1, t0, True, res[i]["result"], rows, f"{s['name']} moves on with a {res[i]['result']} pass ({res[i]['text']}); {len(res)} heat map{'s' * (len(res) != 1)} judged",
                 {"sub": s["name"], "bar": s["bar"], "way": s["way"], "filter": None}, len(res), rules, tables=tables)


# ================================================================ stage 2: the machine check

def _minute_bars(root: str, iso: str):
    """(end_ns, high, low) of the 1-minute bars of a session's prints, from the engine's own tape of that session (the build
    switch: a day from 2025-07-01 on raises) by the swing bars' own builder; None = the session has no tape."""
    tape = S.load_tape(iso, root, allow_holdout=RUN.PERIOD)
    return None if tape is None or not len(tape.ts) else RUN._levels().session_arrays(tape, 1)


def _prices(spec: dict, t: dict, sess: str, kw: dict) -> dict:
    """Row P2.5, the price check of ONE box of a heat map (module docstring): `t` = the table data of its home table."""
    st, u, root = t["_st"], t["_u"], t["root"]
    table = {r["id"]: r for r in J.table(st, u)}
    cell, _ = REC.middle(list(table.values()), t["ids"])
    box = "the middle box" if cell else "no box made money, so the box with the most trades"
    cell = cell or max(t["ids"], key=lambda c: table[c]["trades"])
    slip, tick = R.template("costs")["normal"]["slippage_ticks"], R.template("costs")["contract"][root]["tick"]
    slack, need = slip * tick, {"slack_ticks": slip, "tick": tick}
    trades = RUN.cell_trades(spec, u["key"], cell, sess, kw["days"], RM.auto_workers(RUN.default_workers() if kw["workers"] is None else int(kw["workers"])))
    x, who = J.cellx(st, cell, sess, u), f"{box} ({cell})"
    if len(trades) != len(x["net"]) or abs(sum(tr["net"] for tr in trades) - float(x["net"].sum())) >= 0.01:
        return L._row("P2.5", False, None, need, f"{who}: run again, it has {len(trades):,} trades where its store has {len(x['net']):,} (or another net): the code "
                      "changed since the store was written, so its prices are not the store's", cell=cell)
    if not trades:
        return L._row("P2.5", None, 0, need, f"{who} has no trade: no price to hold against the bars", cell=cell)
    if any(tr.get(k) is None for tr in trades for k in ("entry_price", "exit_price")):
        return L._row("P2.5", None, None, need, f"{who}: the engine's trade rows of {spec['family']} carry no prices, so they cannot be held against the bars", cell=cell)
    bars, off, worse, blind, step, eps = {}, [], [], [], S.MIN_NS, tick * 1e-6
    for i, tr in enumerate(trades, 1):
        day = tr["date"]
        if day not in bars:
            bars[day] = _minute_bars(root, day)
        if bars[day] is None:
            blind.append(i)
            continue
        end, hi, lo = bars[day]
        long_ = tr["side"] in ("long", 1)
        for what, ms, px, pays in (("entry", tr["entry_ms"], float(tr["entry_price"]), not long_), ("exit", tr["exit_ms"], float(tr["exit_price"]), long_)):
            e = (int(ms) * 1_000_000 // step + 1) * step          # the end of the minute this fill is in
            k = int(np.searchsorted(end, e))
            at = dt.datetime.fromtimestamp(int(ms) / 1000, S.ET).strftime("%H:%M:%S")
            one = {"trade": i, "date": day, "side": "long" if long_ else "short", "fill": what, "at_et": at, "price": px}
            if k == len(end) or int(end[k]) != e:
                off.append({**one, "what": f"the {what} at {at} ET is in a minute without a print"})
                continue
            h, l_ = float(hi[k]), float(lo[k])
            if l_ - slack - eps <= px <= h + slack + eps:
                continue
            one.update(low=l_, high=h)
            # `pays`: does a HIGHER price pay this fill (a sale: a short's entry, a long's exit)? A price beyond the bar on the side that pays is off.
            better = px > h if pays else px < l_
            resting = px == (tr.get("order_price") if what == "entry" else tr.get("tp") if tr.get("exit_reason") == "tp" else None)
            (off if better or not resting else worse).append(
                {**one, "what": f"the {what} at {px:g} ({at} ET) is outside its minute's {l_:g} .. {h:g}" + ("" if better or not resting else ": a resting limit filled at its own price")})
    n, days = len(trades), len(bars)
    listed = (f"; {len(worse):,} fill{'s' * (len(worse) != 1)} of a resting limit at its own price, worse than its minute traded (the engine never fills a limit better): listed"
              if worse else "")
    more = {"cell": cell, "trades": n, "days": days, "off": len(off), "limit_fills": len(worse), "not_checked": len(blind),
            "exceptions": off[:SHOWN], "listed": worse[:SHOWN]}
    said = f"within {slip:g} tick{'s' * (slip != 1)} of the low .. high of its 1-minute bar"
    if off:
        return L._row("P2.5", False, len(off), need, f"{who}: {len(off):,} of the entry and exit prices of its {n:,} trades {'is' if len(off) == 1 else 'are'} not {said} "
                      f"({off[0]['what']}, trade {off[0]['trade']} of {off[0]['date']}){listed}", **more)
    if blind:
        gone = sorted({trades[i - 1]["date"] for i in blind})
        return L._row("P2.5", None, 0, need, f"{who}: {len(blind):,} of its {n:,} trades could not be held against the bars -- {len(gone)} session day{'s' * (len(gone) != 1)} "
                      f"of {root} {'has' if len(gone) == 1 else 'have'} no tape to build them from (first {gone[0]}); every other price is {said}{listed}", **more)
    return L._row("P2.5", True, 0, need, f"{who}: every entry and exit price of its {n:,} trades on {days:,} session days is {said}{listed}", **more)


def stage2(name: str, ctx: dict, progress=None) -> dict:
    """The machine check of the heat map that moved on: the code check's lines a machine reads, then the prices of its
    middle box against the raw bars (module docstring)."""
    t0, kw, one = time.monotonic(), _kw(name, ctx), _before(name, ctx, 1)
    picked, tries = one["picked"], one["tries"]
    RUN.may_start()                                 # (the price check runs the engine and reads tapes: never started in the no-start window)
    spec, plan, specs = _idea(picked["sub"], kw)
    t = _table(specs[0], plan, kw)
    costs = R.template("costs")
    rules = {"lines": list(CHECKED), "1.2": R.need("1.2"), "1.4": R.rule("1.4")["also"], "slippage_ticks": costs["normal"]["slippage_ticks"],
             "tick": costs["contract"][t["root"]]["tick"]}
    chk = api.code_check(picked["sub"], store=t["_u"]["key"], looked=True, root=kw["root"], out=kw["out"])
    rows = [x for x in chk["lines"] if x["line"] in CHECKED]
    if all(x["passed"] is not False for x in rows):
        rows.append(_prices(specs[0], t, plan["home"]["session"], kw))
    bad = [x for x in rows if x["passed"] is False]
    na = [x["line"] for x in rows if x["passed"] is None]
    head = f"{picked['sub']}, {chk['source']['trades']:,} trades in {chk['source']['lists']:,} boxes"
    if bad:
        return _card(2, t0, False, "fail", rows, f"CODE PROBLEM ({head}): {bad[0]['text']}", picked, tries, rules, code_problem=True, check=chk["saved"])
    return _card(2, t0, True, "pass", rows, f"the machine check holds ({head}): no line is false" + (f"; not read: {', '.join(na)}" if na else ""),
                 picked, tries, rules, check=chk["saved"])


# ================================================================ stage 3: the indicators

def _others(sub: str, plan: dict, kw: dict) -> dict:
    """{market: the net of the average box} of every OTHER-MARKET table a heat map's card names, as records.run reads a
    neighbor for line 2.5: a table where no box traded is $0, and one that is the home table's trades again is left out."""
    h = plan["home"]
    like = T.sigs(sub, h["market"], h["bar"], h["session"], None, kw["out"])
    got = {p["market"]: T.place(sub, p["market"], p["bar"], p["session"], None, kw["out"], like) for p in plan["neighbors"] if p["market"] != h["market"]}
    return {m: (x["avg_net"] if x["variants"] else 0.0) for m, x in got.items() if not x["copy"]}


def stage3(name: str, ctx: dict, progress=None) -> dict:
    """After a strict pass: the two lines it must also meet. After a low pass: each indicator of the card alone (module docstring)."""
    t0, kw, one = time.monotonic(), _kw(name, ctx), _before(name, ctx, 1)
    card, picked, tries = PS.card(name, ctx.get("root")), one["picked"], one["tries"]
    sub = picked["sub"]
    spec, plan, specs = _idea(sub, kw)
    h, rules = plan["home"], {"indicator": PR.need("indicator"), "floor": R.need("2.2", plan["home"]["market"]), "2.6": R.need("2.6")}
    why = _run([e for e in specs[1:] if e["markets"][0] != h["market"]], kw, "units", progress)      # the same heat map on the other markets
    if why:
        return _error(3, t0, why, [], picked, tries, rules)
    traw, others = _table(specs[0], plan, kw), _others(sub, plan, kw)
    if one["result"] == "strict":
        rows = G.strict_extra(traw, list(others.values()))
        bad = [x for x in rows if x["passed"] is False]
        return _card(3, t0, not bad, "fail" if bad else "skipped", rows, f"a strict pass does not also meet {' and '.join(x['line'] for x in bad)}: {bad[0]['text']}" if bad else
                     "skipped: a strict pass takes no indicator, and its sides and its other markets hold", picked, tries, rules, indicators=[])
    rows, tried, best = [], [], None
    for k, ind in enumerate(card.get("indicators") or [], 1):
        filt, fsub = f"{ind['block']}_{ind['side']}", f"{sub}f{k}"
        nbs = PC.neighbors(h["market"], spec["run"]["family"], h["bar"], ind["block"])
        got = REC.card(fsub, {**copy.deepcopy(spec), "name": fsub, "card": {**spec["card"], "neighbors": nbs},
                              "run": {**copy.deepcopy(spec["run"]), "filters": [{"block": ind["block"], "side": ind["side"]}]}}, kw["root"])
        if not got["ok"]:
            raise J.Refuse(f"indicator {k} of {name} ({ind['block']} {ind['side']}): the toolkit does not take the card of {fsub} -- {got['error']}")
        _, fplan, fspecs = _idea(fsub, kw)
        why = _run(fspecs[:1], kw, "units", progress)       # its home table, plain and with the indicator on: one tape pass
        if why:
            return _error(3, t0, why, rows, picked, tries + len(tried), rules)
        tf = _table(fspecs[0], fplan, kw, filt)
        got = G.indicator(tf, traw, [others[m] for m in nbs if m in others])     # the other markets the indicator runs on too (none: P3.6 does not apply)
        ok, at = not [x for x in got if x["passed"] is False], G.numbers(tf)["avg_trade"]
        rows += _named(got, f"{ind['block']} {ind['side']}", indicator=filt, sub=fsub)
        tried.append({"k": k, "block": ind["block"], "side": ind["side"], "sub": fsub, "passed": ok, "avg_trade": at})
        if ok and (best is None or at > best["avg_trade"]):
            best = tried[-1]
    tries += len(tried)
    if best is None:
        return _card(3, t0, False, "fail", rows, (f"none of the {len(tried)} indicators passes: the idea is dropped" if tried else
                                                   "a low pass needs an indicator and the card names none: the idea is dropped"), picked, tries, rules, indicators=tried)
    return _card(3, t0, True, "pass", rows, f"{best['block']} {best['side']} moves on (average trade {REC._usd(best['avg_trade'])}); "
                 f"{sum(x['passed'] for x in tried)} of {len(tried)} indicator{'s' * (len(tried) != 1)} passed",
                 {**picked, "sub": best["sub"], "filter": f"{best['block']}_{best['side']}"}, tries, rules, indicators=tried)


# ================================================================ stage 4: the proof

def stage4(name: str, ctx: dict, progress=None) -> dict:
    """The reshuffled runs, and only when they hold the random heat maps at the bar of the idea's tries (module docstring)."""
    t0, kw, three = time.monotonic(), _kw(name, ctx), _before(name, ctx, 3)
    picked, tries = three["picked"], three["tries"]
    _, plan, specs = _idea(picked["sub"], kw)
    filt = REC.rule_filter(plan)
    rules = {"proof": PR.need("proof"), "tries": tries, "random_bar": PR.random_bar(tries), "floor": R.need("2.2", plan["home"]["market"])}
    rows = [G.reshuffle(_table(specs[0], plan, kw, filt))]
    if rows[0]["passed"] is False:
        return _card(4, t0, False, "fail", rows, f"the reshuffled runs do not hold, so the random heat maps are not run: {rows[0]['text']}", picked, tries, rules)
    why = _run(specs[:1], kw, "pools", progress)    # the control pool of the home's market and bar size: read where it stands, run only when it is not there
    if why:
        return _error(4, t0, why, rows, picked, tries, rules)
    with _draws(kw["draws"]):
        c1 = _table(specs[0], plan, kw, filt, control=True)["controls"].get("c1") or {}
    rows.append({**G.random(c1.get("p_beat"), tries), "seeds": c1.get("seeds"), "replicates": c1.get("replicates")})
    ok = rows[1]["passed"] is True
    return _card(4, t0, ok, "pass" if ok else "fail", rows, "the proof holds: " + "; ".join(x["text"] for x in rows) if ok else f"the proof fails: {rows[1]['text']}",
                 picked, tries, rules)


STAGES = {0: stage0, 1: stage1, 2: stage2, 3: stage3, 4: stage4}
