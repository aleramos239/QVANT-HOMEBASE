"""LOCK of THE FREEZE (blueprint/freeze.py; `bp.py lock <name>`) -- toolkit plan, step 8; BLUEPRINT.md phase 3.

(a) WHAT IT REFUSES, each before anything runs and with nothing written: no card, no build, a latest round without its
    result, a round with a failed or a missing line, a smoke run, a card changed after the round, no code check, a code
    check that is not passed (the owner has not looked: 1.5), one of another store, code that changed since the home store
    was written without line 1.6, a job of the idea that is still running.
(b) THE WORSE-FILLS TABLE of the build days (runner.run_worse): the engine's STRESS + the 100 ms late cancel for a two-sided
    bracket and nothing else; the home session's instance; its own store and ledger row; never run twice. On build days it
    is trade for trade what the old worse-fills stores hold (two-sided: orb; one-sided: first_bar_mom).
(c) THE DEFAULT = the middle one, by build net, of the variants that make money on build AND on build with worse fills.
(d) THE LOCK: every part the law names (3.1), the test range frozen per market, one hash over all of it, saved through the
    app's idea store; the hash changes when anything in it changes, and freeze.verify names a store file, a code file, the
    card or the lock itself that no longer matches.
(e) THE TEST RANGE of a market: the first test day .. the last session of the unbroken run of complete sessions (a fake
    archive in a temp folder: file names and manifests only).
(f) THE COMMAND LINE as the connector writes it (`lock <name> --root=DIR --json`): the pass runs as a job, a second `lock`
    picks its wait back up, a frozen idea is shown again and nothing is written.

TINY RUNS ONLY, on build days (tests/blueprint_frozen.py); the idea of this file is its own (bpl_lok: no other test file
writes its stores, whatever the order they run in). No day on or after 2025-07-01 is opened: the last test looks at
every engine call. No P&L is asserted: counts, identities, the shape of what is saved.
  pytest tests/test_blueprint_lock.py -q        python tests/test_blueprint_lock.py     one line per test
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_frozen as F  # noqa: E402

import judge as J  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import jobs as JOBS  # noqa: E402
from blueprint import lines as L  # noqa: E402
from blueprint import mc as MC  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import numpy as np  # noqa: E402

NAME, KEY, WORSE = "bpl_lok", "bpl_lok-NQ-tf15", "bpl_lok-NQ-tf15-nyam-worse"
IS = F.IS
RESULTS: dict = {}
CALLS: list = []                                    # every engine call of this module: (days, keywords)
_RUN_MANY = S.run_many


def _watched(specs, *a, **k):
    CALLS.append({"args": a, **{x: k.get(x) for x in ("period", "days", "allow_holdout", "allow_exam", "allow_check", "slip_ticks", "latency_ms", "costs", "root")}})
    return _RUN_MANY(specs, *a, **k)


def setup_function(_=None):
    F.env_on()
    S.run_many = _watched


def teardown_function(_=None):
    S.run_many = _RUN_MANY
    F.env_off()


def _job_file(root: Path, name: str, state: str) -> Path:
    jd = root / "_jobs" / "20260101T000000-abc123"
    jd.mkdir(parents=True, exist_ok=True)
    (jd / "job.json").write_text(json.dumps({"id": jd.name, "command": "build", "name": name, "state": state, "pid": os.getpid(), "args": {}}))
    return jd


# ================================================================ (a) what it refuses

def box(day, trades=None, open_=None) -> dict:
    """Box data by hand: the default variant's net per session day (its trades: one a day with a net, or as listed) and each
    day's worst open loss (not given: none, the day never stood under its start)."""
    day = np.asarray(day, float)
    return {"trades": day[day != 0] if trades is None else np.asarray(trades, float), "day": day, "n": (day != 0).astype(float),
            "open": np.zeros(len(day)) if open_ is None else np.asarray(open_, float)}


