"""LOCK of the blueprint lines (blueprint/lines.py, mc.py, tables.py, api.py, cli.py: `bp.py build --stored`) -- toolkit plan, step 2.

(a) ALL 1,875 STORED TABLES of BLUEPRINT.md section 3: lines 2.1 (heat, share, average variant), 2.2 (average trade, floor),
    2.4 (trades), 2.6 (each side), 2.5 (neighbors) and 2.8 (Monte Carlo) equal out/blueprint/funnel_units.csv number for
    number, and the counts of funnel.md come out the same (1,875 -> 249 -> 56 -> 28 -> 28 -> 18 -> 6 -> 3).
    THE MONTE CARLO IS CHECKED TWO WAYS. funnel.py drew all its tables one after the other from ONE generator, so a table's
    number there depends on the tables before it. (i) With one generator carried through the tables in catalog order (same
    seed, same method) lines.monte gives funnel_units.csv EXACTLY (with the numpy that wrote it, 2.0.2: a numpy whose
    Generator.multinomial draws differently would break (i) and leave (ii)). (ii) The toolkit's own number -- a fresh
    generator with the fixed seed for every table, so that a unit always gets the same answer -- cannot be that number; it
    must sit inside Monte Carlo noise of it: 5 standard errors of the difference of two 1,000-run estimates (+ 1 run).
(b) THE 57 UNITS THAT PASSED THE OLD BUILD (out/v2/build_units.csv, build_pass true): the random-entry numbers of line 2.3 (and
    of 2.7) are judge.build's own, control for control: at out/v2's setting (200 draws, the first 2 seeds, its six folders) --
    where they are also the numbers out/v2 stored -- and, with BP_FULL=1, at the rule in force (4,000 draws, every seed on
    disk; about 15 minutes).
(c) HAND-MADE TABLES: the edge of every line (exactly 60 %, exactly at the floor, exactly 95 %, exactly 200 / 120 trades, half
    the neighbors, one side, a side at $0, no filter, exactly 75 % / 90 % of the runs, ...).
(d) THE COMMAND: the DRY RUN label, the lines in order, text and JSON, exit codes, refusals, and the seal: nothing but stores of
    the old build days (2021-09-22 .. 2023-12-31) is loaded.
Reads BUILD stores only; runs no simulation; writes nothing.

  pytest tests/test_blueprint_lines.py -q     (about 1.5 minutes)     python tests/test_blueprint_lines.py     + a count per block
  BP_FULL=1 ...     + (b) at the rule in force (about 15 minutes more)        BP_QUICK=1 ...     without (a) and (b): seconds
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import lines as L  # noqa: E402
from blueprint import mc as MC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import tables as T  # noqa: E402

FUNNEL = W / "out" / "blueprint" / "funnel_units.csv"
with (W / "out" / "v2" / "build_units.csv").open() as _fh:
    V2 = {r["uid"]: r for r in csv.DictReader(_fh)}
PASSERS = [uid for uid, r in V2.items() if r["build_pass"] == "True"]
STORED_END = R.template("ranges")["stored_build"]["end"]
RUNS = R.template("montecarlo")["runs"]
RESULTS: dict = {}


@contextlib.contextmanager
def rule(**kw):
    keep = dict(J.RULE)
    J.RULE.update(kw)
    try:
        yield
    finally:
        J.RULE.clear()
        J.RULE.update(keep)


def table(nets, trades=None, root="NQ", **kw) -> dict:
    """A hand-made table: one list of daily nets per variant; one trade per variant and day unless `trades` says otherwise."""
    net = np.array(nets, float)
    return {"root": root, "net": net, "n": np.ones(net.shape) if trades is None else np.array(trades, float), **kw}


class Draws:
    """Stands in for the generator: hands mc.draw the day counts a test wants, one row per run."""

    def __init__(self, per_run):
        self.w = np.array(per_run)

    def multinomial(self, n, p, size):
        assert self.w.shape == (size, len(p)) and (self.w.sum(1) == n).all()
        return self.w


def skip(unless: str = "", when: str = "") -> None:
    """Leave a block out: `unless` = an environment variable that must be set for it, `when` = one that must not be."""
    if (unless and not os.environ.get(unless)) or (when and os.environ.get(when)):
        import pytest
        pytest.skip(f"set {unless}=1" if unless else f"{when} is set")


def refused(fn, word: str = "") -> None:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert word in str(e), str(e)
        return
    raise AssertionError(f"not refused ({word})")


# ================================================================ (a) all 1,875 stored tables = funnel_units.csv

def test_all_stored_tables_reproduce_the_funnel():
    skip(when="BP_QUICK")                                   # about a minute: every stored table is read
    with FUNNEL.open() as fh:
        ref = list(csv.DictReader(fh))
    one, rows, bad = MC.generator(), [], []                 # ONE generator through every table, in catalog order: funnel.py's draws
    for a in T.catalog():
        try:
            t = T.stored(a)
        except J.Refuse:
            continue                                        # no judged variant (6 tables): not in the funnel either
        h, f, tr, s = L.heat(t), L.floor(t), L.trades(t), L.sides(t)
        rows.append({"uid": t["uid"], "addr": t["unit"], "family": t["family"], "root": t["root"], "heat": h["passed"], "avg": h["avg"],
                     "share": h["number"], "avgtrade": f["number"], "floor": f["passed"], "trades": tr["number"], "trades200": tr["passed"],
                     "pace": tr["on_pace"]["passed"], "long": s["long"], "short": s["short"], "n_long": s["n_long"], "n_short": s["n_short"],
                     "sides": s["passed"], "monte": L.monte(t, one)["number"], "own": L.monte(t)["number"], "_u": t["_u"]})
    for r in rows:                                          # the neighbors need every table's average: after the loop
        nb = L.neighbors({"neighbors": T.neighbors(r.pop("_u"))})
        r["neighbors"], r["nb_ok"] = nb["number"], nb["passed"]
    assert [r["uid"] for r in rows] == [x["uid"] for x in ref] and len(rows) == 1875, f"{len(rows)} tables, funnel_units.csv has {len(ref)}"
    worst = flips = 0.0
    for r, x in zip(rows, ref):
        for k in ("addr", "family", "root"):
            if r[k] != x[k]:
                bad.append(f"{r['uid']}: {k} {r[k]!r} != {x[k]!r}")
        for k in ("heat", "floor", "sides"):
            if r[k] is not (x[k] == "True"):
                bad.append(f"{r['uid']}: {k} {r[k]} != funnel {x[k]}")
        for k in ("avg", "share", "avgtrade", "trades", "long", "short", "n_long", "n_short", "neighbors", "monte"):
            if r[k] != float(x[k]):
                bad.append(f"{r['uid']}: {k} {r[k]!r} != funnel {x[k]}")
        m = float(x["monte"])                               # (ii) the toolkit's own number: Monte Carlo noise away, not more
        p = (r["own"] + m) / 2
        if abs(r["own"] - m) > 5 * math.sqrt(2 * p * (1 - p) / RUNS) + 1 / RUNS:
            bad.append(f"{r['uid']}: Monte Carlo with a fresh generator {r['own']} is not within noise of funnel {m}")
        worst, flips = max(worst, abs(r["own"] - m)), flips + (R.meets("2.8", r["own"]) != R.meets("2.8", m))
    assert not bad, f"{len(bad)} differences\n" + "\n".join(bad[:40])
    # funnel.md: each line on its own, then one on top of the other (6 = out/v2's stored test (2), not redrawn here: see (b))
    alone = {"heat": 249, "floor": 58, "pace": 1674, "sides": 265, "nb_ok": 309, "trades200": 1477}
    assert {k: sum(bool(r[k]) for r in rows) for k in alone} == alone
    assert sum(R.meets("2.8", r["monte"]) for r in rows) == 13
    left, chain = list(zip(rows, ref)), []
    for keep in (lambda r, x: r["heat"], lambda r, x: r["floor"], lambda r, x: r["pace"], lambda r, x: r["sides"], lambda r, x: r["nb_ok"],
                 lambda r, x: x["random"] == "True", lambda r, x: R.meets("2.8", r["monte"])):
        left = [(r, x) for r, x in left if keep(r, x)]
        chain.append(len(left))
    assert chain == [249, 56, 28, 28, 18, 6, 3], chain
    last = ["ib-NQ-tf15-mid:mode=break", "ib-NQ-tf30-mid:mode=break", "ib-NQ-tf5-mid:mode=break"]
    assert sorted(r["addr"] for r, _ in left) == last
    own = [r for r in rows if R.meets("2.8", r["own"])]     # the same count and the same end with the toolkit's own number
    assert len(own) == 11 and sorted(r["addr"] for r in own if r["addr"] in last) == last and not {r["uid"] for r in own} - {r["uid"] for r in rows if R.meets("2.8", r["monte"])}
    RESULTS["test_all_stored_tables_reproduce_the_funnel"] = (
        len(rows), len(rows), f"Monte Carlo with a fresh generator per table: largest gap to the funnel {worst:.3f}; {int(flips)} tables "
        f"change sides at 75 % ({len(own)} pass 2.8 alone, funnel 13); the checklist still ends at the same 3 tables")


# ================================================================ (b) the passers of the old build: line 2.3 = judge.build

def _same(a, b: str) -> bool:
    """A number of the judge against the same number in out/v2/build_units.csv."""
    return (str(a) == b) if isinstance(a, (bool, str)) else math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-9)


def _passers(as_v2: bool) -> tuple:
    """Every unit that passed the old build: its controls are judge.build's, control for control (as_v2: also the numbers out/v2
    stored); line 2.3 = the judge's verdict on the random controls, with the law's strict "above"; line 2.7 applies to the
    units with a filter and to no other."""
    bad, n, bar, asked = [], {"pass": 0, "bar": 0, "thin": 0}, R.need("2.3", 1), R.template("control")["seeds"]
    for uid in PASSERS:
        u = T.unit(uid)
        t = T.controls(T.stored(u))
        b = J.build(u)
        if t["controls"] != b["controls"] or not b["controls"]:
            bad.append(f"{uid}: controls differ from judge.build\n  here  {t['controls']}\n  judge {b['controls']}")
        for c, v in t["controls"].items() if as_v2 else ():             # out/v2's stored numbers: the <control>_<number> columns
            for k, x in v.items():
                if V2[uid].get(f"{c}_{k}", "") != "" and not _same(x, V2[uid][f"{c}_{k}"]):
                    bad.append(f"{uid}: {c} {k} {x!r} != out/v2 {V2[uid][f'{c}_{k}']}")
        row, rnd = L.beats_random(t), {k: v for k, v in t["controls"].items() if k in L.RANDOM}
        ps, seeds = [v["p_beat"] for v in rnd.values()], min(len(v["seeds"]) for v in rnd.values())
        judge = all(v["pass"] for v in rnd.values())                    # the judge: above the random average, >= 95 %, every trade matched
        want = {"number": min(ps), "passed": judge and min(ps) > bar, "seeds": seeds, "thin": seeds < asked, "controls": rnd}
        if {k: row[k] for k in want} != want:
            bad.append(f"{uid}: line 2.3 {row} != {want}")
        if as_v2 and not (b["t2"] and judge):
            bad.append(f"{uid}: not a passer at out/v2's setting")
        f = L.filter_alone(t)
        if (f["passed"] is None) != (not {"base", "days"} & set(u["controls"])):
            bad.append(f"{uid}: line 2.7 {f} with controls {u['controls']}")
        n["pass"], n["bar"], n["thin"] = n["pass"] + row["passed"], n["bar"] + (judge and not row["passed"]), n["thin"] + row["thin"]
    assert len(PASSERS) == 57 and not bad, f"{len(bad)} differences\n" + "\n".join(bad[:20])
    return len(PASSERS), len(PASSERS), (f"line 2.3 passes for {n['pass']}; {n['bar']} sit at exactly 95 % (they pass the judge's >= and fail "
                                        f"the law's \"above\"); THIN {n['thin']}")


def test_passers_random_numbers_are_the_judges_as_v2():
    """At out/v2's own setting (200 draws, the first 2 seeds, its six store folders: nothing after 2024 is even listed)."""
    skip(when="BP_QUICK")                                   # about half a minute
    with rule(**J.AS_V2):
        RESULTS["test_passers_random_numbers_are_the_judges_as_v2"] = _passers(True)


