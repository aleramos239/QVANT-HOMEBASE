"""LOCK of the pipeline's stages 0 to 4 (blueprint/pipe_stages.py) -- pipeline plan A, task 5.

THE PLUMBING, on tiny REAL runs: 3 named build days, 2 exit cells, 1 worker, 200 draws (the days and cells of
tests/test_blueprint_ideas.py), one pipeline card with ONE way (orb on NQ in the New York morning: a 1-minute and a 5-minute
heat map) and one indicator. Three days prove no edge, so THE GATES ARE PATCHED to canned answers (pipe_gates.raw, indicator,
strict_extra, reshuffle, random: their numbers are locked by tests/test_pipe_gates.py) and what is asserted is what a stage
runs, reads, saves and returns:

0. the card: each heat map becomes a toolkit idea with its card on file; a card that is not whole fails by its line
1. the raw heat map: ONLY the home store of each heat map (`<sub>-NQ-tf<bar>`), no pool, no other market; result, picked and
   tries follow the gate (low / strict before low / the bigger average trade / all fail); a strategy error is a code problem
2. the machine check: rows 1.1-1.4 and P2.5, the sub-idea's check.json on its home store; a false line is a code problem;
   the price check against 1-minute bars (within a tick; a resting limit at its own price is listed; a better price is off;
   a minute without a print; no tape; no prices; a list that is not the store's; no box that made money)
3. the indicators: the other-market stores first; skipped after a strict pass that also meets P3.4 and P3.6; after a low
   pass `<sub>f<k>` is created and judged, the bigger average trade wins, none passing drops the idea; tries are counted
4. the proof: no pool when the reshuffled runs fail; the home's pool, once, when they hold; the bar of the idea's tries
+ a stage writes nothing of the pipeline's state; what a stage does not catch goes up; no gate number is typed in the module.

EVERYTHING IS IN TEMP FOLDERS: the pipeline root (its ideas, stores and ledger), the Lab drafts (test_blueprint_ideas' env),
and the pools folder pipe_store links from (pipe_store.pools is patched: a tiny run can never reach a real control pool).
The clock stands on a Saturday. Each test plays the runner for the stage cards it builds on (pipe_store.write_stage) and
spies on runner.run_build for what was run, so the tests hold in any order; a store that is there is never run again, so
the whole file makes about ten tiny tape passes.

  pytest tests/test_pipe_stages.py -q          python tests/test_pipe_stages.py     the same, one line per test
"""
from __future__ import annotations

import copy
import datetime as dt
import io
import sys
import tempfile
import tokenize
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import run_menus as RM  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import pipe_card as PC  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import pipe_stages as ST  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

NAME = "pst_orb"
CARD = {"name": NAME, "why": "The first minutes of the New York morning set a range, and a break of it traps the traders who leaned on it.",
        "loser": "Traders who faded the opening range.", "source": "owner", "market": "NQ", "session": "nyam", "sides": "both", "sides_why": "",
        "ways": [{"family": "orb", "main_setting": "or_min", "values": ["5", "15", "30"], "fixed": {}, "limits": {}}],
        "indicators": [{"block": "trend", "side": "with", "why": "A break with the trend has more room."}]}
A1, A5 = f"{NAME}_a1", f"{NAME}_a5"                 # its two heat maps
F1, F2 = f"{A5}f1", f"{A5}f2"                       # the 5-minute heat map with the card's first / second indicator
HOME = f"{A5}-NQ-tf5"
_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="pipe_stages_")}
D = Path(_T["keep"].name).resolve()
ROOT, POOLS = D / "pipe", D / "pools"
CTX = {"root": ROOT, "tiny": {"days": TI.DAYS, "cells": TI.CELLS, "workers": 1, "draws": 200}}
CARD_KEYS = {"stage", "name", "passed", "result", "lines", "text", "picked", "tries", "rules", "utc", "seconds"}
PICK = {"sub": A5, "bar": "5", "way": 0, "filter": None}
G_INDICATOR, MINUTE_BARS = G.indicator, ST._minute_bars     # the gate and the bar loader themselves (tests patch the modules')
_DONE: dict = {}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    """Temp folders for all the toolkit writes, an empty pools folder to link from, a Saturday, the workers asked for."""
    TI.setup_function()
    POOLS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PS, "pools", lambda: POOLS)
    monkeypatch.setattr(RUN, "clock", lambda: TI.SAT)
    monkeypatch.setattr(RM, "auto_workers", lambda n=None: n)
    yield monkeypatch
    TI.teardown_function()


# ---------------------------------------------------------------- the runner's part, played by the tests

def add(name: str = NAME, **more) -> str:
    """A card on file in the pipeline's store, once a name (as `bp.py pipe add` files it)."""
    if name not in _DONE:
        card = {**copy.deepcopy(CARD), "name": name, **more}
        PS.add(card, PC.check(card)[1], ROOT, sig=PC.signature(card), family=PC.family_of(card))
        _DONE[name] = True
    return name