def test_lines_3_3_to_3_8_on_the_default_variant_alone():
    assert [f(box([100.0, -50.0, 80.0]))["line"] for f in L.BOX] == [f"3.{i}" for i in range(3, 9)] == [k for k in R.lines() if k.startswith("3.")][2:]
    # 3.3 profit factor: winning trades / losing trades, 1.2 or more
    r = L.box_pf(box([120.0, -100.0]))
    assert r["passed"] is True and (r["number"], r["need"]) == (1.2, 1.2) and r["text"] == "3.3 PASS default variant: profit factor 1.20 over 2 trades (need 1.2 or more)"
    assert L.box_pf(box([119.0, -100.0]))["passed"] is False and L.box_pf(box([5.0, 7.0]))["passed"] is True and L.box_pf(box([0.0, 0.0]))["passed"] is False
    assert L.box_pf(box([0.0], trades=[300.0, -200.0, -40.0]))["number"] == 1.25             # read on the TRADES, not on the days
    # 3.4 net / worst drawdown, 3 or more: +400, then -100 (the drawdown), then +0 = 300 / 100
    r = L.box_ratio(box([400.0, -100.0, 0.0]))
    assert r["passed"] is True and (r["number"], r["net"], r["drawdown"]) == (3.0, 300.0, 100.0)
    assert r["text"] == "3.4 PASS default variant: net $300 / worst drawdown $100 = 3.00, open losses counted (need 3 or more)"
    # ... OPEN LOSSES COUNTED: the same three closes, but day 3 stood $150 under its start (300 - 150 = 150, $250 under the high of 400)
    r = L.box_ratio(box([400.0, -100.0, 0.0], open_=[0.0, 0.0, 150.0]))
    assert r["passed"] is False and (r["net"], r["drawdown"], r["number"]) == (300.0, 250.0, 1.2)
    assert L.box_ratio(box([400.0, -100.0, 0.0], open_=[0.0, 90.0, 0.0]))["drawdown"] == 100.0    # an open loss the close went under anyway adds nothing
    assert L.box_ratio(box([400.0, 50.0], open_=[30.0, 0.0]))["drawdown"] == 30.0                  # day 1: from the $0 it starts at, whatever it closes at
    assert L.box_ratio(box([400.0, 50.0], open_=[0.0, 30.0]))["drawdown"] == 30.0                  # the high trails the CLOSES: day 2 starts at its high
    assert L._drawdown([], []) == 0.0
    assert L.box_ratio(box([400.0, -101.0, 0.0]))["passed"] is False
    assert L.box_ratio(box([-100.0, 500.0]))["drawdown"] == 100.0                             # a loss from the start counts: the high it falls from is $0
    assert L.box_ratio(box([50.0, 60.0]))["passed"] is True and "no drawdown" in L.box_ratio(box([50.0, 60.0]))["text"] and L.box_ratio(box([-5.0, -6.0]))["passed"] is False
    # 3.5 Sharpe on EVERY session day (a day without a trade is $0), per year, 1 or more
    d = np.array([100.0, -50.0, 80.0, 0.0, 60.0, -40.0])
    r = L.box_sharpe(box(d))
    assert r["number"] == float(d.mean() / d.std(ddof=1) * np.sqrt(252)) and r["passed"] is True and r["days"] == 6 and R.rule("3.5")["also"]["days_per_year"] == 252
    assert L.box_sharpe(box([10.0, -10.0, 10.0, -10.0, 1.0]))["passed"] is False and L.box_sharpe(box([5.0]))["passed"] is False and L.box_sharpe(box([5.0, 5.0]))["passed"] is False
    # 3.6 the worst drawdown at 1 micro (a tenth of the contract) UNDER the account's limit: $20,000 at one contract is AT the limit
    need = R.need("3.6")
    assert need == {"micros": 1, "limit": 2000, "account": "LucidPro 50K"} and R.template("sizes")["micros_per_contract"] == 10
    r = L.box_fits(box([30000.0, -19999.0, 5.0]))
    assert r["passed"] is True and r["number"] == 1999.9
    assert r["text"] == "3.6 PASS default variant: worst drawdown $1,999.90 at 1 micro, open losses counted (need under $2,000, the limit of LucidPro 50K)"
    assert L.box_fits(box([30000.0, -20000.0, 5.0]))["passed"] is False and L.box_fits(box([10.0, 20.0]))["number"] == 0.0
    assert L.box_fits(box([30000.0, 5.0, 5.0], open_=[0.0, 20000.0, 0.0]))["passed"] is False      # three winning days: only the open loss says it
    assert "open losses counted" in R.rule("3.4")["text"] and "open losses counted" in R.rule("3.6")["text"]
    # 3.7 Monte Carlo on its own days: money in 80 % of the reshuffled runs or more (the draws of line 2.8)
    r = L.box_monte(box([60.0, 10.0, 5.0, 20.0, 30.0, 15.0]))
    assert r["passed"] is True and (r["number"], r["need"], r["runs"]) == (1.0, 0.8, 1000) and "100 % of 1,000 reshuffled runs" in r["text"]
    assert r["text"].endswith("(need 80 % or more)")
    r = L.box_monte(box([400.0, -100.0, -100.0, -100.0, -100.0, 50.0]))                       # a profit that hangs on one day
    assert r["passed"] is False and 0.3 < r["number"] < 0.8
    one = np.array([400.0, -100.0, -100.0, -100.0, -100.0, 50.0])
    assert r["number"] == float((MC.reshuffle(one[None, :], np.ones((1, 6)))[0][0] > 0).mean())      # the same runs as the table's (mc.py: the fixed seed)
    # 3.8 its net without its best 1 % of days (6 days: 1 day out), above $0 -- the same profit that hangs on one day: $50 - $400 = -$350 is left
    r = L.box_best_days(box(one))
    assert r["passed"] is False and (r["number"], r["need"], r["best"], r["count"], r["days"]) == (-350.0, 0, [400.0], 1, 6)
    assert r["text"] == "3.8 FAIL default variant: -$350 without its best 1 % of days (1 of 6 session days; they made $400 of $50; need above $0)"
    assert L.box_best_days(box([60.0, 10.0, 5.0, 20.0, 30.0, 15.0]))["number"] == 80.0 and R.need("3.8") == {"best_share": 0.01, "above": 0}


def test_the_freeze_is_refused_when_the_default_variant_fails_a_line_of_its_own():
    """The law, as it stands outside a test run: one of the lines 3.3-3.8 not met = nothing is frozen. (The fixtures' tiny
    runs say `box: "said"`: the lines are read and kept and do not refuse -- a 3-day table cannot pass them on its own.)"""
    F.fbm()
    root = F.fresh(F.FBM, "boxno")
    with F.tiny(**{**F.settings(F.FBM), "box": None, "build_avg_trade": None}):
        why = F.refused(lambda: FRZ.lock(F.FBM, root), "does not meet every line read on it before the freeze")
    assert "3.7 FAIL default variant: makes money in " in why and "nothing is frozen" in why and "a new round when one is left" in why
    assert not (root / F.FBM / "lock.json").exists()
    with F.tiny(**F.settings(F.FBM)):                                                          # the same idea, said: frozen, with the lines as they read
        lock = FRZ.lock(F.FBM, root)["lock"]
    b = {x["line"]: x for x in lock["box"]}
    assert list(b) == [f"3.{i}" for i in range(3, 9)] and b["3.7"]["passed"] is False and b["3.7"]["text"].startswith("3.7 FAIL ")
    assert lock["build"] == {"avg_trade": 100.0}                                               # (the fixture's figure; without one: line 2.2's number, below)