def test_passers_random_numbers_are_the_judges_rule_in_force():
    """BP_FULL=1: the same at the rule in force -- 4,000 draws, every control seed on disk (what `bp.py build --stored` prints)."""
    skip(unless="BP_FULL")                                  # about 15 minutes
    assert (J.RULE["draws"], J.RULE["seeds"], J.RULE["dirs"]) == (R.template("control")["draws"], None, None)
    RESULTS["test_passers_random_numbers_are_the_judges_rule_in_force"] = _passers(False)


# ================================================================ (c) hand-made tables: the edge of every line

def test_line_2_1_share_of_variants_profitable():
    r = L.heat(table([[5], [5], [5], [-1], [-1]]))                      # 3 of 5 = exactly 60 %: "more than" is strict
    assert r["passed"] is False and r["number"] == 0.6 and r["need"] == 0.60 and r["line"] == "2.1" and (r["profitable"], r["variants"]) == (3, 5)
    assert r["text"] == "2.1 FAIL 60 % of variants profitable (3 of 5; need more than 60 %); average variant $3"
    assert L.heat(table([[5], [5], [5], [5], [-1]]))["passed"] is True                              # 80 %
    r = L.heat(table([[1], [1], [1], [1], [-10]]))                      # 80 % green, but the average variant loses
    assert r["passed"] is False and r["number"] == 0.8 and r["avg"] == -1.2 and "average variant -$1 (need it profitable)" in r["text"]
    assert L.heat(table([[2], [1], [1], [1], [-5]]))["passed"] is False                             # the average variant at exactly $0
    assert L.heat(table([[3, -1], [-2, 4], [1, 1]]))["number"] == 1.0   # a variant is judged on its total over the days
    assert L.heat(table([[0], [0], [0]]))["passed"] is False            # a variant at $0 is not profitable