def ran(n: int, card: dict, name: str = NAME) -> dict:
    """The runner writes a stage's card: a later stage reads it."""
    PS.write_stage(name, n, card, ROOT)
    return card


def zero(name: str = NAME) -> dict:
    return ran(0, ST.stage0(add(name), CTX), name)


def raw(mp, **by_bar) -> None:
    """pipe_gates.raw answers by bar size: raw(mp, b1=("fail", None), b5=("low", 40.0))."""
    real = G.raw

    def canned(t):
        res, at = by_bar["b" + t["_u"]["tf"]]
        return {**real(t), "result": res, "avg_trade": at}
    mp.setattr(G, "raw", canned)


def one(mp, result: str = "low") -> dict:
    """Stage 1 with the 5-minute heat map moving on with `result` (the 1-minute one fails), its card on file."""
    zero()
    raw(mp, b1=("fail", None), b5=(result, 40.0))
    return ran(1, ST.stage1(NAME, CTX))


def forced(rows: list, fail=()) -> list:
    """A gate's own rows with every line that is read saying PASS, but the ones in `fail`."""
    return [{**x, "passed": False} if x["line"] in fail else x if x["passed"] is None else {**x, "passed": True} for x in rows]


def gate(mp, name: str, fail=()) -> list:
    """pipe_gates.<name> answers its own rows forced (above); -> the arguments of every call."""
    real, calls = getattr(G, name), []

    def canned(*a):
        calls.append(a)
        got = real(*a)
        return forced(got, fail) if isinstance(got, list) else forced([got], fail)[0]
    mp.setattr(G, name, canned)
    return calls


def three(mp, result: str = "low") -> dict:
    """Stages 1 and 3 on file: after a strict pass (skipped) or a low pass (the card's indicator moves on)."""
    one(mp, result)
    gate(mp, "strict_extra")
    gate(mp, "indicator")
    return ran(3, ST.stage3(NAME, CTX))


def spy(mp) -> list:
    """What runner.run_build was asked for and answered -> [{"stage", "keys", "kinds", "skipped"}], one a call."""
    real, calls = RUN.run_build, []

    def run_build(spec, *a, **k):
        rows = real(spec, *a, **k)
        calls.append({"stage": k.get("stage"), "keys": [r["key"] for r in rows], "kinds": [r["kind"] for r in rows], "skipped": [r["skipped"] for r in rows]})
        return rows
    mp.setattr(RUN, "run_build", run_build)
    return calls


def lines(card: dict) -> list:
    return [x["line"] for x in card["lines"]]


def whole(card: dict, n: int) -> dict:
    """A stage card has every field of the plan's shape."""
    assert set(card) >= CARD_KEYS and card["stage"] == n and card["name"] == ST.NAMES[n], sorted(card)
    assert isinstance(card["text"], str) and card["text"] and isinstance(card["rules"], dict) and card["rules"] and card["seconds"] >= 0
    assert dt.datetime.fromisoformat(card["utc"]).tzinfo is not None
    assert all(set(x) >= {"line", "passed", "number", "need", "text"} for x in card["lines"])
    assert ("code_problem" not in card) or card["code_problem"] is True
    return card


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except api.REFUSALS as e:
        assert word in str(e), f"refused, but not for {word!r}: {e}"
        return str(e)
    raise AssertionError(f"not refused ({word})")


def stores() -> list:
    return sorted(p.name for p in (ROOT / "runs").iterdir() if (p / "run.json").exists())


# ================================================================ what every toolkit call gets

def test_every_toolkit_call_gets_the_pipelines_folders_and_the_tiny_runs_days():
    add()
    kw = ST._kw(NAME, CTX)
    assert kw == {"root": ROOT / "ideas", "out": ROOT / "runs", "ledger": ROOT / "p" / NAME / "ledger.csv", "days": TI.DAYS, "cells": TI.CELLS, "workers": 1, "draws": 200}
    full = ST._kw(NAME, {"root": ROOT, "tiny": None})
    assert (full["root"], full["out"], full["ledger"]) == (kw["root"], kw["out"], kw["ledger"])
    assert [full[k] for k in ("days", "cells", "workers", "draws")] == [None] * 4                # the whole build range, the machine's workers
    assert set(ST.STAGES) == set(range(8)) and all(ST.STAGES[n].__name__ == f"stage{n}" and getattr(ST, f"stage{n}") is ST.STAGES[n] for n in ST.STAGES)


def test_a_heat_map_without_another_market_runs_nothing_at_stage_3_and_its_line_does_not_apply(world):
    one(world, "strict")
    extra = gate(world, "strict_extra")
    real = ST._idea

    def alone(sub, kw):                             # as for a family of NQ alone: its card's neighbor is the other bar size, a table of the SAME market
        spec, plan, specs = real(sub, kw)
        return spec, {**plan, "neighbors": [{**plan["home"], "bar": "1", "table": "NQ-tf1-nyam", "said": "1-minute bars"}]}, [specs[0], {**specs[0], "bar_sizes": ["1"]}]
    world.setattr(ST, "_idea", alone)
    world.setattr(RUN, "run_build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a store was run")))
    c = whole(ST.stage3(NAME, CTX), 3)
    assert extra[0][1] == [] and c["lines"][1]["line"] == "P3.6" and c["lines"][1]["passed"] is None and (c["passed"], c["result"]) == (True, "skipped")


