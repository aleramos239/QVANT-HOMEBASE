"""pipe_stages.py -- THE STAGES OF THE PIPELINE, one function a stage (pipeline plan A, tasks 5 and 7: stages 0 to 7; the design's
sections 2 and 3). A stage calls the TOOLKIT (records, runner, tables, api, freeze, oos) for everything that is run or read,
judges what comes back with the pipeline's own gates (pipe_gates.py) -- from stage 5 on with the toolkit's own lines,
through its own commands -- and returns ONE STAGE CARD. It decides nothing else: the runner (pipe_runner.py) writes the
card and the idea's state, and says what a refusal means.

    stage_n(name, ctx, progress=None) -> stage card          STAGES = {n: stage_n}
      name      the pipeline idea (its card.json is on file: pipe_store.add)
      ctx       {"root": the pipeline root | None, "tiny": None | {"days": [...], "cells": [...], "workers": 1, "draws": 200}}
                tiny = a run on named build days and a few exit cells (the tests): never a verdict. For stages 5 and 6
                it may also name "box" and "build_avg_trade" (the lock's) and "test_days" (the read's): THE TEST SWITCH below
      progress  a callable told what a run is doing (runner.run_build's)

    THE STAGE CARD   {"stage", "name", "passed": True | False (stage 7: None, the owner decides), "result", "lines": [rows of
                      lines._row], "text", "picked", "tries", "rules": the numbers it was judged by, "utc", "seconds"}
                     + "code_problem": True ONLY when the stage stopped on the code and not on the idea (a wrong trade, a
                     strategy error, a line the toolkit and the pipeline read differently)
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
  stage5  ONE BOX, LOCKED  on picked.sub, three commands of the toolkit in their order:
                        1. api.code_check on ITS home store (after a low pass that is the store with the indicator on,
                           `<sub>f<k>__<block>_<side>-<ROOT>-tf<bar>`; stage 2 checked the raw heat map's): its check.json is
                           what the lock asks for. A line 1.1-1.4 that is False: passed False AND code_problem
                        2. records.build, ONE round (its reason: REASON): every store of a strict pass is on disk, so it
                           only reads lines 2.1-2.9; after a low pass it RUNS the other-market stores of the heat map with
                           its indicator, and line 2.5 reads them for the first time (a build also asks for the control
                           pool of each other market: the toolkit's own, linked; run here only if one is missing). A
                           False 2.5 after a low pass is the idea's verdict (result "other markets", no code problem). Any
                           other False line: the pipeline's gates and the toolkit disagree -- passed False AND
                           code_problem, the text holds the toolkit's row against the pipeline's own (MINE). lines = the
                           build's rows
                        3. freeze.lock: the worse-fills table of the home table (into the pipeline's stores folder), the
                           default = the MIDDLE box of those that make money with normal and with worse fills, lines
                           3.3-3.8 on it alone, lock.json. THE LOCK'S REFUSAL IS THE VERDICT when it is the box's: no box
                           made money both ways (result "no box") or the middle box fails one of 3.3-3.8 (result "box
                           failed", lines = all six rows, read the lock's own way off its two stores: _box). No second
                           box. Any other refusal of the lock goes up to the runner
                        locked (result "locked"): lines = the lock's rows 3.3-3.8 + P5.9 (passed None: a label, not a gate),
                        the prop check of the default box's BUILD trades on the pipeline's account (pipe_prop.odds).
                        + "locked": {"default": the box, "lock": the lock's hash, "prop": {account id: _prop's}}
  stage6  UNSEEN DAYS   oos.test(picked.sub, confirm=True, relatives_ok=not pipeline.json test.one_read_a_slot): THE ONE
                        READ of this idea, logged by the toolkit in the pipeline's own <ideas root>/test_reads.jsonl before
                        a day is opened; its stores go to pipe_store.runs_test. passed = its passed, lines = its rows
                        4.1-4.9, result "proven on history" | "not proven" (final). + "relatives": [{name, kind, utc,
                        verdict}] -- the related ideas that were read on these days before it (the read's own list; none,
                        or the toolkit's rule in force: []). On a pass: the prop check again, on the default box's TEST
                        trades and the days the read replayed (what propodds.handed hands phase 5), on the pipeline's
                        account and every account of pipeline.json prop.book_accounts. + "prop": {account id: _prop's},
                        "label": the pipeline's account's
  stage7  THE OWNER'S LOOK  nothing is run: THE BOOK CARD is put together from what is on file. passed None, result
                        "awaiting owner", + "book" (the runner's approve puts it in the book):
                          {name, sub, family, source, why, market, session, bar, filter,
                           rule {spec: the frozen card and settings (lock.json), default: the box, lock: the hash},
                           label (stage 6's, on the pipeline's account), prop {account id: {name, confirmed, size, payout_size,
                           eval, payout, label}} (an account whose rule file is not confirmed says confirmed false),
                           hours [first, last entry, HH:MM New York], trades, days_traded,
                           win_days_month (days at the account's `win_day` or more, at the label's eval size in micros, per
                           pipeline.json box.month_days session days), winning_months [months above $0, months with a trade],
                           biggest_day_share (its net / the net; None when the net is not above $0), fast_profit_share (the
                           net of the trades held box.fast_seconds or less / the net; None likewise), worst_day,
                           worst_drawdown (lines._drawdown: open losses counted), avg_trade, profit_factor (None: no losing
                           trade), net, tries, relatives_read (how many related ideas were read on the unseen days before
                           this one: the count of stage 6's `relatives`), stages {n: {passed, result, text}} of stages
                           0-6, utc}
                        EVERY MONEY FACT IS AT ONE CONTRACT after costs (win_days_month alone is at a size), read off the
                        default box's TEST trades on every session day the read replayed (a day without a trade = $0)

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
So nothing is booked in the repo's ledger.csv and no store is written to runs_bp/ or runs_bp_test/: the build's stores and
the lock's worse-fills table are in <root>/runs, the read's three stores in <root>/runs_test, every record under <root>/ideas.
NO LAB DRAFT (_stage, around every stage): the toolkit files an idea's draft in the Lab when HOMEBASE_DRAFTS_DIR is set.
That variable is taken out of the environment while a stage runs and put back afterwards: a sub-idea is never in the Lab.
THE TEST SWITCH (_switch, around the toolkit's commands of stages 5 and 6): a command run on named days is a smoke run and
saves nothing, so a `tiny` run goes through the toolkit's own switch -- BP_TEST_RUN (records.TEST_RUN) = the tiny run's days,
cells, workers, draws, box, build_avg_trade and test_days, with out, ledger and test_out the pipeline's folders -- for as
long as the command runs. Without `tiny` the variable is ABSENT for that time, whatever the environment held: the real
ranges. The toolkit refuses the switch for the app's own idea folder; the pipeline's ideas root is never that.
A STAGE RUN AGAIN (the runner was stopped before its card was written) finds what the toolkit has on file: stage 5 reads the
build on file instead of a second round, and a frozen idea's lock is shown, not made again; stage 6 reads the VERDICT ON FILE
for the lock stage 5 froze (test.json) -- the days are not read twice, and a read that is on file without a verdict is the
toolkit's refusal, never caught here.
WHAT IS NOT CAUGHT: judge.Refuse and the other api.REFUSALS of the toolkit (the no-start window, a store of other inputs,
the ledger's cap, a thin pool, a card the toolkit does not take at stage 3) go up to the runner. So do the refusals of the
toolkit's commands at stages 5 and 6: a lock that is refused for anything but its box, and the test's refusal of a read
that is on file for the idea itself (oos.start): an idea's own read is one read, and the pipeline never asks for a second look.
EVERY PIPELINE IDEA GETS ITS OWN READ (the owner, 2026-10-08; pipeline.json test.one_read_a_slot = false): the toolkit's rule
that a SAME-IDEA RELATIVE's read uses the days up (reads.used: the same entry trigger, market and session with a read in the
pipeline's log or among the old saved strategies, or a default box that takes the same side on most shared days) is waived
at stage 6 -- oos.test is called with relatives_ok -- and the relatives it found are on the read's line in the log, in
test.json and on the stage card. With the rule file at true the keyword is off, and such an idea stops at stage 6 with the
toolkit's words. By hand (`bp.py test`, the chat tool) the rule always holds.
A store row with `ok` False (a strategy error: no store was written) is a stage card with passed False and code_problem.
WRITES NOTHING of the pipeline's state (no stage card, no state.json, no book card); the toolkit writes its own stores,
ledger rows, sub-idea cards, check.json, rounds, lock.json, test.json and its one-read log. EVERY GATE NUMBER IS READ
(pipe_rules, rules.json, costs.json): none is typed here.
Locked by tests/test_pipe_stages.py (stages 0-4) and tests/test_pipe_finish.py (stages 5-7).
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import functools
import json
import os
import time
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_menus as RM

from . import api
from . import freeze as FRZ
from . import lines as L
from . import oos as OOS
from . import pipe_card as PC
from . import pipe_gates as G
from . import pipe_prop as PP
from . import pipe_rules as PR
from . import pipe_store as PS
from . import propodds as PO
from . import records as REC
from . import rules as R
from . import runner as RUN
from . import tables as T

NAMES = {0: "idea card", 1: "raw heat map", 2: "machine check", 3: "indicators", 4: "proof", 5: "pick one box and lock", 6: "unseen days", 7: "the owner's look"}
CHECKED = ("1.1", "1.2", "1.3", "1.4")              # the lines of the code check a machine reads alone (1.5 is a look at a chart, 1.6 waits for a change to the code)
SHOWN = 20                                          # trades listed in a row (their count is always whole)
REASON = "pipeline: stages 1 to 4 passed"           # the reason of a sub-idea's ONE build round (line 2.9 asks for it before the run)
OTHERS = "2.5"                                      # the build's line on the other markets: after a low pass the build is the first to read it
MINE = {"2.1": ("P1.1", "P3.1"), "2.2": ("P1.2", "P3.2"), "2.3": ("P4.2", "P4.2"), "2.4": ("P1.3", "P3.3"), "2.5": ("P3.6", "P3.6"), "2.6": ("P3.4", "P3.4"),
        "2.7": (None, "P3.5"), "2.8": ("P4.1", "P4.1")}     # a line of the build -> the pipeline's gate of it: (of a raw heat map, of one with an indicator)
SWITCH = ("days", "cells", "workers", "draws", "box", "build_avg_trade", "test_days")      # what a tiny run hands the toolkit's test switch (records.TEST_RUN)
BOOK_PROP = ("name", "confirmed", "size", "payout_size", "eval", "payout", "label")        # an account's prop check on a book card


# ================================================================ what every stage shares

def _kw(name: str, ctx: dict) -> dict:
    """What every toolkit call of an idea's stage gets (module docstring): the ONE place that reads `ctx`."""
    root, tiny = ctx.get("root"), ctx.get("tiny") or {}
    return {"root": PS.ideas_root(root), "out": PS.runs(root), "ledger": PS.ledger(name, root),
            "days": tiny.get("days"), "cells": tiny.get("cells"), "workers": tiny.get("workers"), "draws": tiny.get("draws")}