def test_line_2_2_average_trade_against_the_floor():
    r = L.floor(table([[100, 40], [70, 70]]))                            # 280 / 4 trades = exactly $70: "or more"
    assert r["passed"] is True and r["number"] == 70.0 and r["need"] == 70 and r["text"] == "2.2 PASS average trade $70 (need $70)"
    r = L.floor(table([[41, 41], [41, 41]]))
    assert r["passed"] is False and r["text"] == "2.2 FAIL average trade $41 (need $70)"
    r = L.floor(table([[69.99, 69.99]]))                                # the whole figure would read "$70": cents are shown
    assert r["passed"] is False and r["text"] == "2.2 FAIL average trade $69.99 (need $70)"
    assert L.floor(table([[100.0, 0.0]], [[2, 0]]))["number"] == 50.0  # net of all variants / THEIR TRADES, not / days
    assert L.floor(table([[139.0]], root="GC"))["passed"] is False and L.floor(table([[139.0]], root="NQ"))["passed"] is True
    assert L.floor(table([[75.0]], root="ES"))["passed"] is True and L.floor(table([[74.5]], root="ES"))["passed"] is False
    r = L.floor(table([[0.0, 0.0]], [[0, 0]]))
    assert r["passed"] is False and r["number"] is None and "no trade" in r["text"]
    refused(lambda: L.floor(table([[100.0]], root="CL")), "CL")         # a market the law names no floor for