def test_what_a_freeze_refuses():
    root = F.fresh(NAME, "refuse")
    d, build, n = root / NAME, root / NAME / "rounds" / "1" / "build.json", 0
    was, good = F.tree(d), F.read(build)

    def no(word: str) -> str:
        nonlocal n
        n += 1
        with F.tiny(), F.no_engine():
            why = F.refused(lambda: FRZ.lock(NAME, root), word)
        assert not (d / "lock.json").exists(), word
        return why

    with F.tiny(), F.no_engine():
        F.refused(lambda: FRZ.lock("bpl_nobody", root), "no card")
        F.refused(lambda: FRZ.lock("Bad Name", root), "name")
    # ---- the code check (phase 1) stands for the home store of the round, with every line that is read true
    (d / "check.json").unlink()
    assert "code-check bpl_lok --store=bpl_lok-NQ-tf15" in no("no code check")
    F.hand_check(NAME, root, KEY, looked=False)
    assert "--looked" in no("1.5")                                               # the owner has not looked at the 10 trades
    F.hand_check(NAME, root, KEY, marks={"1.2": False})
    no("1.2")
    F.hand_check(NAME, root, KEY, marks={"1.6": False})                          # the earlier trade list was NOT reproduced
    no("1.6")
    F.hand_check(NAME, root, "bpl_other-NQ-tf15")                                # a passed check -- of another store
    assert "runs/bpl_lok-NQ-tf15" in no("not of the home store")
    F.hand_check(NAME, root, KEY, source={"kind": "trades", "where": str(F.tmp() / "trades.json")})
    no("not of the home store")
    F.hand_check(NAME, root, KEY)
    keep = RUN.code
    try:                                                                         # the code changed since the store was written: line 1.6 first
        RUN.code = lambda family=None: {**keep(family), "l2sim.py": "0" * 16}
        assert "--same-as=bpl_lok-NQ-tf15" in no("l2sim.py changed since")
        fresh = str(F.tmp() / "runs_fresh" / KEY)                                # ... a fresh run that reproduced the home store trade for trade: accepted
        F.hand_check(NAME, root, KEY, marks={"1.6": True}, source={"kind": "store", "where": fresh}, asked={"store": fresh, "same_as": str(F.OUT / KEY)})
        with F.tiny(), F.no_engine():
            assert FRZ.start(NAME, root)["heavy"] is True
    finally:
        RUN.code = keep
    F.hand_check(NAME, root, KEY)
    # ---- the build (phase 2): the LATEST round, every line 2.1-2.9, a run that counts
    bad = dict(good, lines=[{**x, "passed": False} if x["line"] == "2.4" else x for x in good["lines"]])
    build.write_text(json.dumps(bad))
    assert "2.4" in no("fails 2.4")
    with F.tiny(), F.no_engine():                                                # waive=: a keyword of the code (the pipeline's, for the other markets' 2.5)
        F.refused(lambda: FRZ.start(NAME, root, waive=("2.5",)), "fails 2.4")   # ... it waives the lines it names and no other
        got = FRZ.start(NAME, root, waive=("2.4",))
        assert got["waived"] == ["2.4"] and got["frozen"] is False
        build.write_text(json.dumps(good))
        assert "waived" not in FRZ.start(NAME, root, waive=("2.4",))             # a line that passed is not waived: nothing is written down
    build.write_text(json.dumps(dict(good, lines=[x for x in good["lines"] if x["line"] != "2.8"])))
    no("no line 2.8")
    build.write_text(json.dumps(dict(good, dry_run=True)))
    no("no build that counts")
    build.write_text(json.dumps(good))
    IS.write_reason(NAME, 2, "a second thought", root)                           # round 2 was started: its reason is on file, it has no result
    IS.write_round_spec(NAME, 2, F.read(d / "rounds" / "1" / "spec.json"), root)
    no("round 2")
    shutil.rmtree(d / "rounds" / "2")
    spec = F.read(d / "spec.json")
    (d / "spec.json").write_text(json.dumps({**spec, "card": {**spec["card"], "neighbors": ["midday", "afternoon"]}}))
    no("changed after round 1")                                                  # the card on file is not the rule that passed the build
    (d / "spec.json").write_text(json.dumps(spec))
    jd = _job_file(root, NAME, "running")                                        # a job of the idea is at work
    assert jd.name in no("still running")
    shutil.rmtree(root / "_jobs")
    # ---- an idea without a build at all
    REC.card("bpl_new", F.idea("bpl_new"), root)
    with F.tiny(), F.no_engine():
        F.refused(lambda: FRZ.lock("bpl_new", root), "no build on file")
    IS.refresh(NAME, root)
    assert F.tree(d) == was and IS.status(NAME, root) == "lead" and IS.read_idea(NAME, root)["phase"] == 2       # no refusal left a trace
    with F.tiny(), F.no_engine():
        assert FRZ.start(NAME, root)["frozen"] is False                          # ... and it can be frozen as it stands
    RESULTS["test_what_a_freeze_refuses"] = (n + 4, n + 4, "refusals, each before anything runs and with nothing written")


# ================================================================ (b) the worse-fills table of the build days

def test_the_worse_fills_are_the_engines_stress_and_the_late_cancel():
    w, eng = R.template("costs")["worse"], RUN._engine
    assert RUN.worse_kw(True) == {"slip_ticks": w["slip_ticks"], "latency_ms": w["latency_ms"], "oco_cancel_ms": w["oco_cancel_ms"]}
    assert RUN.worse_kw(False) == dict(S.STRESS) == {"slip_ticks": 2.0, "latency_ms": 250} and w["oco_cancel_ms"] == J.OCO_MS == 100
    assert RUN.worse_words(RUN.worse_kw(True)) == "2 ticks + 250 ms + a 100 ms late cancel" and RUN.worse_words(RUN.worse_kw(False)) == "2 ticks + 250 ms"
    kw = eng(RUN.worse_kw(True))                                                 # as the engine takes them: the late cancel is a field of its Costs
    assert (kw["slip_ticks"], kw["latency_ms"], kw["costs"].oco_cancel_ms, set(kw)) == (2.0, 250, 100, {"slip_ticks", "latency_ms", "costs"})
    assert eng(RUN.worse_kw(False)) == dict(S.STRESS) and eng({}) == {} and RUN.worse_key("x-NQ-tf15", "mid") == "x-NQ-tf15-mid-worse"
    assert (RUN.WORSE, RUN.STAGE) == ("bp_build_worse", {"unit": "bp_build", "pool": "null_bp"})


OLD = [  # (family, market, bar, session, values of its main setting, the old worse-fills stores of BUILD days and days of each)
    ("orb", "pre", {"or_min": ["5", "15", "30"]}, [("runs_v2", "orb-NQ-tf15-pre-pick-stress", ["2024-03-15", "2024-09-18"]),
                                                   ("runs_check2025", "orb-NQ-tf15-pre-check-stress", ["2025-03-27", "2025-06-30"])], 100),
    ("first_bar_mom", "mid", {"k": [1.0, 1.5, 2.0]}, [("runs_v2", "first_bar_mom-NQ-tf15-mid-pick-stress", ["2024-03-15", "2024-09-18"]),
                                                      ("runs_check2025", "first_bar_mom-NQ-tf15-mid-check-stress", ["2025-03-27", "2025-06-30"])], 0)]