@contextlib.contextmanager
def _env(**put):
    """The environment while the block runs: every name of `put` at its value (None = not there), and as it was afterwards."""
    keep = {k: os.environ.get(k) for k in put}
    try:
        for k, v in put.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        yield
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _stage(fn):
    """A stage as the runner calls it: NO LAB DRAFT while it runs (module docstring) -- the app's variable for the drafts
    folder is out of the environment for every toolkit call the stage makes, and back when it returns or raises."""
    @functools.wraps(fn)
    def stage(name: str, ctx: dict, progress=None) -> dict:
        with _env(**{api.ideastore().draftstore.ENV: None}):
            return fn(name, ctx, progress)
    return stage


def _switch(name: str, ctx: dict):
    """THE TOOLKIT'S TEST SWITCH while one of its commands runs (module docstring): a tiny run's settings with the pipeline's
    folders, or -- without `tiny` -- no switch at all."""
    tiny, root = ctx.get("tiny"), ctx.get("root")
    return _env(**{REC.TEST_RUN: json.dumps({**{k: tiny[k] for k in SWITCH if tiny.get(k) is not None}, "out": str(PS.runs(root)),
                                              "ledger": str(PS.ledger(name, root)), "test_out": str(PS.runs_test(root))}) if tiny else None})


def _cmd(kw: dict) -> dict:
    """What a COMMAND of the toolkit takes of _kw (records.build, freeze.lock): the draws are its test switch's."""
    return {k: kw[k] for k in ("root", "out", "ledger", "workers", "days", "cells")}


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