def test_line_2_3_beats_random_tables():
    def ctl(p, seeds=10, **kw):
        return {"pass": True, "lift": 100.0, "p_beat": p, "replicates": 4000, "real_replicates": seeds, "short": 0, **kw}

    r = L.beats_random({"controls": {"c1": ctl(0.95)}})                       # exactly 95 %: the judge's >= passes it, the law's "above" does not
    assert r["passed"] is False and r["number"] == 0.95 and r["need"] == 0.95 and r["thin"] is False and r["seeds"] == 10
    assert r["text"] == "2.3 FAIL beats 95 % of 4,000 random tables (need above 95 %); 10 seeds"
    assert L.beats_random({"controls": {"c1": ctl(0.9503)}})["passed"] is True
    r = L.beats_random({"controls": {"c1": ctl(0.999, seeds=2)}})             # THIN is said, not failed
    assert r["passed"] is True and r["thin"] is True and r["seeds"] == 2 and r["text"].endswith("2 seeds: THIN (the law asks 10)")
    for rd, bar in ((1, 0.95), (2, 0.975), (3, 0.983), (4, 0.9875), (5, 0.99)):                     # the bar rises with the round
        a, b = L.beats_random({"round": rd, "controls": {"c1": ctl(bar)}}), L.beats_random({"round": rd, "controls": {"c1": ctl(bar + 0.0003)}})
        assert (a["passed"], b["passed"], a["need"], a["round"]) == (False, True, bar, rd)
    assert L.beats_random({"round": 2, "controls": {"c1": ctl(0.97)}})["passed"] is False
    refused(lambda: L.beats_random({"round": 6, "controls": {"c1": ctl(1.0)}}), "6")                      # there is no sixth round
    r = L.beats_random({"controls": {"c1": ctl(0.99), "c2": ctl(0.90, seeds=2)}})                         # every control must hold; the weakest is shown
    assert r["passed"] is False and r["number"] == 0.90 and r["seeds"] == 2 and r["thin"] is True
    r = L.beats_random({"controls": {"c1": ctl(0.99, short=3)}})              # trades without a random match: not the same days
    assert r["passed"] is False and "3 trades had no random match" in r["text"]
    r = L.beats_random({"controls": {"days": {"pass": True, "p_beat": 0.99}, "base": {"pass": True}, "shift": ctl(0.96, seeds=2)}})
    assert r["passed"] is True and list(r["controls"]) == ["shift"]    # days / base are the filter's controls (2.7), not random tables
    for missing in ({}, {"controls": {}}, {"controls": {"c1": {"pass": False, "why": "no pool"}}}, {"controls": {"base": {"pass": True}}}):
        r = L.beats_random(missing)
        assert r["passed"] is False and r["number"] is None and r["thin"] is True and "no random tables" in r["text"]
    assert "no pool" in L.beats_random({"controls": {"c1": {"pass": False, "why": "no pool"}}})["text"]