def test_the_worse_fills_table_is_trade_for_trade_what_the_old_stores_hold():
    """Two-sided (orb: + the late cancel) and one-sided (first_bar_mom: without it), on 4 BUILD days of 2024 and 2025 H1."""
    import numpy as np
    n = cells = 0
    for family, sess, params, stores, oco in OLD:
        if not all((LB.W / d / k / "run.json").exists() for d, k, _ in stores):
            continue
        days = sorted(x for _, _, ds in stores for x in ds)
        spec = {"name": f"bpl_w{family[:3]}", "reason": "The worse-fills table of the freeze, held against the stores of the old worse-fills runs.",
                "family": family, "markets": ["NQ"], "bar_sizes": ["15"], "sessions": [sess], "params": params, "filters": [], "exits": "standard", "limits": {}}
        key, out, led = f"{spec['name']}-NQ-tf15", F.tmp() / "runs_old", F.tmp() / "ledger_old.csv"
        with F.tiny():
            got = RUN.run_worse(spec, key, sess, 1, out, ledger=led, days=days, cells=F.CELLS)
        m = F.read(out / got[0]["key"] / "run.json")
        assert (got[0]["kind"], got[0]["stage"], m["run_kw"].get("oco_cancel_ms", 0), m["both_sides_declared"]) == ("worse", "bp_build_worse", oco, bool(oco))
        mine = LB.load_unit(got[0]["key"], out)
        for d, k, ds in stores:
            old, ords = LB.load_unit(k, LB.W / d), [dt.date.fromisoformat(x).toordinal() for x in ds]
            assert int(old["meta"].get("oco_cancel_ms") or 0) == oco and old["meta"]["stress"] is True
            for c in m["cells"]:
                a, b = LB.unit_cell(mine, c["id"]), LB.unit_cell(old, c["id"])
                ma, mb = np.isin(a["date"], ords), np.isin(b["date"], ords) & (b["sess"] == LB.SESS_CODE[sess])
                assert sorted(zip(a["entry_ms"][ma].tolist(), np.round(a["net"][ma], 2).tolist())) == sorted(zip(b["entry_ms"][mb].tolist(), np.round(b["net"][mb], 2).tolist())), \
                    f"{d}/{k} cell {c['id']} differs"
                n, cells = n + int(mb.sum()), cells + 1
    if not cells:
        import pytest
        pytest.skip("the old worse-fills stores are not on this machine")
    assert n > 0
    RESULTS["test_the_worse_fills_table_is_trade_for_trade_what_the_old_stores_hold"] = (cells, cells, f"cell x store comparisons on build days, {n} stored trades")


# ================================================================ (c) the default variant

def test_the_default_is_the_middle_of_the_variants_that_also_survive_worse_fills():
    rows = [{"id": "a", "net": 50.0, "vi": 0, "xi": 0}, {"id": "b", "net": -10.0, "vi": 0, "xi": 1}, {"id": "c", "net": 300.0, "vi": 1, "xi": 0},
            {"id": "d", "net": 120.0, "vi": 1, "xi": 1}, {"id": "e", "net": 0.0, "vi": 2, "xi": 0}, {"id": "f", "net": 80.0, "vi": 2, "xi": 1}]
    ids = [x["id"] for x in rows]
    assert REC.middle(rows, ids) == ("f", ["a", "f", "d", "c"])                  # on build alone (what a build shows)
    worse = {"a": 5.0, "b": 40.0, "c": 150.0, "d": -1.0, "e": 9.0, "f": 0.0}     # d loses with worse fills, f makes nothing: both are out
    assert REC.middle(rows, ids, worse) == ("a", ["a", "c"])                     # 2 survivors: the lower of the two middle ones, never the best
    assert REC.middle(rows, ids, {**worse, "f": 0.01}) == ("f", ["a", "f", "c"])
    assert REC.middle(rows, ids, {k: -1.0 for k in ids}) == (None, [])           # nothing survives: there is no default
    assert REC.middle(rows, ids, {**worse, "b": 999.0})[1] == ["a", "c"]         # a variant that loses on build is never in, whatever its worse fills say
    assert REC.middle(rows, ids, {k: 1.0 for k in ids}) == REC.middle(rows, ids)  # the ORDER is the build net's, not the worse fills'


# ================================================================ (d) the lock

KEYS = ["name", "version", "locked_utc", "round", "store", "spec", "plan", "home", "variants", "default", "survivors", "default_rule", "box", "prop", "build", "costs", "control",
        "montecarlo", "code", "stores", "test_range", "hash"]


def _locked() -> tuple:
    if "lock" not in RESULTS:
        root = F.fresh(NAME, "lock")
        before, k = F.tree(root / NAME), len(CALLS)
        with F.tiny():
            r = FRZ.lock(NAME, root)
        RESULTS["lock"] = (root, r, before, CALLS[k:])
    return RESULTS["lock"]