# ================================================================ stage 0: the card

def test_stage_0_saves_each_heat_maps_card_in_the_toolkit_and_nothing_of_the_pipelines():
    add()
    before = (TI.tree(ROOT / "p"), PS.state(NAME, ROOT))
    c = whole(ST.stage0(NAME, CTX), 0)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "pass", None, 0) and c["subs"] == [A1, A5]
    assert lines(c) == ["P0.1", "P0.2", "P0.3", "P0.4"] and all(x["passed"] is True for x in c["lines"]) and c["rules"] == {"card": PR.need("card")}
    assert "2 heat maps" in c["text"] and A1 in c["text"]
    for s in PS.card(NAME, ROOT)["subs"]:
        d = ROOT / "ideas" / s["name"]
        assert (d / "card.md").is_file() and TI.read(d / "spec.json") == s["spec"]          # the toolkit's idea = the heat map as the card was filed
        assert REC.status(s["name"], ROOT / "ideas")["status"] == "idea"
    assert (TI.tree(ROOT / "p"), PS.state(NAME, ROOT)) == before                              # no stage card, no state: the runner writes those
    assert not (TI.HOME / "pipeline" / "p" / NAME).exists()


def test_stage_0_fails_a_card_that_is_not_whole_by_its_line():
    card = {**copy.deepcopy(CARD), "name": "pst_eve", "session": "eve"}                       # filed without the check (the store checks no card)
    if "pst_eve" not in _DONE:
        PS.add(card, None, ROOT, sig=PC.signature(card), family="orb")
        _DONE["pst_eve"] = True
    c = whole(ST.stage0("pst_eve", CTX), 0)
    assert (c["passed"], c["result"], c["subs"]) == (False, "fail", []) and [x["line"] for x in c["lines"] if x["passed"] is False] == ["P0.2"]
    assert "the evening session is not in this version" in c["text"] and not (ROOT / "ideas" / "pst_eve_a5").exists()


def test_stage_0_fails_when_the_toolkit_does_not_take_a_heat_maps_card(world):
    add()
    world.setattr(REC, "card", lambda name, spec, root=None: {"ok": False, "error": "the card is not whole: 0.4 FAIL said so"})
    c = whole(ST.stage0(NAME, CTX), 0)
    assert c["passed"] is False and c["subs"] == [] and c["lines"][1]["passed"] is False
    assert c["lines"][1]["text"].startswith(f"P0.2 FAIL {A1}: the toolkit does not take its card -- the card is not whole: 0.4 FAIL said so")


# ================================================================ stage 1: the raw heat map

def test_stage_1_runs_only_the_home_store_of_each_heat_map_and_no_pool(world):
    zero()
    calls, before = spy(world), TI.tree(ROOT / "p" / NAME)
    raw(world, b1=("fail", None), b5=("low", 40.0))
    c = whole(ST.stage1(NAME, CTX), 1)
    assert len(calls) == 1 and calls[0]["stage"] == "units"                                   # ONE run for all the heat maps
    assert calls[0]["keys"] == [f"{A1}-NQ-tf1", HOME] and calls[0]["kinds"] == ["unit", "unit"]
    assert {f"{A1}-NQ-tf1", HOME} <= set(stores())                                            # (what was RUN is the spy's: the later tests share the folder)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "low", PICK, 2)
    assert lines(c) == ["P1.1", "P1.2", "P1.3"] * 2 and [x["sub"] for x in c["lines"]] == [A1] * 3 + [A5] * 3
    assert c["lines"][0]["text"].startswith(f"{A1}: P1.1 ") and c["lines"][5]["text"].startswith(f"{A5}: P1.3 ")
    assert [(t["sub"], t["way"], t["bar"], t["result"], t["avg_trade"]) for t in c["tables"]] == [(A1, 0, "1", "fail", None), (A5, 0, "5", "low", 40.0)]
    assert c["rules"] == {"raw": PR.need("raw"), "floor": R.need("2.2", "NQ")} and A5 in c["text"] and "low pass" in c["text"]
    assert set(TI.tree(ROOT / "p" / NAME)) - set(before) <= {"ledger.csv", "ledger.csv.lock"}      # the idea's own ledger (and its lock), nothing of its state
    assert (ROOT / "p" / NAME / "ledger.csv").is_file() and PS.state(NAME, ROOT)["status"] == "queued" and PS.state(NAME, ROOT)["stage"] is None
    assert not [p for p in (ROOT / "runs").iterdir() if p.is_symlink()] and not list(POOLS.iterdir())      # no pool was linked, none was reached