@_stage
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

@_stage
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


@_stage
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


@_stage
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

@_stage
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


# ================================================================ stage 5: pick one box and lock

def _prop(x: dict, calendar, accounts) -> dict:
    """THE PROP CHECK of one box's trades on each account (pipe_prop.odds: the two odds within the days of pipeline.json,
    each at its best size, and the label) -> {account id: {name, confirmed, size, payout_size, eval, payout, label, text}}."""
    out = {}
    for rid in accounts:
        o = PP.odds(x, calendar, rid)
        out[rid] = {**{k: o["account"][k] for k in ("name", "confirmed")}, **{k: o[k] for k in ("size", "payout_size", "eval", "payout", "label", "text")}}
    return out


def _built(sub: str, kw: dict):
    """The sub-idea's BUILD ON FILE (its latest round with a result), or None: a stage 5 that is run again builds no second
    round -- a later round is read at a higher bar of line 2.3, and a frozen idea is not built at all."""
    d = REC._carded(sub, kw["root"])
    for n in reversed(api.ideastore().rounds(sub, kw["root"])):
        b = REC._json(d / "rounds" / str(n) / "build.json")
        if b:
            return b
    return None


def _gate(name: str, ctx: dict, picked: dict, line: str):
    """The pipeline's OWN row of a line of the build, off the stage cards on file (MINE), or None: no gate of its reads it."""
    want = MINE.get(line, (None, None))[bool(picked["filter"])]
    return next((x for c in PS.stages(name, ctx.get("root")).values() for x in c.get("lines") or []
                 if want and x.get("line") == want and x.get("sub", picked["sub"]) == picked["sub"]), None)