def test_the_freeze_saves_everything_under_one_hash():
    root, r, before, calls = _locked()
    d, lock = root / NAME, F.read(root / NAME / "lock.json")
    assert list(r)[:len(F.CONTRACT)] == list(F.CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "error")] == [True, "lock", NAME, "lead", 3, 1, None, None]
    assert r["lock"] == lock and list(lock) == KEYS and (lock["name"], lock["version"], lock["round"], lock["store"]) == (NAME, 1, 1, NAME)
    assert (r["hash"], r["default"], r["already"], r["matches"], r["mismatches"]) == (lock["hash"], lock["default"], False, True, [])
    # 3.1 the rule
    spec = F.read(d / "spec.json")
    assert lock["spec"] == {k: spec[k] for k in ("name", "version", "card", "run")} and lock["plan"] == F.read(d / "rounds/1/spec.json")["plan"]
    assert lock["home"] == {"market": "NQ", "session": "nyam", "bar": "15", "table": "NQ-tf15-nyam", "unit": "bpl_lok-NQ-tf15-nyam", "uid": "bpl_lok-NQ-tf15|nyam|",
                            "key": KEY, "folder": str(F.OUT), "filter": None, "worse": WORSE}
    # ... the variant list = the variants judged on build; the default = the middle survivor of build AND build with worse fills
    sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
    u = T.bp_unit(sp, "NQ", "15", "nyam")
    st, wst = J.store({"dir": F.OUT, "key": KEY}), J.store({"dir": F.OUT, "key": WORSE})
    rows = J.table(st, u)
    ids = J.table_stats(rows)["ids"]
    wnet = {c: float(J.cellx(wst, c, "nyam", u)["net"].sum()) for c in ids}
    assert lock["variants"] == ids and len(ids) == r["variants"] == F.read(d / "rounds/1/build.json")["table"]["variants"]
    assert (lock["default"], lock["survivors"]) == REC.middle(rows, ids, wnet) and lock["default"] in lock["survivors"] and r["survivors"] == len(lock["survivors"])
    assert lock["default_rule"] == J.TIE_RULE and set(lock["survivors"]) <= set(REC.middle(rows, ids)[1])
    # ... the costs and the control
    assert lock["costs"] == {"normal": R.template("costs")["normal"], "worse": {"slip_ticks": 2.0, "latency_ms": 250, "oco_cancel_ms": 100, "two_sided": True}}
    c = lock["control"]
    assert (c["kind"], c["pool"], c["seeds"], c["draws"]) == ("c1", "c1-NQ-tf15", list(range(1, 11)), 200)       # (200: the draws of the test run; the law's 4,000 otherwise)
    assert c["draw_seed"] == {"build": J.seed_of(u["uid"], "bp_build-c1"), "test": J.seed_of(u["uid"], "test-c1")} and c["draw_seed"]["build"] != c["draw_seed"]["test"]
    assert lock["montecarlo"] == {"runs": 1000, "seed": R.template("montecarlo")["seed"]}
    # ... the code, the stores, the test range, one hash over all of it
    assert lock["code"] == RUN.code("orb") and set(lock["code"]) == {"l2sim.py", "l2ref.py", "families/blocks.py", "families/port1.py", "flowtab.py", "bpfeat.py", "levels.py", "zones.py", "indicators.py"}
    assert list(lock["stores"]) == [KEY, WORSE, "c1-NQ-tf15"] and all(v == FRZ.store_hash(F.OUT, k) for k, v in lock["stores"].items())
    assert all(set(v) == {"folder", "inputs_hash", "run", "cells"} and len(v["run"]) == len(v["cells"]) == 16 for v in lock["stores"].values())
    assert lock["test_range"] == {"NQ": RUN.test_range("NQ")} == r["test_range"] and lock["test_range"]["NQ"]["start"] == R.template("ranges")["test"]["start"] == "2025-07-01"
    assert r["range"] == {"market": "NQ", "start": "2025-07-01", "end": lock["test_range"]["NQ"]["end"]} and lock["test_range"]["NQ"]["end"] >= "2026-01-02"
    assert lock["hash"] == FRZ.digest(lock) and len(lock["hash"]) == 16 and FRZ.verify(lock, spec) == []
    # saved through the app's idea store: phase 3, still a lead (the status is what the saved results say), the event on its log
    assert F.tree(d) == sorted(before + ["lock.json"]) and sorted(r["saved"]) == sorted([str(F.OUT / WORSE), str(d / "lock.json")])
    got = IS.read_idea(NAME, root)
    assert (got["status"], got["phase"], got["round"], IS.status(NAME, root)) == ("lead", 3, 1, "lead")
    log = [json.loads(x) for x in (d / "log.jsonl").read_text().splitlines()]
    assert log[-1]["event"] == "locked" and (log[-1]["hash"], log[-1]["default"], log[-1]["round"]) == (lock["hash"], lock["default"], 1)
    # the answer: lines 3.1 and 3.2, the hash, the default and the test range in words, the next step
    b = F.by(r)
    assert [x["line"] for x in r["lines"]] == [f"3.{i}" for i in range(1, 9)] and all(x["passed"] is True and x["text"].startswith(x["line"] + " PASS ") for x in r["lines"])
    assert lock["default"] in b["3.1"]["text"] and "never the best" in b["3.1"]["text"] and "2 ticks + 250 ms + a 100 ms late cancel" in b["3.1"]["text"]
    assert lock["hash"] in b["3.2"]["text"] and "new version" in b["3.2"]["text"]
    text = r["text"].split("\n")
    assert text[0].startswith(f"FROZEN now: {NAME} · lock {lock['hash']} · version 1 · round 1 · home NQ New York morning 15-minute bars")
    assert f"DEFAULT VARIANT {lock['default']}" in r["text"] and f"TEST RANGE NQ 2025-07-01 .. {lock['test_range']['NQ']['end']}" in r["text"] and "read ONCE" in r["text"]
    assert "test bpl_lok --confirm" in r["next"] and "ONE read" in r["next"] and "\n" not in r["next"]
    assert json.loads(json.dumps(r)) == r                                         # JSON as it is: a job keeps it, the connector reads it
    # the pass: ONE worse-fills pass on the build switch, the named build days, the home session -- 2 ticks, 250 ms, the 100 ms late cancel
    assert len(calls) == 1 and calls[0]["period"] == "bp_build" and calls[0]["days"] == F.DAYS and calls[0]["args"] == ()
    assert (calls[0]["slip_ticks"], calls[0]["latency_ms"], calls[0]["costs"].oco_cancel_ms) == (2.0, 250, 100)
    assert not any(calls[0][k] for k in ("allow_holdout", "allow_exam", "allow_check"))
    m = F.read(F.OUT / WORSE / "run.json")
    assert (m["stage"], m["period"], m["sessions"], m["worse_of"], m["days"], len(m["cells"])) == ("bp_build_worse", "bp_build", ["nyam"], KEY, F.DAYS, 6)
    assert all(c["inputs"]["sess"] == "nyam" for c in m["cells"]) and (WORSE, "bp_build_worse", "grid") in [(x["key"], x["stage"], x["kind"]) for x in LB.read_ledger(F.LEDGER)]
    RESULTS["test_the_freeze_saves_everything_under_one_hash"] = (len(KEYS), len(KEYS), "parts of the lock, one hash over all of them")


def test_choose_takes_the_pipelines_pick_only_among_the_survivors():
    """freeze._choose: the middle survivor (as before), or -- with `pick`, a keyword of the CODE: the pipeline's variant mode -- the picked
    cell, which has to be a judged variant that makes money on build AND with worse fills."""
    rows = [{"id": "a", "net": 50.0, "vi": 0, "xi": 0}, {"id": "b", "net": -10.0, "vi": 0, "xi": 1}, {"id": "c", "net": 300.0, "vi": 1, "xi": 0},
            {"id": "d", "net": 120.0, "vi": 1, "xi": 1}, {"id": "e", "net": 0.0, "vi": 2, "xi": 0}, {"id": "f", "net": 80.0, "vi": 2, "xi": 1}]
    ids, worse = [x["id"] for x in rows], {"a": 5.0, "b": 40.0, "c": 150.0, "d": -1.0, "e": 9.0, "f": 0.0}
    assert FRZ._choose(rows, ids, worse, None, "t") == ("a", ["a", "c"], J.TIE_RULE)                    # no pick: the middle survivor, the old rule
    d, surv, rule = FRZ._choose(rows, ids, worse, "c", "t")                                           # the best survivor, picked by the pipeline: taken
    assert (d, surv) == ("c", ["a", "c"]) and rule != J.TIE_RULE and "picked by the pipeline" in rule and "c" in rule and "never the best" in rule
    assert FRZ._choose(rows, ids, worse, "a", "t")[0] == "a"
    for cell, word in (("d", "worse fills"), ("b", "makes money on build"), ("e", "makes money on build"), ("zz", "judged variant")):
        try:
            FRZ._choose(rows, ids, worse, cell, "t")
        except J.Refuse as e:
            assert cell in str(e) and word in str(e) and "picked" in str(e), str(e)
        else:
            raise AssertionError(f"{cell} was taken")
    try:
        FRZ._choose(rows, ids, {k: -1.0 for k in ids}, "a", "t")                                     # nothing survives at all: the old refusal
    except J.Refuse as e:
        assert "not a variant that makes money" in str(e)
    else:
        raise AssertionError("no survivor, no default")