def test_stage_1_takes_a_strict_pass_before_a_low_one_then_the_bigger_average_trade(world):
    zero()
    raw(world, b1=("fail", None), b5=("low", 40.0))
    ST.stage1(NAME, CTX)                                                                      # (the stores are there from here on)
    with TI.no_engine():                                                                      # ... and no stage 1 runs them again
        raw(world, b1=("strict", 80.0), b5=("low", 500.0))
        c = ST.stage1(NAME, CTX)
        assert (c["result"], c["picked"], c["tries"]) == ("strict", {"sub": A1, "bar": "1", "way": 0, "filter": None}, 2)
        raw(world, b1=("strict", 80.0), b5=("strict", 90.0))
        c = ST.stage1(NAME, CTX)
        assert (c["result"], c["picked"]["sub"], c["passed"]) == ("strict", A5, True)
        raw(world, b1=("low", 80.0), b5=("low", 90.0))
        assert ST.stage1(NAME, CTX)["picked"]["sub"] == A5


def test_stage_1_drops_the_idea_when_every_heat_map_fails(world):
    zero()
    raw(world, b1=("fail", None), b5=("fail", 12.0))
    c = whole(ST.stage1(NAME, CTX), 1)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", None, 2) and "every one of the 2 raw heat maps failed" in c["text"]
    assert "code_problem" not in c and len(c["lines"]) == 6


def test_a_strategy_error_stops_a_stage_as_a_code_problem(world):
    zero()
    world.setattr(RUN, "run_build", lambda spec, *a, **k: [{"key": HOME, "kind": "unit", "ok": False, "skipped": False, "error": "ERROR ZeroDivisionError in on_bar"}])
    c = whole(ST.stage1(NAME, CTX), 1)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", None, 0) and c["code_problem"] is True and c["lines"] == []
    assert c["text"].startswith(f"CODE PROBLEM: {HOME}: sessions were dropped by a strategy error (ERROR ZeroDivisionError in on_bar)")


def test_what_the_toolkit_refuses_goes_up_to_the_runner(world):
    name = add("pst_orbw", market="ES")                                                       # another card: none of its stores is there
    zero(name)
    one(world)
    world.setattr(S, "OPEN_WINDOW", (dt.time(9, 18), dt.time(9, 36)))                         # off since 2026-10-07 (l2sim.OPEN_WINDOW): put back here
    world.setattr(RUN, "clock", lambda: dt.datetime(2026, 10, 5, 9, 25, tzinfo=S.ET))         # a Monday, inside the no-start window
    with TI.no_engine():
        refused(lambda: ST.stage1(name, CTX), "nothing heavy starts")                         # runner.may_start's, before a pass
        refused(lambda: ST.stage2(NAME, CTX), "nothing heavy starts")                         # the price check runs the engine: it does not start either
    assert not [k for k in stores() if k.startswith(name)]
    refused(lambda: ST.stage2(name, CTX), "stage 1 (raw heat map) has no passed card on file")      # the stages run in their order
    refused(lambda: ST.stage4(name, CTX), "stage 3 (indicators) has no passed card on file")
    add("pst_none", market="GC")                                                              # a card whose stage 0 never ran: no toolkit idea
    refused(lambda: ST.stage1("pst_none", CTX), "has no card on file")


# ================================================================ stage 2: the machine check

def test_stage_2_reads_the_code_checks_lines_and_the_prices_and_saves_the_check(world):
    first = one(world)
    c = whole(ST.stage2(NAME, CTX), 2)
    assert lines(c) == ["1.1", "1.2", "1.3", "1.4", "P2.5"] and [x["passed"] for x in c["lines"]] == [True] * 5, [x["text"] for x in c["lines"]]
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "pass", first["picked"], 2) and "code_problem" not in c
    p = c["lines"][4]
    assert p["text"].startswith("P2.5 PASS the middle box (") and "within 1 tick of the low .. high of its 1-minute bar" in p["text"]
    assert p["trades"] >= 1 and (p["off"], p["limit_fills"], p["not_checked"], p["exceptions"]) == (0, 0, 0, []) and p["cell"] in p["text"]
    assert p["need"] == {"slack_ticks": 1.0, "tick": 0.25} == {"slack_ticks": R.template("costs")["normal"]["slippage_ticks"], "tick": R.template("costs")["contract"]["NQ"]["tick"]}
    chk = TI.read(ROOT / "ideas" / A5 / "check.json")                                         # the sub-idea's code check, on ITS home store: what the lock reads
    assert c["check"] == [str(ROOT / "ideas" / A5 / "check.json")] and chk["command"] == "code-check" and chk["name"] == A5
    assert chk["source"]["kind"] == "store" and Path(chk["source"]["where"]).resolve() == (ROOT / "runs" / HOME).resolve()
    assert [x["line"] for x in chk["lines"]] == ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]
    assert not (ROOT / "ideas" / A1 / "check.json").exists()                                  # the heat map that did not move on is not checked
    assert c["rules"]["lines"] == ["1.1", "1.2", "1.3", "1.4"] and c["rules"]["slippage_ticks"] == 1.0 and 2 not in PS.stages(NAME, ROOT)