def test_line_2_4_trades_and_on_pace():
    one = [0] * 9
    r = L.trades(table([one + [0]] * 2, [one + [200]] * 2))
    assert r["passed"] is True and r["number"] == 200.0 and r["need"] == 200 and "on_pace" not in r
    assert r["text"] == "2.4 PASS 200 trades, average variant (need 200)"
    r = L.trades(table([one + [0]] * 2, [one + [200], one + [199]]))    # the AVERAGE variant: 199.5
    assert r["passed"] is False and r["number"] == 199.5 and r["text"] == "2.4 FAIL 199.50 trades, average variant (need 200)"
    r = L.trades(table([one + [0]], [one + [120]], months=27))          # the stored 27 months: also read on pace = 200 x 27 / 45
    assert r["passed"] is False and r["on_pace"] == {"passed": True, "need": 120.0, "months": 27}
    assert r["text"] == "2.4 FAIL 120 trades, average variant (need 200); on pace: PASS (need 120 on the stored 27 months)"
    r = L.trades(table([one + [0]], [one + [119]], months=27))
    assert r["on_pace"]["passed"] is False and r["text"].endswith("on pace: FAIL (need 120 on the stored 27 months)")
    r = L.trades(table([one + [0]], [one + [250]], months=27))
    assert r["passed"] is True and r["on_pace"]["passed"] is True
    assert "on_pace" not in L.trades(table([one + [0]], [one + [150]], months=45))                  # the whole build: no pace reading


def test_line_2_5_neighbors():
    r = L.neighbors({"neighbors": [10.0, -5.0]})                        # exactly half: "half or more"
    assert r["passed"] is True and r["number"] == 0.5 and r["need"] == 0.5 and (r["profitable"], r["tables"]) == (1, 2)
    assert r["text"] == "2.5 PASS 1 of 2 neighbor tables profitable, 50 % (need 50 % or more)"
    assert L.neighbors({"neighbors": [10.0, -5.0, -1.0]})["passed"] is False
    assert L.neighbors({"neighbors": [10.0, 0.0]})["passed"] is True and L.neighbors({"neighbors": [0.0, 0.0, 10.0]})["passed"] is False   # $0 is not profitable
    for none in ({}, {"neighbors": []}):
        r = L.neighbors(none)
        assert r["passed"] is False and r["number"] == 0.0 and r["text"].startswith("2.5 FAIL no neighbor table")


def test_line_2_6_long_and_short():
    r = L.sides({"long": 500.0, "short": 20.0, "n_long": 30, "n_short": 25})
    assert r["passed"] is True and r["number"] == 20.0 and r["need"] == 0
    assert r["text"] == "2.6 PASS long $500, short $20, all variants together (need both above $0)"
    assert L.sides({"long": 500.0, "short": 0.0, "n_long": 30, "n_short": 25})["passed"] is False      # a side at exactly $0: "above"
    r = L.sides({"long": 500.0, "short": -20.0, "n_long": 30, "n_short": 25})
    assert r["passed"] is False and r["number"] == -20.0 and "short -$20" in r["text"]
    r = L.sides({"long": 500.0, "short": 0.0, "n_long": 30, "n_short": 0})                             # one-sided: judged on that side
    assert r["passed"] is True and r["number"] == 500.0 and r["text"] == "2.6 PASS long only: $500, all variants together (need above $0)"
    r = L.sides({"long": 0.0, "short": -80.0, "n_long": 0, "n_short": 12})
    assert r["passed"] is False and r["text"].startswith("2.6 FAIL short only: -$80")
    r = L.sides({"long": 0.0, "short": 0.0, "n_long": 0, "n_short": 0})
    assert r["passed"] is False and r["number"] is None and r["text"] == "2.6 FAIL no trade"


def test_line_2_7_a_filter_wins_alone():
    ok = {"c1": {"pass": True, "lift": 1.0, "p_beat": 0.99, "replicates": 4000, "real_replicates": 10, "short": 0}}
    low = {"c1": {**ok["c1"], "p_beat": 0.90}}
    f = {"name": "news days", "avg_trade": 212.0, "plain_avg_trade": 171.0, "p_beat": []}
    for none in ({}, {"filters": []}, {"filters": None, "controls": ok}):                           # no filter: the line does not apply
        r = L.filter_alone(none)
        assert r["passed"] is None and r["text"] == "2.7 n/a  no filter in this unit"
    r = L.filter_alone({"filters": [f], "controls": ok})
    assert r["passed"] is True and (r["number"], r["need"]) == (212.0, 171.0)
    assert r["text"] == "2.7 PASS news days: average trade $212 with it, $171 without (need higher)"
    r = L.filter_alone({"filters": [f], "controls": low})               # a higher average trade, but not that round's random bar
    assert r["passed"] is False and r["higher"] is True and r["random_bar"] is False and r["text"].endswith("the random bar of round 1 is not met")
    assert L.filter_alone({"filters": [f], "controls": {"c1": {**ok["c1"], "p_beat": 0.98}}, "round": 3})["passed"] is False
    r = L.filter_alone({"filters": [{**f, "avg_trade": 171.0}], "controls": ok})                    # the same average trade is not higher
    assert r["passed"] is False and r["higher"] is False and r["random_bar"] is True
    assert L.filter_alone({"filters": [{**f, "p_beat": [0.95]}], "controls": ok})["passed"] is False   # a day filter AT the bar of its day subsets
    assert L.filter_alone({"filters": [{**f, "p_beat": [0.96]}], "controls": ok})["passed"] is True
    two = [f, {"name": "thin book", "avg_trade": 150.0, "plain_avg_trade": 171.0, "p_beat": []}]     # each filter alone: the weakest is shown
    r = L.filter_alone({"filters": two, "controls": ok})
    assert r["passed"] is False and r["number"] == 150.0 and r["text"].startswith("2.7 FAIL thin book")
    r = L.filter_alone({"filters": [{"name": "orb_thin against orb", "why": "no base store"}], "controls": ok})
    assert r["passed"] is False and "no plain version" in r["text"] and "no base store" in r["text"]