def test_a_default_the_pipeline_picked_is_locked_with_its_words_and_the_hash_over_them():
    root0, r0, _, _ = _locked()
    lock0 = r0["lock"]
    pick = lock0["default"]
    with F.tiny(), F.no_engine():
        assert FRZ.start(NAME, F.fresh(NAME, "pick_start"), default=pick)["default"] == pick      # (start keeps it for run: a job keeps its arguments)
        assert "default" not in FRZ.start(NAME, F.fresh(NAME, "pick_start0"))                      # no pick: no key
    root = F.fresh(NAME, "pick")
    with F.tiny():
        r = FRZ.lock(NAME, root, default=pick)
    lock = F.read(root / NAME / "lock.json")
    assert lock["default"] == pick == r["default"] and lock["survivors"] == lock0["survivors"] and lock["variants"] == lock0["variants"]
    assert lock["default_rule"] != J.TIE_RULE and "picked by the pipeline" in lock["default_rule"] and pick in lock["default_rule"]
    assert FRZ.verify(lock, F.read(root / NAME / "spec.json")) == [] and lock["hash"] == FRZ.digest(lock) and lock["hash"] != lock0["hash"]
    assert [x["line"] for x in r["lines"]] == [f"3.{i}" for i in range(1, 9)] and "picked by the pipeline" in F.by(r)["3.1"]["text"]
    assert f"DEFAULT VARIANT {pick}: picked by the pipeline" in r["text"]
    fresh = F.fresh(NAME, "pick_no")                                                              # a cell that is no variant: refused, nothing written
    before = F.tree(fresh / NAME)
    with F.tiny():
        F.refused(lambda: FRZ.lock(NAME, fresh, default="no_such_cell"), "judged variant")
    assert not (fresh / NAME / "lock.json").exists() and F.tree(fresh / NAME) == before
    assert lock0["default_rule"] == J.TIE_RULE                                                    # every other caller: the middle survivor


def test_a_frozen_idea_stays_as_it_is():
    root, r, _, _ = _locked()
    d = root / NAME
    stamp, was = (d / "lock.json").stat().st_mtime_ns, F.tree(d)
    with F.tiny(), F.no_engine():
        again = FRZ.lock(NAME, root)                                             # `lock` again: the lock on file, nothing written, nothing run
        assert (again["already"], again["hash"], again["saved"], again["matches"], again["lock"]) == (True, r["hash"], [], True, r["lock"])
        assert again["text"].split("\n")[0].startswith(f"FROZEN already: {NAME} · lock {r['hash']}") and "The lock matches the files on disk" in again["text"]
        assert (d / "lock.json").stat().st_mtime_ns == stamp and F.tree(d) == was
        F.refused(lambda: REC.card(NAME, F.idea(NAME), root), "frozen")          # 3.2: from here nothing changes
        F.refused(lambda: REC.build(NAME, "one more round", root=root), "frozen")
    st = REC.status(NAME, root)
    assert (st["status"], st["phase"]) == ("lead", 3) and "FROZEN" in st["next"] and "--confirm" in st["next"]
    # a store the freeze rests on that OTHER code wrote than the code that is frozen (a control pool is written once): said, with line 1.6
    with F.no_engine():
        odd = FRZ._result(NAME, root, {**r["lock"], "code": {**r["lock"]["code"], "l2sim.py": "0" * 16}}, True, [], [])
    assert [n for n in odd["notes"] if n.startswith("c1-NQ-tf15 was written by an earlier l2sim.py") and "line 1.6" in n] and odd["matches"] is False
    assert again["notes"] == [] and f"NOTE: {odd['notes'][0]}." in odd["text"].split("\n")
    rc, js = F.run_cli(["status", f"--root={root}", "--json"])
    assert rc == 0 and "FROZEN" in json.loads(js)["ideas"][0]["next"]


def test_the_hash_changes_when_anything_in_the_lock_changes():
    _, r, _, _ = _locked()
    lock = r["lock"]
    edits = [("default", lock["variants"][0] if lock["variants"][0] != lock["default"] else lock["variants"][1]), ("variants", lock["variants"][::-1]),
             ("survivors", []), ("version", 2), ("round", 2), ("locked_utc", "2026-10-07T00:00:00+00:00"),
             ("costs", {**lock["costs"], "worse": {**lock["costs"]["worse"], "slip_ticks": 1.0}}), ("control", {**lock["control"], "draws": 4000}),
             ("control", {**lock["control"], "draw_seed": {**lock["control"]["draw_seed"], "test": 1}}), ("code", {**lock["code"], "l2sim.py": "0" * 16}),
             ("stores", {**lock["stores"], KEY: {**lock["stores"][KEY], "cells": "0" * 16}}),
             ("test_range", {"NQ": {**lock["test_range"]["NQ"], "end": "2026-09-23"}}), ("spec", {**lock["spec"], "run": {**lock["spec"]["run"], "limits": {"max_tr": 1}}})]
    seen = {lock["hash"]}
    for k, v in edits:
        h = FRZ.digest({**lock, k: v})
        assert h not in seen and len(h) == 16, k
        seen.add(h)
    assert FRZ.digest({**lock, "hash": "anything"}) == lock["hash"] and FRZ.digest(json.loads(json.dumps(lock))) == lock["hash"]      # ... and only then
    assert FRZ.digest(dict(reversed(list(lock.items())))) == lock["hash"]                                                            # (the order of the keys is no change)
    RESULTS["test_the_hash_changes_when_anything_in_the_lock_changes"] = (len(edits), len(edits), "changes, each another hash")