def test_stage_2_a_false_line_of_the_code_check_is_a_code_problem_and_no_price_is_read(world):
    one(world)
    real = api.code_check

    def off(*a, **k):
        r = real(*a, **k)
        return {**r, "lines": [{**x, "passed": False, "text": "1.2 FAIL 1 overlap"} if x["line"] == "1.2" else x for x in r["lines"]]}
    world.setattr(api, "code_check", off)
    world.setattr(RUN, "cell_trades", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the price check ran")))
    c = whole(ST.stage2(NAME, CTX), 2)
    assert (c["passed"], c["result"]) == (False, "fail") and c["code_problem"] is True and lines(c) == ["1.1", "1.2", "1.3", "1.4"]
    assert c["text"].startswith("CODE PROBLEM") and "1.2 FAIL 1 overlap" in c["text"] and c["picked"] == PICK


def bars(trades: list, moved: dict, gone=()):
    """A stand-in for the minute bars: around every fill of `trades` a bar of its price -1 .. +1 point; `moved` =
    {(trade number, "entry" | "exit"): (low, high) as offsets from the price}; `gone` = fills whose minute has no bar."""
    def of(root, iso):
        got = {}
        for i, tr in enumerate(trades, 1):
            for what in ("entry", "exit"):
                if tr["date"] == iso and (i, what) not in gone:
                    lo, hi = moved.get((i, what), (-1.0, 1.0))
                    got[(int(tr[f"{what}_ms"]) * 1_000_000 // S.MIN_NS + 1) * S.MIN_NS] = (tr[f"{what}_price"] + hi, tr[f"{what}_price"] + lo)
        ends = sorted(got)
        return np.array(ends, np.int64), np.array([got[e][0] for e in ends]), np.array([got[e][1] for e in ends])
    return of


def test_the_price_check_holds_every_fill_against_its_minute_and_reads_a_limit_as_the_engine_fills_it(world):
    one(world)
    kw = ST._kw(NAME, CTX)
    spec, plan, specs = ST._idea(A5, kw)
    t = ST._table(specs[0], plan, kw)
    cell = REC.middle(J.table(t["_st"], t["_u"]), t["ids"])[0]
    trades = RUN.cell_trades(specs[0], HOME, cell, "nyam", TI.DAYS)
    i = next(k for k, tr in enumerate(trades, 1) if tr["exit_reason"] == "tp")               # a target: a resting limit, filled at its own price
    tr = trades[i - 1]
    assert tr["exit_price"] == tr["tp"] and tr["entry_price"] != tr["order_price"]            # ... entered on a stop (the fill is the print + a tick)
    up, down = (5.0, 10.0), (-10.0, -5.0)                                                     # the minute traded only above / only below the price
    worse, better = (up, down) if tr["side"] == "long" else (down, up)                        # a long's target SELLS: a minute above it paid more

    def check(moved=None, gone=(), none=False):
        world.setattr(ST, "_minute_bars", (lambda root, iso: None) if none else bars(trades, moved or {}, gone))
        return ST._prices(specs[0], t, "nyam", kw)

    r = check()
    assert r["passed"] is True and (r["trades"], r["off"], r["limit_fills"]) == (len(trades), 0, 0)
    r = check({(i, "exit"): (0.25, 3.0)})                                                     # exactly one tick outside: the engine's slippage
    assert r["passed"] is True and r["limit_fills"] == 0
    r = check({(i, "exit"): worse})                                                           # the limit at its own price, worse than the minute: listed
    assert r["passed"] is True and (r["off"], r["limit_fills"]) == (0, 1) and "a resting limit" in r["text"] and "listed" in r["text"]
    assert r["listed"][0]["trade"] == i and r["listed"][0]["fill"] == "exit" and "filled at its own price" in r["listed"][0]["what"]
    r = check({(i, "exit"): better})                                                          # a price better than the minute ever traded: off, limit or not
    assert r["passed"] is False and r["number"] == 1 and r["off"] == 1 and r["exceptions"][0]["trade"] == i and "P2.5 FAIL" in r["text"]
    for side in (up, down):                                                                   # a stop's fill outside its minute, either way: off
        r = check({(i, "entry"): side})
        assert r["passed"] is False and r["exceptions"][0]["fill"] == "entry" and "outside its minute's" in r["exceptions"][0]["what"]
    r = check({(i, "entry"): (0.5, 3.0)})                                                     # two ticks outside
    assert r["passed"] is False
    r = check(gone=[(i, "entry")])
    assert r["passed"] is False and "in a minute without a print" in r["exceptions"][0]["what"]
    r = check(none=True)                                                                      # no tape for the day: not read, and it says why
    assert r["passed"] is None and r["not_checked"] == len(trades) and "no tape" in r["text"] and r["text"].startswith("P2.5 n/a ")
    world.setattr(ST, "_minute_bars", bars(trades, {}))
    real = RUN.cell_trades
    world.setattr(RUN, "cell_trades", lambda *a, **k: [{**x, "entry_price": None} for x in real(*a, **k)])
    r = ST._prices(specs[0], t, "nyam", kw)
    assert r["passed"] is None and "carry no prices" in r["text"]
    world.setattr(RUN, "cell_trades", lambda *a, **k: real(*a, **k)[1:])                      # another list than the store's: the code changed
    r = ST._prices(specs[0], t, "nyam", kw)
    assert r["passed"] is False and "the code changed since the store was written" in r["text"]
    world.setattr(RUN, "cell_trades", real)
    most = max(J.table(t["_st"], t["_u"]), key=lambda x: x["trades"])
    world.setattr(ST, "_minute_bars", bars(real(specs[0], HOME, most["id"], "nyam", TI.DAYS), {}))
    world.setattr(REC, "middle", lambda rows, ids, worse=None: (None, []))                    # no box made money: the one with the most trades
    r = ST._prices(specs[0], t, "nyam", kw)
    assert r["passed"] is True and "no box made money, so the box with the most trades" in r["text"] and (r["cell"], r["trades"]) == (most["id"], most["trades"])


def test_stage_2_a_wrong_price_is_a_code_problem_and_a_day_without_a_tape_is_not(world):
    one(world)
    world.setattr(ST, "_minute_bars", lambda root, iso: None)
    c = whole(ST.stage2(NAME, CTX), 2)
    assert c["passed"] is True and "code_problem" not in c and c["lines"][4]["passed"] is None and c["text"].endswith("not read: P2.5")
    real = RUN._levels().session_arrays
    world.setattr(ST, "_minute_bars", MINUTE_BARS)
    world.setattr(RUN._levels(), "session_arrays", lambda tape, tf: (lambda e, h, l_: (e, h + 50.0, l_ + 50.0))(*real(tape, tf)))      # the bars 50 points away
    c = whole(ST.stage2(NAME, CTX), 2)
    assert (c["passed"], c["result"]) == (False, "fail") and c["code_problem"] is True and c["lines"][4]["passed"] is False
    assert c["text"].startswith("CODE PROBLEM") and "P2.5 FAIL" in c["text"] and c["lines"][4]["off"] >= 2


# ================================================================ stage 3: the indicators

def test_stage_3_is_skipped_after_a_strict_pass_that_holds_on_its_sides_and_its_other_markets(world):
    first = one(world, "strict")
    calls, extra, cards = spy(world), gate(world, "strict_extra"), []
    world.setattr(G, "indicator", lambda *a: (_ for _ in ()).throw(AssertionError("an indicator was tried after a strict pass")))
    real = REC.card
    world.setattr(REC, "card", lambda *a, **k: cards.append(a[0]) or real(*a, **k))
    c = whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "skipped", first["picked"], 2) and lines(c) == ["P3.4", "P3.6"]
    assert len(calls) == 1 and calls[0]["stage"] == "units" and calls[0]["keys"] == [f"{A5}-ES-tf5", f"{A5}-GC-tf5"]      # the same heat map on the other markets
    (t, others), = extra
    assert t["unit"] == f"{HOME}-nyam" and t["sides"] == "both" and len(others) == 2 and all(isinstance(x, float) for x in others)
    assert cards == [] and c["indicators"] == [] and "skipped" in c["text"] and c["rules"]["indicator"] == PR.need("indicator")


def test_stage_3_fails_a_strict_pass_that_does_not_meet_its_two_lines(world):
    one(world, "strict")
    gate(world, "strict_extra", fail=("P3.6",))
    c = whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["result"], c["tries"]) == (False, "fail", 2) and "P3.6" in c["text"] and "code_problem" not in c
    assert [x["line"] for x in c["lines"] if x["passed"] is False] == ["P3.6"]


def test_stage_3_after_a_low_pass_tries_the_cards_indicator_as_a_toolkit_idea_of_its_own(world):
    one(world)
    calls, tried = spy(world), gate(world, "indicator")
    c = whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["result"], c["tries"]) == (True, "pass", 3) and c["picked"] == {"sub": F1, "bar": "5", "way": 0, "filter": "trend_with"}
    assert [x["stage"] for x in calls] == ["units", "units"] and calls[0]["keys"] == [f"{A5}-ES-tf5", f"{A5}-GC-tf5"]
    assert calls[1]["keys"] == [f"{F1}-NQ-tf5", f"{F1}__trend_with-NQ-tf5"] and calls[1]["kinds"] == ["unit", "filter"]     # its HOME table, plain and with it on
    spec = TI.read(ROOT / "ideas" / F1 / "spec.json")                                         # the heat map's card with that one filter
    assert spec["run"]["filters"] == [{"block": "trend", "side": "with"}] and spec["card"]["neighbors"] == ["ES", "GC"] and spec["name"] == F1
    assert spec["card"]["home"] == {"market": "NQ", "session": "nyam", "bar": "5"} and (ROOT / "ideas" / F1 / "card.md").is_file()
    assert TI.read(ROOT / "ideas" / A5 / "spec.json")["run"]["filters"] == []                 # the raw heat map's card stays as it was
    (tf, traw, others), = tried
    assert tf["unit"] == f"{F1}__trend_with-NQ-tf5-nyam" and traw["unit"] == f"{HOME}-nyam" and tf["sides"] == traw["sides"] == "both"
    assert len(others) == 2 and all(isinstance(x, float) for x in others)
    assert lines(c) == [f"P3.{i}" for i in range(1, 7)] and all(x["text"].startswith("trend with: P3.") and x["sub"] == F1 and x["indicator"] == "trend_with" for x in c["lines"])
    assert [(x["k"], x["block"], x["side"], x["sub"], x["passed"]) for x in c["indicators"]] == [(1, "trend", "with", F1, True)] and "trend with moves on" in c["text"]
    with TI.no_engine():                                                                      # again: every store is there
        assert ST.stage3(NAME, CTX)["picked"]["sub"] == F1