def _box(u: dict, kw: dict):
    """WHAT THE LOCK READ ON THE BOX, the lock's own way (freeze.run) off its two stores -- the home table and its worse-fills
    table -> (the default box | None: no box makes money with normal AND with worse fills, its rows 3.3-3.8). None: the
    stores of a lock are not both there, or not one table (the lock did not get as far as the box)."""
    try:
        st, _ = T._open(kw["out"], u["key"])
        wst, _ = T._open(kw["out"], RUN.worse_key(u["key"], u["sess"]))
        T._labels(st, u)
        rows = J.table(st, u)
        ids = J.table_stats(rows)["ids"]
        default, _ = REC.middle(rows, ids, {c: float(J.cellx(wst, c, u["sess"], u)["net"].sum()) for c in ids})
    except (KeyError, *api.REFUSALS):
        return None
    return default, ([] if default is None else [fn(T.box(st, u, default, kw["days"])) for fn in L.BOX])


@_stage
def stage5(name: str, ctx: dict, progress=None) -> dict:
    """The code check of the heat map's own home store, its one build round, then the lock: the middle box alone (module docstring)."""
    t0, kw, four = time.monotonic(), _kw(name, ctx), _before(name, ctx, 4)
    picked, tries, own = four["picked"], four["tries"], PR.need("prop", "account")
    sub, with_ = picked["sub"], (f" with {picked['filter'].replace('_', ' ', 1)}" if picked["filter"] else "")
    _, plan, specs = _idea(sub, kw)
    h, rules = plan["home"], {"prop": PR.need("prop"), "checked": list(CHECKED)}
    u = T.bp_unit(specs[0], h["market"], h["bar"], h["session"], "", T.filter_of(specs[0], REC.rule_filter(plan)))
    needs = lambda rows: {**rules, "lines": {x["line"]: x["need"] for x in rows}}  # noqa: E731
    with _switch(name, ctx):
        chk = api.code_check(sub, store=u["key"], looked=True, root=kw["root"], out=kw["out"])
        rows = [x for x in chk["lines"] if x["line"] in CHECKED]
        bad = [x for x in rows if x["passed"] is False]
        if bad:
            return _card(5, t0, False, "fail", rows, f"CODE PROBLEM ({sub}, its home store {u['key']}): {bad[0]['text']}", picked, tries, rules,
                         code_problem=True, check=chk["saved"])
        rows = (_built(sub, kw) or REC.build(sub, REASON, **_cmd(kw)))["lines"]
        bad = [x for x in rows if x["passed"] is False]
        odd = [x for x in bad if not (picked["filter"] and x["line"] == OTHERS)]
        if odd:                                     # the toolkit reads a line otherwise than the pipeline's gate did: neither number is believed
            said = "; ".join(f"the toolkit: {x['text']} -- the pipeline: {(_gate(name, ctx, picked, x['line']) or {}).get('text') or 'no gate of its own reads this line'}"
                             for x in odd)
            return _card(5, t0, False, "fail", rows, f"CODE PROBLEM: the toolkit's build of {sub} fails {', '.join(x['line'] for x in odd)} where the pipeline's gates "
                         f"passed ({said})", picked, tries, needs(rows), code_problem=True)
        if bad:
            return _card(5, t0, False, "other markets", rows, f"{sub}{with_} does not hold on its other markets, which the build is the first to run with the "
                         f"indicator on: {bad[0]['text']}", picked, tries, needs(rows))
        try:
            r = FRZ.lock(sub, **_cmd(kw))
        except J.Refuse:
            got = _box(u, kw)
            if got is None or (got[0] is not None and all(x["passed"] for x in got[1])):
                raise                               # not the box: the lock's own word goes up to the runner
            default, rows = got
            if default is None:
                return _card(5, t0, False, "no box", rows, f"no box of {sub}{with_} makes money with normal AND with worse fills: there is no middle box to "
                             "lock, and the idea stops", picked, tries, rules)
            return _card(5, t0, False, "box failed", rows, f"the middle box {default} of {sub}{with_} does not meet "
                         f"{', '.join(x['line'] for x in rows if not x['passed'])}: " + "; ".join(x["text"] for x in rows if not x["passed"])
                         + " -- no second box: the idea stops", picked, tries, needs(rows), default=default)
    lock = r["lock"]
    home, default = lock["home"], lock["default"]
    rows = [x for x in r["lines"] if x["line"] in {b["line"] for b in lock["box"]}]
    st, _ = T._open(Path(home["folder"]), home["key"])
    prop = _prop(J.cellx(st, default, home["session"], u), T.build_days(u, kw["days"]), [own])
    p = prop[own]
    rows.append(L._row("P5.9", None, None, {k: rules["prop"][k] for k in ("days", "eval", "payout")}, p["text"], account=own,
                       **{k: p[k] for k in ("label", "eval", "payout", "size", "payout_size")}))
    return _card(5, t0, True, "locked", rows, f"{sub}{with_} is locked: the middle box {default} (of {len(lock['survivors'])} that make money with normal and with worse "
                 f"fills), lock {lock['hash']}; on the build days it is a {p['label'].upper()} on {p['name']} (a label, not a gate)", picked, tries, needs(rows[:-1]),
                 locked={"default": default, "lock": lock["hash"], "prop": prop})