def test_verify_names_the_file_that_no_longer_matches():
    root, r, _, _ = _locked()
    spec, copy = F.read(root / NAME / "spec.json"), F.tmp() / "runs_changed"
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(F.OUT, copy)
    lock = json.loads(json.dumps(r["lock"]).replace(json.dumps(str(F.OUT)), json.dumps(str(copy))))       # the same lock over a copy of its stores
    lock["hash"] = FRZ.digest(lock)
    assert lock["home"]["folder"] == str(copy) and FRZ.verify(lock, spec) == []
    # a store file: one byte of run.json, the trades file, a store that is gone
    f = copy / KEY / "run.json"
    f.write_text(f.read_text().replace('"stage": "bp_build"', '"stage": "bp_built"', 1))
    bad = FRZ.verify(lock, spec)
    assert len(bad) == 1 and "runs_changed/bpl_lok-NQ-tf15 changed since the freeze (run)" in bad[0]
    now = FRZ.store_hash(copy, KEY)                                               # ... and a lock taken over the changed file would be another lock
    assert now["run"] != lock["stores"][KEY]["run"] and now["cells"] == lock["stores"][KEY]["cells"]
    assert FRZ.digest({**lock, "stores": {**lock["stores"], KEY: now}}) != lock["hash"]
    with open(copy / WORSE / "cells.npz", "ab") as fh:
        fh.write(b"\0")
    assert [("(cells)" in x or "(run)" in x) for x in FRZ.verify(lock, spec)] == [True, True]
    shutil.rmtree(copy / "c1-NQ-tf15")
    assert len(FRZ.verify(lock, spec)) == 3 and "c1-NQ-tf15 cannot be read" in FRZ.verify(lock, spec)[2]
    # the code: a file of the engine or of the family that is not what it was
    good, keep = r["lock"], RUN.code
    try:
        RUN.code = lambda family=None: {**keep(family), "families/port1.py": "f" * 16}
        bad = FRZ.verify(good, spec)
        assert len(bad) == 1 and bad[0].startswith("families/port1.py changed since the freeze")
    finally:
        RUN.code = keep
    # the card on file; the lock itself
    assert FRZ.verify(good, {**spec, "run": {**spec["run"], "limits": {"max_tr": 1}}}) == ["the card and settings on file (spec.json) are not the frozen ones"]
    hand = {**good, "default": good["variants"][0] if good["variants"][0] != good["default"] else good["variants"][1]}
    assert "lock.json was changed after it was written" in FRZ.verify(hand, spec)[0] and FRZ.verify(good, spec) == []


# ================================================================ (e) the test range of a market

def _archive(base: Path, root: str, days: dict, tapes=None) -> None:
    """A fake archive: {date: [(contract, ticks, complete), ...]} as manifests, and (NQ) the tape files of `tapes`."""
    for d, files in days.items():
        for contract, ticks, complete in files:
            f = base / "ticks" / root / d[:4] / f"{d}_{contract}.json"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"root": root, "contract": contract, "session_date": d, "ticks": ticks, "complete": complete}))
    for d in tapes or []:
        f = base / "tape" / root / d[:4] / d[5:7] / f"{d}.parquet"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("")


@contextlib.contextmanager
def _disk(base: Path):
    keep = (S.ARCHIVE, S.TAPE_DIR, S.HB_TAPE, S.OWN_TAPE)
    S.ARCHIVE, S.TAPE_DIR, S.HB_TAPE, S.OWN_TAPE = base / "ticks", base / "tape", base / "hb", base / "own"
    try:
        yield
    finally:
        S.ARCHIVE, S.TAPE_DIR, S.HB_TAPE, S.OWN_TAPE = keep


def test_the_test_range_ends_with_the_last_complete_session_on_disk():
    base = F.tmp() / "archive"
    one = lambda ok=True: [("Z6", 5000, ok)]  # noqa: E731
    days = {"2025-06-30": one(), "2025-07-01": one(), "2025-07-02": [("U5", 90000, True), ("Z5", 400, False)],      # the FRONT contract counts (the most ticks)
            "2025-07-05": one(), "2025-12-31": one(), "2026-01-02": one(), "2026-01-05": one(), "2026-01-06": one(False), "2026-01-07": one()}
    _archive(base, "GC", days)
    (base / "own" / "GC").mkdir(parents=True)
    (base / "own" / "GC" / "2025-07-01.tape").write_text("")
    with _disk(base), F.no_engine():
        r = RUN.test_range("GC")
        # 2025-06-30 is a build day, 2025-07-05 a Saturday; 2026-01-06 is not complete, so the run of complete sessions ends the day before it
        assert (r["start"], r["end"], r["sessions"], r["stops"], r["no_tape"]) == ("2025-07-01", "2026-01-05", 5, "2026-01-06", 4)
        assert r["parts"] == [{"name": "Jul-Dec 2025", "start": "2025-07-01", "end": "2025-12-31", "sessions": 3},
                              {"name": "Jan-Sep 2026", "start": "2026-01-01", "end": "2026-01-05", "sessions": 2}]
        _archive(base, "ES", {**days, "2026-01-06": one()})                       # nothing incomplete: to the last session on disk
        assert (RUN.test_range("ES")["end"], RUN.test_range("ES")["stops"], RUN.test_range("ES")["sessions"]) == ("2026-01-07", None, 7)
        # NQ is replayed from its ofb_tick tapes: a session without one ends the run, whatever its manifest says
        _archive(base, "NQ", {**days, "2026-01-06": one()}, tapes=["2025-07-01", "2025-07-02", "2025-12-31", "2026-01-02"])
        assert (RUN.test_range("NQ")["end"], RUN.test_range("NQ")["stops"], RUN.test_range("NQ")["no_tape"]) == ("2026-01-02", "2026-01-05", 0)
        # refused: no complete session; a second part without one (line 4.1 reads both)
        _archive(base, "YM", {"2025-07-01": one(False), "2025-07-02": one()})
        F.refused(lambda: RUN.test_range("YM"), "no complete session")
        F.refused(lambda: RUN.test_range("RTY"), "no complete session")
        _archive(base, "CL", {"2025-07-01": one(), "2025-12-31": one(), "2026-01-02": one(False)})
        assert "Jan-Sep 2026" in F.refused(lambda: RUN.test_range("CL"), "line 4.1")
    real = RUN.test_range("NQ")                                                   # this machine: file names and manifests, nothing else
    assert real["start"] == "2025-07-01" and real["end"] >= "2026-09-22" and [p["name"] for p in real["parts"]] == ["Jul-Dec 2025", "Jan-Sep 2026"]
    assert sum(p["sessions"] for p in real["parts"]) == real["sessions"] and all(p["sessions"] > 100 for p in real["parts"])


# ================================================================ (f) the command line