def test_line_2_8_and_4_7_monte_carlo():
    def split(a, b):                                                    # `a` runs draw day 0 twice, `b` runs draw day 1 twice
        return Draws([[2, 0]] * a + [[0, 2]] * b)

    t = table([[100, -500], [100, -500], [100, -500]])                  # day 0: every variant +$100 a trade; day 1: -$500
    r = L.monte(t, split(750, 250))                                     # exactly 75 % of the runs: "or more"
    assert r["passed"] is True and r["number"] == 0.75 and r["need"] == 0.75 and r["runs"] == RUNS == 1000
    assert r["text"] == "2.8 PASS 2.1 and 2.2 both hold in 75 % of 1,000 reshuffled runs (need 75 % or more)"
    r = L.monte(t, split(749, 251))
    assert r["passed"] is False and r["number"] == 0.749 and "74.9 %" in r["text"]
    assert L.monte(table([[60, -500]] * 3), split(1000, 0))["number"] == 0.0        # 2.1 holds in every run, 2.2 ($60 < $70) in none: BOTH
    assert L.monte(table([[60, -500]] * 3, root="NQ"), split(1000, 0))["passed"] is False
    assert L.monte(table([[500, -500], [500, -500], [-90, -500], [-90, -500], [-90, -500]]), split(1000, 0))["number"] == 0.0   # floor yes, 40 % green
    mix = table([[300, 0], [300, 0], [0, 300]])                         # THE SAME DAYS FOR EVERY VARIANT: a run of day 0 leaves variant 3 flat
    assert L.monte(mix, split(600, 400))["number"] == 0.6               # day-0 runs: 2 of 3 green, $200 a trade; day-1 runs: 1 of 3 green
    tot, cnt = MC.reshuffle(mix["net"], mix["n"], split(600, 400))
    assert tot.shape == (3, 1000) and (tot[:, 0] == [600, 600, 0]).all() and (tot[:, -1] == [0, 0, 600]).all() and (cnt == 6).all()
    r = L.monte_test(t, split(900, 100))                                # 4.7: the average variant makes money in 90 % of the runs or more
    assert r["passed"] is True and r["number"] == 0.9 and r["need"] == 0.90 and r["line"] == "4.7"
    assert L.monte_test(t, split(899, 101))["passed"] is False
    assert L.monte_test(table([[60, -500]] * 3), split(1000, 0))["number"] == 1.0   # 4.7 asks for a profit, not for the floor
    # the real draws: whole days with replacement, as many as the range has; the fixed seed gives every table the same ones
    rng = np.random.default_rng(7)
    net, n = rng.normal(50, 400, (6, 40)).round(), np.ones((6, 40))
    w = MC.draw(40, MC.generator(), RUNS)
    assert w.shape == (40, RUNS) and (w.sum(0) == 40).all() and (w >= 0).all() and (w == np.round(w)).all() and (w.max(1) > 1).all()
    a, b, c = MC.reshuffle(net, n), MC.reshuffle(net, n), MC.reshuffle(net, n, MC.generator())
    assert (a[0] == b[0]).all() and (a[0] == c[0]).all() and (a[0] == np.einsum("vd,dr->vr", net, w)).all() and (a[1] == 6 * 40).all()
    assert L.monte(table(net))["number"] == L.monte(table(net))["number"] == L.monte(table(net), MC.generator())["number"]
    one = MC.generator()                                                # ONE generator carried on (funnel.py): the second table gets other days
    assert L.monte(table(net), one)["number"] == L.monte(table(net))["number"] and (MC.reshuffle(net, n, one)[0] != a[0]).any()
    assert L.monte(table(np.abs(net) + 70))["number"] == 1.0 and L.monte(table(-np.abs(net)))["number"] == 0.0