def test_stage_3_drops_the_idea_when_no_indicator_passes_and_counts_the_tries(world):
    first = one(world)
    gate(world, "indicator", fail=("P3.5",))
    c = whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", first["picked"], 3) and "none of the 1 indicators passes" in c["text"]
    assert [x["line"] for x in c["lines"] if x["passed"] is False] == ["P3.5"] and c["indicators"][0]["passed"] is False and "code_problem" not in c
    real = PS.card
    world.setattr(PS, "card", lambda name, root=None: {**real(name, root), "indicators": []})  # a low pass on a card without an indicator
    c = whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["tries"], c["lines"]) == (False, 2, []) and "the card names none" in c["text"]


def test_stage_3_moves_on_the_passing_indicator_with_the_biggest_average_trade(world):
    one(world)
    real, two = PS.card, [CARD["indicators"][0], {"block": "vwap", "side": "with", "why": "A break above the session's average price has buyers behind it."}]
    world.setattr(PS, "card", lambda name, root=None: {**real(name, root), "indicators": two})
    numbers = G.numbers
    world.setattr(G, "numbers", lambda t: {**numbers(t), "avg_trade": {F1: 50.0, F2: 90.0}.get(t["_u"]["key"].split("__")[0], numbers(t)["avg_trade"])})
    calls = gate(world, "indicator")
    c = whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["tries"]) == (True, 4) and c["picked"] == {"sub": F2, "bar": "5", "way": 0, "filter": "vwap_with"}
    assert [x["sub"] for x in c["indicators"]] == [F1, F2] and [x["avg_trade"] for x in c["indicators"]] == [50.0, 90.0] and "2 of 2 indicators passed" in c["text"]
    assert [a[0]["unit"] for a in calls] == [f"{F1}__trend_with-NQ-tf5-nyam", f"{F2}__vwap_with-NQ-tf5-nyam"] and len(c["lines"]) == 12
    assert c["lines"][6]["text"].startswith("vwap with: P3.1")
    world.setattr(G, "indicator", lambda tf, traw, others: forced(G_INDICATOR(tf, traw, others), ("P3.1",) if "vwap" in tf["unit"] else ()))
    c = ST.stage3(NAME, CTX)                                                                  # the bigger one fails: the one that passes moves on
    assert (c["passed"], c["tries"], c["picked"]["sub"], c["picked"]["filter"]) == (True, 4, F1, "trend_with") and "1 of 2 indicators passed" in c["text"]