# ================================================================ stage 6: the unseen days, read once

def _accounts() -> list:
    """The accounts of a book card: the pipeline's own first, then pipeline.json prop.book_accounts (each once)."""
    return list(dict.fromkeys([PR.need("prop", "account"), *PR.need("prop", "book_accounts")]))


@_stage
def stage6(name: str, ctx: dict, progress=None) -> dict:
    """THE ONE READ of the unseen days for the locked heat map, and on a pass the label off its test trades (module docstring)."""
    t0, kw, five = time.monotonic(), _kw(name, ctx), _before(name, ctx, 5)
    picked, tries, was = five["picked"], five["tries"], five["locked"]
    sub, rules = picked["sub"], {"prop": PR.need("prop"), "test": PR.need("test")}
    r = REC._json(REC._carded(sub, kw["root"]) / "test.json")
    again = bool(r and r.get("lines") and r.get("lock") == was["lock"])      # the verdict of THIS lock's read is on file: it is read, the days are not
    if not again:
        with _switch(name, ctx):
            r = OOS.test(sub, confirm=True, root=kw["root"], workers=kw["workers"], out=PS.runs_test(ctx.get("root")), ledger=kw["ledger"],
                         days=(ctx.get("tiny") or {}).get("test_days"), relatives_ok=not rules["test"]["one_read_a_slot"])
    rows, rng, rel = r["lines"], r.get("range") or {}, list(r.get("relatives") or [])        # rel: the related ideas read on these days before this one
    rules.update(lines={x["line"]: x["need"] for x in rows}, range=rng)
    head = (f"{sub} on the unseen days {rng.get('start')} .. {rng.get('end')}" + (" (its verdict was on file: the days are not read twice)" if again else "")
            + (f" ({len(rel)} related idea{'s' * (len(rel) != 1)} read on these days before it)" if rel else ""))
    if r.get("passed") is not True:
        bad = [x for x in rows if x["passed"] is not True]
        return _card(6, t0, False, "not proven", rows, f"{head}: NOT PROVEN, it fails {', '.join(x['line'] for x in bad)} ({bad[0]['text'] if bad else r.get('verdict')}). "
                     "A fail is final: no re-tune, no second read", picked, tries, rules, relatives=rel)
    got = PO.handed(sub, kw["root"])                # what the freeze and the read leave for the prop simulator: the read's own store and days
    prop = _prop(PO.cell(got, was["default"]), got["calendar"], _accounts())
    p = prop[PR.need("prop", "account")]
    return _card(6, t0, True, "proven on history", rows, f"{head}: PROVEN ON HISTORY, every line 4.1-4.9 holds; on those days the box {was['default']} is a "
                 f"{p['label'].upper()} on {p['name']} (a label, not a gate)", picked, tries, rules, prop=prop, label=p["label"], relatives=rel)