# ================================================================ (d) the command, and the seal

def _run(argv: list) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = C.main(argv)
    return rc, out.getvalue()


CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")     # plan section 8


def test_build_stored_command():
    """`bp.py build --stored`: the DRY RUN label, lines 2.1-2.8 in order, the one object of the plan's section 8 as text and as
    JSON, exit 0 = done (a line may fail) and 2 = refused, through the front door too."""
    with rule(draws=200):                                   # every store folder and every seed (the rule in force), fewer draws
        r = A.build_stored("first_bar_mom-NQ-tf15-mid")
        rc, txt = _run(["build", "--stored", "first_bar_mom-NQ-tf15|mid|"])        # the uid form of the same unit
        rj, js = _run(["build", "--stored", "first_bar_mom-NQ-tf15-mid", "--json"])
    assert list(r)[:len(CONTRACT)] == list(CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "saved", "error")] == \
        [True, "build", "first_bar_mom-NQ-tf15-mid", None, 2, None, None, [], None] and r["next"].startswith("A dry run saves nothing")
    assert r["label"] == "DRY RUN on the old build days" and r["dry_run"] is True and r["uid"] == "first_bar_mom-NQ-tf15|mid|"
    assert [x["line"] for x in r["lines"]] == ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8"]
    assert all(set(x) >= {"line", "passed", "number", "need", "text"} and x["text"].startswith(x["line"] + " ") for x in r["lines"])
    assert r["days"] == {"start": "2021-09-22", "end": STORED_END, "months": 27, "sessions": 573, "build_months": 45}
    assert r["table"] == {"store": "runs/first_bar_mom-NQ-tf15", "variants": 96, "dead": 0, "duplicates": 0}
    by = {x["line"]: x for x in r["lines"]}
    with FUNNEL.open() as fh:
        f = next(x for x in csv.DictReader(fh) if x["addr"] == r["name"])
    assert [by[k]["number"] for k in ("2.1", "2.2", "2.4", "2.5")] == [float(f[k]) for k in ("share", "avgtrade", "trades", "neighbors")]
    assert by["2.3"]["seeds"] == 10 and by["2.3"]["thin"] is False and by["2.3"]["round"] == 1
    assert list(by["2.3"]["controls"]["c1"]["stores"]) == ["runs/c1-NQ-tf15", "runs_seeds/c1-NQ-tf15-mid-build-s3to10"]
    assert by["2.4"]["on_pace"] == {"passed": True, "need": 120.0, "months": 27} and by["2.7"]["passed"] is None
    assert (r["failed"], r["failed_on_pace"], r["not_applicable"], r["thin"], r["passed"]) == (["2.8"], ["2.8"], ["2.7"], [], False)
    assert json.loads(json.dumps(r, default=lambda o: 1 / 0))["lines"][0]["line"] == "2.1"      # JSON-ready as it is
    lines = txt.rstrip("\n").split("\n")
    assert rc == 0 and lines == r["text"].split("\n") and len(lines) == 11                      # done: exit 0 although 2.8 fails
    assert lines[0] == "DRY RUN on the old build days (2021-09-22 .. 2023-12-31: 27 of the build's 45 months). Not a blueprint verdict."
    assert lines[2:10] == [x["text"] for x in r["lines"]] and lines[3] == "2.2 PASS average trade $81 (need $70)"
    assert lines[10] == "RESULT of the dry run: fails 2.8. Line 2.9 (the rounds) is not counted in a dry run."
    assert rj == 0 and json.loads(js) == json.loads(json.dumps(r)) and js.count("\n") == 1 and js.isascii()   # ONE JSON object, one line
    # 2.4 against 200 and on pace; THIN; a filter; a unit named by an out/v2 uid
    with rule(**J.AS_V2):
        r = A.build_stored("donchian_thin-NQ-tf5-nyam")     # a Level 2 option of donchian: line 2.7 applies; 161 trades on 27 months
        e = A.build_stored("E1-A-NQ")                       # straddle_tight_0830 on 08:30 release days: a day filter, random minutes
    by = {x["line"]: x for x in r["lines"]}
    assert by["2.7"]["passed"] is not None and by["2.7"]["filters"][0]["name"].startswith("donchian_thin against donchian") and r["not_applicable"] == []
    assert by["2.4"]["passed"] is False and by["2.4"]["on_pace"]["passed"] is True and "2.4" in r["failed"] and "2.4" not in r["failed_on_pace"]
    assert "with 2.4 read on pace: " in r["text"] and r["thin"] == ["2.3"] and "THIN (too few random-entry seeds): 2.3" in r["text"]
    assert e["name"] == "straddle_tight_0830-NQ-tf30-pre@A" and e["uid"] == "E1-A-NQ"
    by = {x["line"]: x for x in e["lines"]}
    assert list(by["2.3"]["controls"]) == ["shift"] and by["2.7"]["filters"][0]["name"] == "day filter A against all days" and by["2.7"]["passed"] is True
    # refusals: exit 2 with the reason, as text and as the same object with ok false; a bad command line is refused the same way
    n = 0
    for argv, word in ((["build"], "the idea's name"), (["build", "--stored", "nonsense"], "expected <family>"),
                       (["build", "--stored", "no_such_family-NQ-tf5-pm"], "no BUILD store"),
                       (["build", "--stored", "ib-NQ-tf15-nyam:mode=fade"], "no judged variant"),
                       (["build", "--stored"], "expected one argument"), (["build", "--stored", "x", "--no-such-option"], "unrecognized"),
                       (["lock", "x"], "name"), ([], "required")):                 # (the freeze of something that is no idea's name)
        rc, txt = _run(argv)
        assert rc == 2 and txt.startswith("REFUSED: ") and word in txt, (argv, txt)
        rc, js = _run(argv + ["--json"])
        d = json.loads(js)
        assert rc == 2 and list(d) == list(CONTRACT) and d["ok"] is False and word in d["error"] and (d["lines"], d["saved"], d["job"]) == ([], [], None), d
        assert d["phase"] == {"build": 2, "lock": 3}.get(d["command"]) and d["command"] == (argv[0] if argv else None) and d["text"] == txt.rstrip("\n")
        n += 1
    # the front door itself, as the connector starts it: one JSON object on stdout, exit 0; a refusal exits 2
    import subprocess
    for argv, code in ((["build", "--stored", "straddle_tight_0830-NQ-tf30-pre@A", "--json"], 0), (["build", "--stored", "nonsense", "--json"], 2)):
        q = subprocess.run([sys.executable, str(W / "bp.py"), *argv], capture_output=True, text=True, timeout=300)
        d = json.loads(q.stdout)
        assert q.returncode == code and d["ok"] is (code == 0) and d["command"] == "build" and len(d["lines"]) == (8 if code == 0 else 0), q.stderr[-400:]
    RESULTS["test_build_stored_command"] = (5 + n, 5 + n, "3 units, the refusals, the front door")