def test_stage_3_reads_the_other_markets_an_indicator_runs_on_and_none_for_one_of_nq_alone(world):
    one(world)
    tried, real = gate(world, "indicator"), PC.neighbors
    world.setattr(PC, "neighbors", lambda market, family, bar, block=None: ["ES"] if block else real(market, family, bar))      # as for SMT: NQ and ES
    ST.stage3(NAME, CTX)
    assert len(tried[-1][2]) == 1 and TI.read(ROOT / "ideas" / F1 / "spec.json")["card"]["neighbors"] == ["ES"]
    world.setattr(PC, "neighbors", lambda market, family, bar, block=None: ["1-minute bars"] if block else real(market, family, bar))   # as for Level 2
    c = ST.stage3(NAME, CTX)
    assert tried[-1][2] == [] and TI.read(ROOT / "ideas" / F1 / "spec.json")["card"]["neighbors"] == ["1-minute bars"]
    p36 = c["lines"][5]
    assert p36["line"] == "P3.6" and p36["passed"] is None and c["passed"] is True            # no other market runs it: the line does not block
    world.setattr(PC, "neighbors", real)
    ST.stage3(NAME, CTX)                                                                      # (the card of the indicator as the other tests have it)


def test_stage_3_a_card_the_toolkit_refuses_goes_up_and_a_strategy_error_is_a_code_problem(world):
    one(world)
    gate(world, "indicator")
    ST.stage3(NAME, CTX)                                                                      # (the other-market stores are there)
    real = REC.card
    world.setattr(REC, "card", lambda *a, **k: {"ok": False, "error": "the card is not whole: 0.2 FAIL filter said so"})
    refused(lambda: ST.stage3(NAME, CTX), f"indicator 1 of {NAME} (trend with): the toolkit does not take the card of {F1} -- the card is not whole")
    world.setattr(REC, "card", real)
    run = RUN.run_build
    world.setattr(RUN, "run_build", lambda spec, *a, **k: [{"key": f"{F1}__trend_with-NQ-tf5", "kind": "filter", "ok": False, "skipped": False, "error": "ERROR in the filter"}]
                  if any(s["name"] == F1 for s in (spec if isinstance(spec, list) else [spec])) else run(spec, *a, **k))
    c = whole(ST.stage3(NAME, CTX), 3)
    assert c["passed"] is False and c["code_problem"] is True and c["tries"] == 2 and c["picked"] == PICK and "ERROR in the filter" in c["text"]