# ================================================================ stage 7: the owner's look (the book card)

def _facts(x: dict, calendar, fast) -> dict:
    """THE MONEY FACTS OF A BOOK CARD off one box's trades (judge.cellx's arrays: 1 contract after costs) and the session days
    they were run on (a day without a trade = $0): module docstring. fast = the seconds a fast trade is held at most."""
    net, dur, by, months = np.asarray(x["net"], np.float64), np.asarray(x["dur_s"]), {}, {}
    for d, ent, s, n, mae in zip(x["date"], x["entry_ms"], dur, net, x["mae"]):
        by.setdefault(int(d), []).append((int(ent), int(ent) + int(s) * 1000, float(n), abs(float(mae)) + LB.COMM_RT))      # tables.box's row of a trade
    days = sorted({*LB._ordinals(calendar).tolist(), *by})
    day = np.array([sum(t[2] for t in by.get(d, ())) for d in days])
    opn = np.array([LB._worst_open(by.get(d, [])) + 0.0 for d in days])
    for d, rows in by.items():
        k = dt.date.fromordinal(d).strftime("%Y-%m")
        months[k] = months.get(k, 0.0) + sum(t[2] for t in rows)
    total, pf = float(net.sum()), L._pf(net)
    at = sorted(dt.datetime.fromtimestamp(int(m) / 1000, S.ET).strftime("%H:%M") for m in x["entry_ms"])
    share = lambda v: float(v) / total if L._profitable(total) else None  # noqa: E731
    return {"hours": [at[0], at[-1]] if at else None, "trades": len(net), "days_traded": len(by),
            "winning_months": [sum(bool(L._profitable(v)) for v in months.values()), len(months)],
            "biggest_day_share": share(day.max()) if len(day) else None, "fast_profit_share": share(net[dur <= fast].sum()),
            "worst_day": float(day.min()) if len(day) else None, "worst_drawdown": L._drawdown(day, opn),
            "avg_trade": total / len(net) if len(net) else None, "profit_factor": None if pf in (None, float("inf")) else pf, "net": total}