def test_only_the_old_build_days_are_read():
    """The seal. guard() refuses any store that is not inside 2021-09-22 .. 2023-12-31, and a dry run loads no other store:
    every cells.npz the judge opens for it (library.load_unit, watched here) has its range inside those days -- with every
    store folder listed, the 2024, 2025 and 2026 ones too."""
    late = [r for r in J.index() if r["end"] > STORED_END]
    assert len(late) > 100 and any(r["end"] >= "2025-07-01" for r in late)          # they are on disk, and listed
    for rec in late[:5] + [max(late, key=lambda r: r["end"]), {**late[0], "start": "", "end": ""}]:
        refused(lambda rec=rec: T.guard(rec), "stored build days only")
    refused(lambda: T.guard({**late[0], "start": "2021-09-22", "end": "2024-01-02"}), "stored build days only")
    ok = next(r for r in J.index() if r["dir"] == J.LB.RUNS)
    assert T.guard(ok) is ok
    keep, seen = J.LB.load_unit, []

    def watched(key, runs_dir=None):
        s = keep(key, runs_dir)
        seen.append((Path(runs_dir).name if runs_dir is not None else "runs", key, s["meta"]["range"]["start"], s["meta"]["range"]["end"]))
        return s

    try:
        J.LB.load_unit = watched
        J.reset()                                           # nothing in the judge's memory: every store is loaded under watch
        T._AVG.clear()
        with rule(draws=200):
            for a in ("ib-NQ-tf15-mid:mode=break", "E1-A-NQ", "donchian_thin-NQ-tf5-nyam"):     # c1 with 10 seeds · days + shift · c1 + c2 + base
                A.build_stored(a)
    finally:
        J.LB.load_unit = keep
        J.reset()
    assert len(seen) > 15 and {"runs", "runs_seeds"} == {s[0] for s in seen}, seen
    assert all("2021-09-22" <= a and b <= STORED_END for _, _, a, b in seen), [s for s in seen if s[3] > STORED_END]
    RESULTS["test_only_the_old_build_days_are_read"] = (len(seen), len(seen), "stores loaded, all inside the old build days")


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            ok, n, note = RESULTS.get(name, ("", "", ""))
            print(f"PASS {name}" + (f": {ok} of {n}" if n else "") + (f" -- {note}" if note else "") + f" ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
        except BaseException as e:                          # pytest.skip
            if type(e).__name__ != "Skipped":
                raise
            print(f"SKIP {name} ({e})", flush=True)
    sys.exit(rc)