# ================================================================ stage 4: the proof

def test_stage_4_runs_no_pool_when_the_reshuffled_runs_fail(world):
    third = three(world, "strict")
    calls, shuffled = spy(world), gate(world, "reshuffle", fail=("P4.1",))
    world.setattr(G, "random", lambda *a: (_ for _ in ()).throw(AssertionError("the random heat maps were read")))
    c = whole(ST.stage4(NAME, CTX), 4)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", third["picked"], 2) and lines(c) == ["P4.1"]
    assert calls == [] and "the random heat maps are not run" in c["text"] and "code_problem" not in c       # nothing was run: no pool
    assert shuffled[0][0]["unit"] == f"{HOME}-nyam" and c["rules"] == {"proof": PR.need("proof"), "tries": 2, "random_bar": PR.random_bar(2), "floor": 70}


def test_stage_4_runs_the_homes_pool_once_and_holds_the_table_against_the_bar_of_its_tries(world):
    three(world, "strict")
    calls, draws = spy(world), J.RULE["draws"]
    gate(world, "reshuffle")
    beat = gate(world, "random")
    c = whole(ST.stage4(NAME, CTX), 4)
    assert (c["passed"], c["result"], c["tries"]) == (True, "pass", 2) and lines(c) == ["P4.1", "P4.2"] and c["text"].startswith("the proof holds")
    assert len(calls) == 1 and calls[0] == {"stage": "pools", "keys": ["c1-NQ-tf5"], "kinds": ["pool"], "skipped": calls[0]["skipped"]}      # the home's, no other market's
    pool = ROOT / "runs" / "c1-NQ-tf5"
    assert (pool / "run.json").is_file() and not pool.is_symlink() and not list(POOLS.iterdir())      # run here (tiny), under the temp root
    assert not [k for k in stores() if k.startswith("c1") and k != "c1-NQ-tf5"]
    (p_beat, tries), = beat
    assert 0.0 <= p_beat <= 1.0 and tries == 2 and c["lines"][1]["tries"] == 2 and c["lines"][1]["need"] == PR.random_bar(2)
    assert len(c["lines"][1]["seeds"]) == R.template("control")["seeds"] and c["lines"][1]["replicates"] == 200 and J.RULE["draws"] == draws      # the tiny run's draws, then the law's again
    with TI.no_engine():                                                                      # the pool is there: read, never run twice
        gate(world, "random", fail=("P4.2",))
        c = whole(ST.stage4(NAME, CTX), 4)
    assert (c["passed"], c["result"]) == (False, "fail") and c["text"].startswith("the proof fails: P4.2") and "code_problem" not in c


def test_stage_4_proves_the_heat_map_with_its_indicator_at_the_bar_of_three_tries(world):
    third = three(world)
    assert third["picked"]["sub"] == F1 and third["tries"] == 3
    shuffled = gate(world, "reshuffle")
    beat = gate(world, "random")
    c = whole(ST.stage4(NAME, CTX), 4)
    assert shuffled[0][0]["unit"] == f"{F1}__trend_with-NQ-tf5-nyam" and beat[0][1] == 3 and c["rules"]["random_bar"] == PR.random_bar(3)
    assert c["picked"] == third["picked"] and c["tries"] == 3 and c["lines"][1]["tries"] == 3 and c["passed"] is True


# ================================================================ no number of a gate is typed in the module

def test_no_gate_number_is_typed_in_the_module():
    src = (W / "blueprint" / "pipe_stages.py").read_text(encoding="utf-8")
    typed = {t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.NUMBER}
    # 0-7 the stages, counts and indexes · 20 rows listed · 1000 and 1_000_000 ms / ns · 1e-6 a float's slack · 0.01 a cent (records.show's) · 0.0 an empty table
    assert typed <= {"0", "1", "2", "3", "4", "5", "6", "7", "20", "1000", "1_000_000", "1e-6", "0.01", "0.0"}, sorted(typed)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-W", "ignore"]))