def _win_days(x: dict, calendar, account: str, size) -> float | None:
    """WINNING DAYS A MONTH on an account at `size` micros: the days of its day pool (propodds.days of propodds.ledger: the
    account's own daily limit, every session day) at its rule file's `win_day` or more, per pipeline.json box.month_days
    session days. None: no size (the box did not trade), or the account names no winning day."""
    r = PO.app().load_rules(account)
    if not size or not r.get("win_day"):
        return None
    pnl = PO.days(PO.ledger(x, size, r), r, calendar)[0]
    return float((pnl >= r["win_day"]).sum()) / len(pnl) * PR.need("box", "month_days")


@_stage
def stage7(name: str, ctx: dict, progress=None) -> dict:
    """THE BOOK CARD of an idea that passed its read, for the owner's look: put together from what is on file (module docstring)."""
    t0, kw, six = time.monotonic(), _kw(name, ctx), _before(name, ctx, 6)
    root, picked, tries, own, box = ctx.get("root"), six["picked"], six["tries"], PR.need("prop", "account"), PR.need("box")
    card, cards, sub = PS.card(name, root), PS.stages(name, root), picked["sub"]
    was = _before(name, ctx, 5)["locked"]
    lock = REC._json(REC._carded(sub, kw["root"]) / "lock.json") or {}
    if lock.get("hash") != was["lock"]:
        raise J.Refuse(f"the lock of {sub} on file ({lock.get('hash') or 'none'}) is not the one stage 5 froze ({was['lock']}): no book card is made of it")
    got = PO.handed(sub, kw["root"])
    x, prop = PO.cell(got, was["default"]), six["prop"]
    facts = _facts(x, got["calendar"], box["fast_seconds"])
    usd = lambda v: "n/a" if v is None else REC._usd(v)  # noqa: E731
    book = {"name": name, "sub": sub, "family": card["ways"][picked["way"]]["family"], "source": card.get("source"), "ref": card.get("ref"), "why": card.get("why"),
            "market": card["market"], "session": card["session"], "bar": picked["bar"], "filter": picked["filter"],
            "rule": {"spec": lock.get("spec"), "default": was["default"], "lock": was["lock"]},
            "label": prop[own]["label"], "prop": {a: {k: p.get(k) for k in BOOK_PROP} for a, p in prop.items()},
            **{k: facts[k] for k in ("hours", "trades", "days_traded")}, "win_days_month": _win_days(x, got["calendar"], own, prop[own]["size"]),
            **{k: facts[k] for k in ("winning_months", "biggest_day_share", "fast_profit_share", "worst_day", "worst_drawdown", "avg_trade", "profit_factor", "net")},
            "tries": tries, "relatives_read": len(six.get("relatives") or []),
            "stages": {str(n): {"passed": c.get("passed"), "result": c.get("result"), "text": (str(c.get("text") or "").splitlines() or [""])[0]}
                       for n, c in cards.items() if n in NAMES and n < max(NAMES)},
            "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    return _card(7, t0, None, "awaiting owner", [], f"{name} waits for the owner's look: {sub}, box {was['default']}, a {book['label'].upper()} on {prop[own]['name']} -- "
                 f"{facts['trades']:,} trades on {facts['days_traded']:,} of {len(got['calendar']):,} unseen session days, net {usd(facts['net'])} at one contract, "
                 f"worst drawdown {usd(facts['worst_drawdown'])}, {facts['winning_months'][0]} of {facts['winning_months'][1]} months won "
                 f"(bp.py pipe approve {name}, or bp.py pipe refuse {name} --why=TEXT)", picked, tries,
                 {"prop": PR.need("prop"), "box": box, "unseen": list(got["span"])}, book=book)


STAGES = {0: stage0, 1: stage1, 2: stage2, 3: stage3, 4: stage4, 5: stage5, 6: stage6, 7: stage7}