def test_the_command_line_runs_the_pass_as_a_job_and_shows_a_frozen_idea_again():
    if S.compute_window_end() is not None:
        import pytest
        pytest.skip("no heavy run starts 09:18-09:36 ET on weekdays")
    name = "bpl_job"                                                             # its own stores: its worse-fills table is not on disk yet
    root = F.fresh(name, "cmd")
    last = [f"--root={root}", "--json"]
    with F.tiny():
        rc, js = F.run_cli(["lock", name, "--wait=0", *last])                    # the pass is a job: `running` at once ...
        d = json.loads(js)
        assert rc == 0 and list(d)[:len(F.CONTRACT)] == list(F.CONTRACT) and (d["command"], d["name"], d["phase"], d["lines"]) == ("lock", name, 3, [])
        assert d["job"]["state"] in ("queued", "running") and not (root / name / "lock.json").exists()
        jid = d["job"]["id"]
        assert JOBS.command(jid, root) == "lock" and F.read(root / "_jobs" / jid / "job.json")["args"]["heavy"] is True
        rc, js = F.run_cli(["lock", name, *last])                                # ... and `lock` again picks ITS wait back up (no second job)
        d = json.loads(js)
        if d["job"] is None:                                                    # (the job had ended between the two calls: its own answer, by its id)
            rc, js = F.run_cli(["job", jid, "--wait=60", *last])
            d = json.loads(js)
        assert rc == 0 and d["job"] == {"id": jid, "state": "done", "progress": d["job"]["progress"]} and len(list((root / "_jobs").iterdir())) == 1, d
        lock = F.read(root / name / "lock.json")
        assert (d["hash"], d["default"], d["already"], d["status"], d["phase"]) == (lock["hash"], lock["default"], False, "lead", 3)
        assert [x["line"] for x in d["lines"]] == [f"3.{i}" for i in range(1, 9)] and d["range"]["start"] == "2025-07-01" and (F.OUT / f"{name}-NQ-tf15-nyam-worse" / "run.json").exists()
        rc, js = F.run_cli(["job", jid, "--wait=0", *last])                      # the job by its id: the freeze's own answer
        assert rc == 0 and json.loads(js)["hash"] == lock["hash"]
        with F.no_engine():                                                      # a frozen idea: shown again at once, as the connector asks for it and for a person
            rc, js = F.run_cli(["lock", name, *last])
            again = json.loads(js)
            assert rc == 0 and (again["already"], again["hash"], again["saved"], again["job"]) == (True, lock["hash"], [], None)
            rc, txt = F.run_cli(["lock", name, f"--root={root}"])
            lines = txt.rstrip("\n").split("\n")
            assert rc == 0 and lines[0].startswith(f"FROZEN already: {name} · lock {lock['hash']}") and lines[1].startswith("3.1 PASS ") and lines[-1].startswith("NEXT: ")
            # refusals: exit 2, the one object, nothing run
            for argv, word in ((["lock", "bpl_nobody"], "no card"), (["lock"], "name"), (["lock", "Bad Name"], "name"), (["lock", name, "--days=2025-07-01"], "unrecognized")):
                rc, js = F.run_cli([*argv, *last])
                e = json.loads(js)
                assert rc == 2 and list(e) == list(F.CONTRACT) and e["ok"] is False and word in e["error"] and (e["command"], e["phase"]) == ("lock", 3), (argv, e)
    RESULTS["test_the_command_line_runs_the_pass_as_a_job_and_shows_a_frozen_idea_again"] = (1, 1, "freeze through the front door, its pass as a job")


# ================================================================ nothing of the test days, nothing outside the temp folder

def test_the_lock_keeps_the_builds_average_trade_and_the_lines_of_the_default():
    root = F.fresh(NAME, "boxkeep")
    with F.tiny(build_avg_trade=None):
        r = FRZ.lock(NAME, root)
    lock = r["lock"]
    sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
    u, st = T.bp_unit(sp, "NQ", "15", "nyam"), J.store({"dir": F.OUT, "key": KEY})
    nets = [np.asarray(J.cellx(st, c, "nyam", u)["net"], float) for c in lock["variants"]]
    assert lock["build"]["avg_trade"] == sum(float(x.sum()) for x in nets) / sum(len(x) for x in nets) == T.avg_trade(st, u, lock["variants"])
    data = T.box(st, u, lock["default"], F.DAYS)
    assert len(data["day"]) == len(F.DAYS) and float(data["day"].sum()) == float(data["trades"].sum()) and int(data["n"].sum()) == len(data["trades"])
    # each day's worst open loss: the library's own reading of the default variant's trades (MAE + the round-turn commission), a day without a trade = 0
    c, cal = J.cellx(st, lock["default"], "nyam", u), T.build_days(u, F.DAYS)
    assert len(data["open"]) == len(F.DAYS) and (data["open"] >= 0).all() and not data["open"][data["n"] == 0].any()
    assert round(float(data["open"].max()), 2) == LB.metrics(c, cal)["worst_open_loss"] > 0
    # SHOWN, never a pass line: the default variant's prop odds on the build days for the account of line 3.6, kept with the lock
    prop = PO.look(c, cal)
    assert lock["prop"] == json.loads(json.dumps(prop)) and prop["account"] == {"id": R.rule("3.6")["also"]["rule_file"], "name": "LucidPro 50K · $1,200 daily limit"}
    assert prop["text"].startswith("PROP ODDS ON THE BUILD DAYS (shown, never a pass line): LucidPro 50K") and "TEST days" in prop["text"] and prop["text"] in r["text"]
    assert prop["rule"] == PO.RULE and prop["days"] == len(F.DAYS) and all(0.0 <= prop[p]["p"] <= 1.0 and prop[p]["size"] in R.template("sizes")["steps"] for p in ("eval", "payout"))
    assert not any(x["line"].startswith("5.") for x in r["lines"]), "the shown odds are no line of the lock"
    mine = [f(data) for f in L.BOX]
    assert [(x["line"], x["passed"], x["text"]) for x in lock["box"]] == [(x["line"], x["passed"], x["text"]) for x in mine]
    assert [x["line"] for x in r["lines"]] == [f"3.{i}" for i in range(1, 9)] and [x["text"] for x in r["lines"]][2:] == [x["text"] for x in mine]


def test_no_test_day_was_opened_and_nothing_was_written_outside_the_temp_folder():
    assert CALLS, "the module ran no engine call at all"
    for c in CALLS:                                                              # every engine call of this module: the build switch, build days, no other switch
        assert c["period"] == "bp_build" and c["args"] == () and not any(c[k] for k in ("allow_holdout", "allow_exam", "allow_check")), c
        assert c["days"] and max(c["days"]) <= "2025-06-30", c
    F.clean()


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
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
        finally:
            teardown_function()
    sys.exit(rc)
