"""LOCK of phase 5, before the eval is bought (blueprint/propodds.py; `bp.py sim <name> --account=ID --attempts=N
--fee-budget=USD`) -- toolkit plan, step 9.

(a) THE WALKS ARE THE APP'S. With zero open loss the eval walk and the funded walk give, PATH FOR PATH on the same drawn
    days (same seed), what homebase/backtest/propsim's run_eval and run_funded give -- for every rule file's mechanics
    (trailing floor and lock, consistency, minimum days, the soft daily loss limit).
(b) THE OPEN-LOSS RULE, on hand-made days with known answers: a day whose worst point -- its start minus its worst open loss
    -- is at or under the floor in force busts the account whatever it closes at; a cent above it does not.
(c) THE "LIVE IS WORSE" ROW is propsim.degrade's with the numbers of line 5.2 (win rate -5 points, winners -15 %), and a
    day turned into a loss takes the open loss of the losing day it was drawn from.
(d) SIZE AND DAYS: a size in micros is the library's micro cost model; the day pool is the app's weekday grid; the soft
    daily loss limit is the app's (a day that hits it closes at the limit, and its open loss is the limit).
(e) THE ODDS on hand-made trade lists with known answers, size by size; the best size of a phase and the rule "between
    two sizes whose confidence intervals overlap, take the smaller".
(f) THE COMMAND: refused unless the out-of-sample test is on file and passed, without the owner's attempts and fee budget,
    for an account the app has no rule file for; lines 5.1-5.4; the result saved through the app's idea store; the command
    line as the connector writes it -- and the app's own blueprint_sim against this toolkit.
EVERYTHING IS HAND-MADE (tests/blueprint_synth.py): no tape is read, no engine run is made, nothing leaves the temp folder.

  pytest tests/test_blueprint_propodds.py -q          python tests/test_blueprint_propodds.py     the same, one line per test
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import rules as R  # noqa: E402

import blueprint_synth as SY  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402

PS = PO.app()
E = PS.engine
IS = A.ideastore()
PRO, PRO_FREE, FLEX = "lucid-pro-50k@2026-09-27b", "lucid-pro-50k-no-dll@2026-09-27b", "lucid-flex-50k@2026-09-27"
ACCOUNTS = (FLEX, PRO, PRO_FREE, "apex-eod-50k@2026-09-27b", "apex-legacy-300k@2026-09-28", "topstep-50k@2026-09-27b")
CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")      # plan section 8
NAMES = {0: "timeout", PO.PASS: "pass", PO.BUST: "bust"}
HOME = Path.home() / ".homebase"
APP_PYTHON = S.REPO / ".venv" / "bin" / "python"
_T = {"keep": tempfile.TemporaryDirectory(prefix="bp_sim_")}
TMP = Path(_T["keep"].name).resolve()
ROOT, DRAFTS, STORES = TMP / "ideas", TMP / "drafts", TMP / "stores"
ENV = {"HOMEBASE_IDEAS_ROOT": str(TMP / "ideas_env"), "HOMEBASE_DRAFTS_DIR": str(DRAFTS)}        # never the real ~/.homebase
_KEPT: dict = {}
RESULTS: dict = {}


def _listing(p: Path):
    return sorted(x.name for x in p.iterdir()) if p.exists() else None


BEFORE = {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies")}


def setup_function(_=None):
    _KEPT.update({k: os.environ.get(k) for k in ENV})
    os.environ.update(ENV)


def teardown_function(_=None):
    for k, v in _KEPT.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def refused(fn, *words) -> str:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert all(w in str(e) for w in words), str(e)
        return str(e)
    raise AssertionError(f"not refused ({words})")


def read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def by(r: dict) -> dict:
    return {x["line"]: x for x in r["lines"]}


def cells(rows: list) -> dict:
    """Hand-made trades as the packed arrays of a store's cell."""
    return LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])))


def one(days: list, r: dict, funded: bool = False) -> dict:
    """ONE hand-made path, [(the day's P&L, its worst open loss)], walked."""
    pnl, opn = (np.array([[d[k] for d in days]], np.float64) for k in (0, 1))
    return PO.funded_walk(pnl, opn, r) if funded else PO.eval_walk(pnl, pnl != 0, opn, r)


def pool(seed: int, n: int = 120, scale: float = 600.0) -> tuple:
    rnd = random.Random(seed)
    pnl = np.array([0.0 if rnd.random() < 0.25 else round(rnd.gauss(60.0, scale), 2) for _ in range(n)])
    return pnl, pnl != 0.0


# ================================================================ (a) the walks are the app's

def test_with_zero_open_loss_the_walks_are_the_apps_path_for_path():
    seen = set()
    for rid in ACCOUNTS:
        r = PS.load_rules(rid)
        for seed, scale in ((1, 300.0), (2, 900.0), (3, 2600.0), (4, 9000.0)):
            pnl, traded = pool(seed, scale=scale)
            for H in (10, 20, 70):
                idx = PO.draws(len(pnl), 300, H, PS.SEED)
                P, T = pnl[idx], traded[idx]
                e, f = PO.eval_walk(P, T, np.zeros_like(P), r), PO.funded_walk(P, np.zeros_like(P), r)
                for k in range(len(idx)):
                    path = list(zip(P[k].tolist(), T[k].tolist()))
                    a, b = E.run_eval(path, r), E.run_funded(path, r)
                    assert (NAMES[int(e["outcome"][k])], int(e["day"][k]), int(e["trade_days"][k])) == (a["outcome"], a["day"], a["trade_days"]), (rid, seed, H, k)
                    mine = {"payout_at": int(f["payout_at"][k]) or None, "max_payout_at": int(f["max_payout_at"][k]) or None, "bust_at": int(f["bust_at"][k]) or None,
                            "cheque": None if math.isnan(f["cheque"][k]) else float(f["cheque"][k])}
                    assert mine == b, (rid, seed, H, k, mine, b)
                    seen |= {a["outcome"]} | {key for key, v in b.items() if v is not None}
    assert seen == {"pass", "bust", "timeout", "payout_at", "cheque", "max_payout_at", "bust_at"}, f"the comparison did not see every outcome: {seen}"


def test_the_paths_are_drawn_once_per_pool_from_the_apps_seed():
    a = PO.draws(120, 500, 20, PS.SEED)
    assert a.shape == (500, 20) and a.min() >= 0 and a.max() < 120 and a is PO.draws(120, 500, 20, PS.SEED)      # one fixed matrix: every size and row on the same paths
    assert np.array_equal(a, np.random.default_rng(PS.SEED).integers(0, 120, size=(500, 20))) and not np.array_equal(a, PO.draws(120, 500, 20, PS.SEED + 1))
    assert (PS.N_PATHS, PS.SEED) == (20_000, 20260801), "the app's own settings: the toolkit types none"
    need = R.need("5.3")
    assert (need["eval"]["days"], need["payout"]["days"]) == (10, 20)                    # the days the walks are given


# ================================================================ (b) the open-loss rule, by hand

def test_an_open_loss_at_the_floor_busts_the_account_whatever_the_day_closes_at():
    flex, pro = PS.load_rules(FLEX), PS.load_rules(PRO_FREE)
    assert (flex["trailing_mll"], flex["lock_at"], flex["lock_floor"], flex["eval_target"]) == (2000, 2100, 100, 3000)
    out = lambda days, r=flex: (NAMES[int(one(days, r)["outcome"][0])], int(one(days, r)["day"][0]))  # noqa: E731
    # from a flat start the floor is -$2,000: an open loss of $2,000 is the bust, $1,999.99 is not -- though the day closed UP
    assert out([(500.0, 2100.0)]) == ("bust", 1) and out([(500.0, 2000.0)]) == ("bust", 1) and out([(500.0, 1999.99)]) == ("timeout", 1)
    assert out([(500.0, 0.0)]) == ("timeout", 1) == (E.run_eval([500.0], flex)["outcome"], 1)             # the end-of-day rule sees nothing
    # the floor trails the end-of-day peak: +$1,000 puts it at -$1,000, and the next day's worst point is held against THAT
    assert out([(1000.0, 0.0), (200.0, 2000.0)]) == ("bust", 2) and out([(1000.0, 0.0), (200.0, 1999.0)]) == ("timeout", 2)
    # locked at +$100 once the peak reaches +$2,100
    assert out([(2500.0, 0.0), (0.0, 2400.0)]) == ("bust", 2) and out([(2500.0, 0.0), (0.0, 2399.0)]) == ("timeout", 2)
    # the breach comes before the close: a day that would have passed the eval is a bust when its open loss reached the floor
    assert out([(3000.0, 1500.0)], pro) == ("pass", 1) and out([(3000.0, 2000.0)], pro) == ("bust", 1)
    # a losing day is caught at its close as before (an open loss smaller than the closing loss adds nothing)
    assert out([(-2000.0, 100.0)]) == ("bust", 1) == out([(-2000.0, 0.0)])


def test_the_funded_walk_has_the_same_rule():
    r = PS.load_rules(FLEX)
    assert (r["win_day"], r["payout_win_days"], r["max_payout_profit"], r["payout_share"], r["payout_cap"]) == (150, 5, 4000, 0.5, 2000)
    f = one([(900.0, 0.0)] * 5, r, funded=True)
    assert (int(f["payout_at"][0]), float(f["cheque"][0]), int(f["max_payout_at"][0]), int(f["bust_at"][0])) == (5, 2000.0, 5, 0)
    f = one([(900.0, 2000.0)] + [(900.0, 0.0)] * 4, r, funded=True)
    assert (int(f["payout_at"][0]), int(f["max_payout_at"][0]), int(f["bust_at"][0])) == (0, 0, 1) and math.isnan(f["cheque"][0])
    f = one([(900.0, 0.0)] * 3 + [(900.0, 2600.0)], r, funded=True)            # peak +$2,700: the floor is locked at +$100
    assert int(f["bust_at"][0]) == 4 and int(f["payout_at"][0]) == 0
    assert int(one([(900.0, 0.0)] * 3 + [(900.0, 2599.0), (900.0, 0.0)], r, funded=True)["max_payout_at"][0]) == 5


# ================================================================ (c) the "live is worse" row

def test_the_live_is_worse_row_is_the_apps_degrade():
    need = R.need("5.2")
    assert (need["win_rate"], -need["winners"]) == (-0.05, 0.15) == E.DEGRADATION[2][1:], "line 5.2 is the app's middle row"
    rnd = random.Random(11)
    for seed in (5, 6):
        pnl, traded = pool(seed, n=200)
        opn = np.array([0.0 if p == 0 else abs(p) * rnd.uniform(1.0, 2.0) + (p > 0) * 50.0 for p in pnl])
        got, opn_w = PO.worse(pnl, traded, opn)
        want = E.degrade(pnl.tolist(), traded.tolist(), -0.05, 0.15)
        assert got.tolist() == want and len(opn_w) == len(opn)
        flipped = [i for i in range(len(pnl)) if pnl[i] > 0 and want[i] < 0]
        assert len(flipped) == round(0.05 * int(traded.sum())) > 0
        for i in flipped:                           # a day turned into a loss carries the open loss of a losing day with that P&L
            assert opn_w[i] in opn[pnl == want[i]] and opn_w[i] >= -want[i]
        keep = [i for i in range(len(pnl)) if i not in flipped]
        assert np.array_equal(opn_w[keep], opn[keep])                              # winners are smaller; their worst point is not
        assert all(want[i] == pnl[i] * 0.85 for i in keep if pnl[i] > 0) and all(want[i] == pnl[i] for i in keep if pnl[i] <= 0)
    # no losing day to draw from: the app turns the day into minus the mean day, and its open loss is at least that loss
    got, opn_w = PO.worse(np.full(40, 100.0), np.ones(40, bool), np.full(40, 7.0))
    assert sorted(set(got.tolist())) == [-85.0, 85.0] and (got < 0).sum() == 2 and set(opn_w[got < 0]) == {85.0} and set(opn_w[got > 0]) == {7.0}


# ================================================================ (d) size and days

def test_a_size_in_micros_is_the_librarys_micro_cost_model():
    days = SY.weekdays()[:3]
    x = cells([SY.trade(days[0], 50.0, 10.0), SY.trade(days[1], -30.0, 30.0), SY.trade(days[2], 0.5, 0.0)])
    assert np.allclose(x["net"], [506.0, -294.0, 11.0]) and np.allclose(x["mae"], [100.0, 300.0, 0.0])        # 1 contract, as the stores keep it
    z = PO.sized(x, 1)
    assert np.allclose(z["net"], [50.0, -30.0, 0.5]) and np.allclose(z["mae"], [10.0, 30.0, 0.0]) and z["cost"] == 1.0
    z = PO.sized(x, 7)
    assert np.allclose(z["net"], [350.0, -210.0, 3.5]) and np.allclose(z["mae"], [70.0, 210.0, 0.0]) and z["cost"] == 7.0
    assert np.array_equal(z["exit_ms"] - z["entry_ms"], [600_000] * 3)
    x["risk"][:] = 100.0                            # the library sizes a 100-point stop on NQ to 5 micros of about $1,000 risk
    lib = LB.sized(x, "NQ")
    assert lib["micros"].tolist() == [5, 5, 5] and np.allclose(lib["net"], PO.sized(x, 5)["net"]) and np.allclose(lib["mae"], PO.sized(x, 5)["mae"])
    assert np.allclose(lib["cost"], PO.sized(x, 5)["cost"]) and R.template("sizes")["micros_per_contract"] == LB.MICRO_DIV


def test_the_day_pool_is_the_session_days_of_the_read_with_each_days_worst_open_loss():
    r = PS.load_rules(FLEX)
    d = SY.weekdays("2025-07-07", "2025-07-18")                                   # two weeks, Monday to Friday
    rows = PO.ledger(cells([SY.trade(d[1], 50.0, 10.0), SY.trade(d[1], -30.0, 30.0, at="10:15"), SY.trade(d[3], 20.0, 80.0), SY.trade(d[8], -5.0, 5.0)]), 10, r)
    net, traded, opn, dates = PO.days(rows, r, d[1:9])
    assert (net.tolist(), traded.tolist(), dates) == PS.weekday_grid(rows), "on a calendar of every weekday the pool IS the app's weekday grid"
    assert dates == d[1:9] and net.tolist() == [200.0, 0.0, 200.0, 0.0, 0.0, 0.0, 0.0, -50.0]
    # the worst open point of a day = library._worst_open: at each entry, what is realised minus the open trade's MAE and commission
    assert opn.tolist() == [110.0, 0.0, 810.0, 0.0, 0.0, 0.0, 0.0, 60.0]           # day 1: -(100 + 10) at the first entry; +500 - (300 + 10) at the second
    cal = [x for x in SY.weekdays("2025-07-01", "2025-07-31") if x != "2025-07-04"]          # the session days a read lists: no 4th of July
    net, traded, opn, dates = PO.days(rows, r, cal)                               # the whole range: its other sessions are days without a trade
    assert dates == cal and len(dates) == 22 and int(traded.sum()) == 3 and float(net.sum()) == 350.0 and float(opn.sum()) == 980.0
    assert opn[dates.index(d[3])] == 810.0
    assert PO.days(rows, r, cal[:3])[3] == sorted(set(cal[:3]) | {d[1], d[3], d[8]}) and PO.days(rows, r)[3] == [d[1], d[3], d[8]], "a day that traded is never dropped"


def test_the_soft_daily_loss_limit_closes_the_day_at_the_limit_and_its_open_loss_is_the_limit():
    pro, free = PS.load_rules(PRO), PS.load_rules(PRO_FREE)
    assert (E._dll(pro), E._dll(free)) == (1200.0, None)
    d = SY.weekdays()[0]
    x = cells([SY.trade(d, -50.0, 60.0), SY.trade(d, 30.0, 90.0, at="10:15"), SY.trade(d, 40.0, 1.0, at="10:45")])
    rows = PO.ledger(x, 10, pro)                    # -$500, then a trade that dips $910 under it: the day is closed at -$1,200
    assert [(t["net"], bool(t.get("dll_stop"))) for t in rows] == [(-500.0, False), (-700.0, True)] and rows == PS.limit_trades(PO.ledger(x, 10, free), pro)
    net, _, opn, _ = PO.days(rows, pro)
    assert (net.tolist(), opn.tolist()) == ([-1200.0], [1200.0])
    net, _, opn, _ = PO.days(PO.ledger(x, 10, free), free)                        # without the limit: all three trades, the dip in full
    assert (net.tolist(), opn.tolist()) == ([200.0], [1410.0])
    net, _, opn, _ = PO.days(PO.ledger(x, 5, pro), pro)                           # at half the size the dip stays inside the limit
    assert (net.tolist(), opn.tolist()) == ([100.0], [705.0])


# ================================================================ (e) the odds, on hand-made lists

def steady(micro_net: float, micro_mae: float = 0.0) -> dict:
    """One trade every weekday of the hand-made range, always the same."""
    return cells([SY.trade(d, micro_net, micro_mae) for d in SY.weekdays()])


def test_the_size_steps_an_account_may_trade():
    all_ = R.template("sizes")["steps"]
    assert all_ == [1, 2, 3, 5, 7, 10, 15, 20, 30, 40]
    assert PO.steps(PS.load_rules(PRO)) == (all_, [1, 2, 3, 5, 7, 10, 15, 20])      # funded: the scaling plan starts at 20 micros
    assert PO.steps(PS.load_rules("topstep-50k@2026-09-27b")) == (all_, all_)       # 50 micros, no scaling plan
    assert PO.steps({**PS.load_rules(PRO), "cap_micros": 12, "scaling_micros": None}) == ([1, 2, 3, 5, 7, 10], [1, 2, 3, 5, 7, 10])


def test_the_odds_of_a_steady_winner_are_known_size_by_size():
    r = PS.load_rules(PRO_FREE)                     # target $3,000, one day may pass, no consistency rule, no daily limit
    t = PO.table(steady(40.0), r, SY.weekdays(), paths=400)
    assert [x["size"] for x in t] == [1, 2, 3, 5, 7, 10, 15, 20, 30, 40]
    # the plain row: $40 a micro a day, every day. The eval needs $3,000 inside 10 days: 10 micros ($400 a day) and up
    assert [x["eval"]["plain"]["p"] for x in t] == [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
    assert all(x["eval"]["plain"]["bust"] == 0 for x in t)
    # the maximum payout needs 5 days of $150 and $4,000 inside 20 days: 5 micros ($200 a day) and up; no step above 20 micros
    assert [x["payout"] and x["payout"]["plain"]["p"] for x in t] == [0, 0, 0, 1, 1, 1, 1, 1, None, None]
    for x in t:                                     # "live is worse" is never better, and it is the walk on the app's degraded days
        assert x["eval"]["worse"]["p"] <= x["eval"]["plain"]["p"] and (x["payout"] is None or x["payout"]["worse"]["p"] <= x["payout"]["plain"]["p"])
        assert (x["days"], x["traded"], x["flipped"]) == (44, 44, 2) and 2 == round(0.05 * 44)
    net, traded, opn, _ = PO.days(PO.ledger(steady(40.0), 10, r), r, SY.weekdays())
    assert net.tolist() == [400.0] * 44
    wnet, wopn = PO.worse(net, traded, opn)
    w, ten = PO.odds(wnet, traded, wopn, r, 400), next(x for x in t if x["size"] == 10)
    assert w["eval"] == ten["eval"]["worse"] and w["payout"] == ten["payout"]["worse"]
    assert 0.5 < w["eval"]["p"] < 0.8, "9 winning days of $340 in a row, a losing day 1 in 22: 0.955 ** 9 = 0.66"
    assert w["eval"]["ci"] == list(E.wilson_ci(round(w["eval"]["p"] * 400), 400))


def test_open_losses_change_the_answer_and_the_end_of_day_rule_would_not_see_it():
    r = PS.load_rules(PRO_FREE)
    x = steady(40.0, 250.0)                          # the same winner, but every trade is $250 a micro under water first
    t = {row["size"]: row for row in PO.table(x, r, SY.weekdays(), paths=400)}
    assert {k: t[10]["eval"]["plain"][k] for k in ("p", "ci", "bust")} == {"p": 0.0, "ci": list(E.wilson_ci(0, 400)), "bust": 1.0}          # $2,510 open on day 1: bust
    assert t[10]["eval"]["plain"]["free"] == {"p": 0.0, "ci": list(E.wilson_ci(0, 400)), "bust": 1.0}                               # ... and no day limit helps a bust on day 1
    assert t[7]["eval"]["plain"]["bust"] == 0.0 and t[7]["eval"]["plain"]["p"] == 0.0                   # $1,757 open: alive, but 10 x $280 is not $3,000
    assert all(t[s]["eval"]["plain"]["p"] == 0.0 for s in t), "no size passes once open losses count"
    net, traded, opn, _ = PO.days(PO.ledger(x, 10, r), r, SY.weekdays())
    assert opn.tolist() == [2510.0] * 44
    assert PO.odds(net, traded, np.zeros_like(opn), r, 400)["eval"]["p"] == 1.0, "the end-of-day rule (the tester page's) passes it every time"
    assert "COUNTS OPEN LOSSES" in PO.LABEL and "END-OF-DAY" in PO.LABEL and "tester page" in PO.LABEL


def test_the_prop_odds_shown_at_the_lock_are_line_5_5s_reading_and_refuse_nothing():
    """propodds.look (BLUEPRINT.md phase 3, owner 2026-10-07): one variant's trades for the account of line 3.6, read as line
    5.5 reads a strategy. A number that is only shown: an account the app does not have, or no trade, is said and nothing is raised."""
    rid = R.rule("3.6")["also"]["rule_file"]
    assert rid == PRO and PS.load_rules(rid)["name"].startswith(R.need("3.6")["account"]) and PS.load_rules(rid)["trailing_mll"] == R.need("3.6")["limit"]
    x, cal = steady(40.0), SY.weekdays()
    got, want = PO.look(x, cal, paths=400), PO.read("", PO.table(x, PS.load_rules(rid), cal, paths=400), "5.5")
    assert got["account"] == {"id": rid, "name": PS.load_rules(rid)["name"]} and (got["rule"], got["days"]) == (PO.RULE, 44)
    assert got["eval"] == want["eval"] and got["payout"] == want["payout"] and set(got) == {"account", "rule", "days", "eval", "payout", "text"}
    e, p = got["eval"], got["payout"]
    mic = lambda n: f"{n} micro{'s' * (n != 1)}"  # noqa: E731
    assert (e["size"], p["size"]) == (1, 5), "no day limit: $40 a day reaches $3,000 at 1 micro; the first payout needs 5 days of $150"
    assert got["text"] == (f"PROP ODDS ON THE BUILD DAYS (shown, never a pass line): {PS.load_rules(rid)['name']}, open losses count, the \"live is worse\" row -- eval, a pass "
                           f"before a bust {100 * e['p']:.1f} % at {mic(e['size'])} (plain {100 * e['plain']:.1f} %); funded, a first payout before a bust "
                           f"{100 * p['p']:.1f} % at {mic(p['size'])} (plain {100 * p['plain']:.1f} %). Line 5.5 asks 50 % and 50 % of them on the TEST days (phase 5).")
    assert e["plain"] == 1.0 and PO.look(steady(40.0, 2100.0), cal, paths=400)["eval"]["p"] == 0.0, "every trade $2,100 a micro under water first: no size survives"
    json.dumps(got)                                 # plain JSON: it is kept with the lock
    assert PO.look({"net": np.zeros(0)}, cal)["text"].endswith("not shown, the variant has no trade")
    also = R.rule("3.6")["also"]
    try:
        also["rule_file"] = "no-such-account@2026-01-01"
        gone = PO.look(x, cal, paths=400)
    finally:
        also["rule_file"] = rid
    assert set(gone) == {"account", "text"} and "not shown, the app's prop simulator has no rule file no-such-account@2026-01-01" in gone["text"]


def test_between_two_sizes_whose_intervals_overlap_the_smaller_is_taken():
    row = lambda size, p, lo, hi, pay=True: {"size": size, "eval": {"worse": {"p": p, "ci": [lo, hi]}},  # noqa: E731
                                             "payout": {"worse": {"p": p / 2, "ci": [lo / 2, hi / 2]}} if pay else None}
    rows = [row(5, 0.50, 0.49, 0.51), row(10, 0.61, 0.60, 0.62), row(15, 0.615, 0.605, 0.625), row(20, 0.40, 0.39, 0.41, pay=False)]
    assert PO.best(rows, "eval")["size"] == 10      # 15 has the highest odds; 10's interval reaches into it, 5's does not
    assert PO.best(rows, "payout")["size"] == 10 and PO.best(rows[:1] + rows[3:], "payout")["size"] == 5       # a step the funded account may not trade is not read
    assert PO.best([row(5, 0.2, 0.19, 0.21), row(10, 0.2, 0.19, 0.21)], "eval")["size"] == 5                  # equal odds: the smaller
    assert PO.best([row(5, 0.0, 0.0, 0.001), row(10, 0.0, 0.0, 0.001)], "eval")["size"] == 5                  # nothing passes: the smallest step
    assert PO.best([row(5, 0.1, 0.09, 0.11), row(10, 0.9, 0.89, 0.91)], "eval")["size"] == 10


# ================================================================ (f) the command

GOOD = [SY.trade(d, 40.0, 5.0) for d in SY.weekdays()]                            # $40 a micro every day
THIN = [SY.trade(d, 30.0 if i % 2 else -28.0, 30.0) for i, d in enumerate(SY.weekdays())]      # $1 a micro a day on average
LOSS = [SY.trade(d, -10.0, 10.0) for d in SY.weekdays()[:5]]
CELLS = {"v_good": GOOD, "v_thin": THIN, "v_worse": GOOD[:5], "v_build": GOOD[:5], "v_test": LOSS}     # the locked variants on the test days ...
WORSE = {**CELLS, "v_worse": LOSS}                                                # ... and with worse fills: v_worse loses there
FROZEN = ["v_good", "v_thin", "v_worse", "v_test"]                                # the lock's survivors: v_build made no money on build


def proven(name: str, **kw) -> Path:
    """An idea that is PROVEN ON HISTORY, with a read of five locked variants of which two survive."""
    return SY.proven(IS, ROOT, name, STORES, **{"cells": CELLS, "worse": WORSE, "survivors": FROZEN, **kw})


def test_refused_unless_the_test_is_on_file_and_passed():
    sim = lambda name, **kw: PO.sim(name, **{"account": PRO, "attempts": 3, "fee_budget": 345.0, "root": ROOT, "paths": 200, **kw})  # noqa: E731
    refused(lambda: sim("syn_nobody"), "no idea syn_nobody")
    refused(lambda: sim("Not A Name"), "name")
    SY.proven(IS, ROOT, "syn_lead")                                               # a lead: built, never tested
    assert IS.status("syn_lead", ROOT) == "lead"
    refused(lambda: sim("syn_lead"), "out-of-sample test is not on file", "bp.py test syn_lead")
    proven("syn_failed", test_fail=("4.5",))
    assert IS.status("syn_failed", ROOT) == "shelved"
    refused(lambda: sim("syn_failed"), "did not pass", "SHELVED")
    proven("syn_bare", stores=False)                                              # passed, but its result names no store of the read
    assert IS.status("syn_bare", ROOT) == "proven_on_history"
    refused(lambda: sim("syn_bare"), "lock.json", "test.json", "stores", "worse")
    proven("syn_gone", written=False)
    refused(lambda: sim("syn_gone"), "no store", "syn_gone-NQ-tf15-nyam-test")
    proven("syn_early", store_span=("2025-06-02", "2025-06-30"))                  # stores that are not of the frozen test range
    refused(lambda: sim("syn_early"), "2025-06-02", "not a store of the test days", SY.SPAN[0])
    proven("syn_other", store_lock="0000000000000000")                            # stores of another lock's read
    refused(lambda: sim("syn_other"), "another lock", "0000000000000000")
    proven("syn_relock", test_lock="1111111111111111")                            # a test result of another lock than the one on file
    refused(lambda: sim("syn_relock"), "1111111111111111", SY.LOCK)
    proven("syn_none", survivors=["v_worse", "v_test"])
    refused(lambda: sim("syn_none"), "no variant", "profitable on build, on the test and with worse fills")
    proven("syn_missing", locked=[*CELLS, "v_not_stored"])
    refused(lambda: sim("syn_missing"), "lacks the locked variant v_not_stored")
    proven("syn_ok")
    # line 5.4: the attempts and the fee budget are the owner's numbers -- never guessed, never left out
    for kw, word in (({"attempts": None}, "attempts"), ({"attempts": 0}, "attempts"), ({"attempts": 2.5}, "attempts"), ({"attempts": True}, "attempts"),
                     ({"fee_budget": None}, "fee budget"), ({"fee_budget": -1.0}, "fee budget"), ({"fee_budget": float("nan")}, "fee budget")):
        refused(lambda: sim("syn_ok", **kw), word, "5.4")
    refused(lambda: sim("syn_ok", account=None), "--account")
    refused(lambda: sim("syn_ok", account="lucid-pro-9000k@2030"), "lucid-pro-9000k@2030", PRO, FLEX)       # the app's rule files are named
    for name in ("syn_lead", "syn_failed", "syn_bare", "syn_gone", "syn_early", "syn_other", "syn_relock", "syn_none", "syn_missing", "syn_ok"):
        assert not (ROOT / name / "sim").exists(), f"{name}: a refusal wrote a result"


def test_what_the_freeze_and_the_read_hand_over():
    proven("syn_hand")
    h = PO.handed("syn_hand", ROOT)
    assert (h["market"], h["session"], h["bar"], h["lock"], h["span"]) == ("NQ", "nyam", "15", SY.LOCK, SY.SPAN) and h["calendar"] == SY.weekdays()
    assert h["where"] == "stores/syn_hand-NQ-tf15-nyam-test" and [v["id"] for v in h["variants"]] == list(CELLS)
    # each locked variant's net on the test days and with worse fills (1 contract, as the stores keep it), and whether the lock froze it as a survivor
    got = {v["id"]: (v["test"], v["worse"], v["frozen"]) for v in h["variants"]}
    assert got["v_good"] == (44 * 406.0, 44 * 406.0, True) and got["v_worse"] == (5 * 406.0, 5 * -94.0, True) and got["v_test"] == (5 * -94.0, 5 * -94.0, True)
    assert got["v_build"] == (5 * 406.0, 5 * 406.0, False) and got["v_thin"][0] == 22 * 306.0 + 22 * -274.0 > 0
    assert h["survivors"] == ["v_good", "v_thin"], "profitable on build and with worse fills there (the lock's survivors), on the test, and with worse fills there"
    x = PO.cell(h, "v_thin")
    assert len(x["net"]) == 44 and set(np.round(x["net"]).tolist()) == {306.0, -274.0}
    refused(lambda: PO.cell(h, "v_nobody"), "v_nobody")


def test_the_command_reads_one_strategy_on_lines_5_1_to_5_5_and_saves_them_in_the_app():
    proven("syn_ok")
    with SY.no_engine():                             # the trades are read where the read left them: nothing is run, no tape is opened
        r = RESULTS["sim"] = PO.sim("syn_ok", PRO, 3, 345.0, ROOT, paths=2000)
    assert tuple(r)[:len(CONTRACT)] == CONTRACT and (r["ok"], r["command"], r["name"], r["phase"], r["status"]) == (True, "sim", "syn_ok", 5, "proven_on_history")
    json.dumps(r)                                    # plain JSON as it is: the command line prints it
    assert [x["line"] for x in r["lines"]] == ["5.1", "5.2", "5.3", "5.4", "5.5"], [x["text"] for x in r["lines"]]
    assert [x["passed"] for x in r["lines"]] == [True, True, None, True, True]      # 5.3 is the PORTFOLIO's bar: said, not judged, for one strategy
    assert all(x["text"].startswith(f"{x['line']} PASS ") for x in r["lines"] if x["line"] != "5.3") and by(r)["5.3"]["text"].startswith("5.3 n/a  the PORTFOLIO's bar")
    assert r["account"]["id"] == PRO and r["account"]["name"] == "LucidPro 50K · $1,200 daily limit" and r["account"]["confirmed"] is True
    assert (r["attempts"], r["fee_budget"], r["rule"], r["paths"], r["seed"]) == (3, 345.0, "open losses count", 2000, PS.SEED)
    # the surviving variants: profitable on build, on the test and with worse fills -- 2 of the 5
    assert (r["survivors"], r["locked"], r["lock"]) == (2, 5, SY.LOCK) and [v["id"] for v in r["variants"]] == ["v_good", "v_thin"]
    assert r["range"] == {"start": SY.SPAN[0], "end": SY.SPAN[1]} and r["pool"] == {"days": 44, "traded": 44}
    ch = r["chosen"]
    assert ch["variant"] == "v_good" and ch["margin"] == max(v["margin"] for v in r["variants"]) >= 1.0
    sizes = [x["size"] for x in r["table"]]
    assert sizes == [1, 2, 3, 5, 7, 10, 15, 20, 30, 40] and [x["size"] for x in r["table"] if x["payout"]] == [1, 2, 3, 5, 7, 10, 15, 20]
    free = lambda x: x["eval"]["worse"]["free"]  # noqa: E731                     (one strategy is read on line 5.5's odds: no day limit)
    top = max(r["table"], key=lambda x: free(x)["p"])
    mine = next(x for x in r["table"] if x["size"] == ch["eval"]["size"])
    assert mine["size"] <= top["size"] and free(mine)["ci"][1] >= free(top)["ci"][0]                                   # the smaller of two that overlap
    assert not any(free(x)["ci"][1] >= free(top)["ci"][0] for x in r["table"] if x["size"] < mine["size"])
    assert (ch["eval"]["p"], ch["eval"]["ci"]) == (free(mine)["p"], free(mine)["ci"]) and ch["eval"]["plain"] == mine["eval"]["plain"]["free"]["p"] == 1.0
    assert ch["eval"]["fast"] == mine["eval"]["worse"]["p"] and ch["payout"]["size"] <= 20 and ch["payout"]["p"] >= 0.50 and ch["eval"]["p"] >= 0.50
    assert all(free(x)["p"] >= x["eval"]["worse"]["p"] - 0.05 for x in r["table"]), "without a day limit a pass is not rarer than inside 10 days (other paths: Monte Carlo noise aside)"
    assert r["horizon"] == PS.HORIZON == 250 and r["days"] == {"eval": 10, "payout": 20}
    L = by(r)
    assert L["5.3"]["need"] == {"eval": {"days": 10, "odds": 0.6}, "payout": {"days": 20, "odds": 0.75}} == R.need("5.3")
    assert L["5.3"]["number"] == {"eval": ch["eval"]["fast"], "payout": ch["payout"]["fast"]} and "a portfolio needs 60 %" in L["5.3"]["text"] and "a portfolio needs 75 %" in L["5.3"]["text"]
    assert L["5.5"]["need"] == {"eval": 0.5, "payout": 0.5} == R.need("5.5") and L["5.5"]["number"] == {"eval": ch["eval"]["p"], "payout": ch["payout"]["p"]}
    assert L["5.5"]["text"].count("need 50 % or more") == 2 and "no day limit" in L["5.5"]["text"] and "250 trading days" in L["5.5"]["text"]
    assert L["5.2"]["need"] == {"win_rate": -0.05, "winners": -0.15} and "win rate -5 points" in L["5.2"]["text"] and "winners -15 %" in L["5.2"]["text"]
    assert L["5.4"]["number"] == {"attempts": 3, "fee_budget": 345.0} and "3 attempts" in L["5.4"]["text"] and "$345" in L["5.4"]["text"]
    assert f"{ch['eval']['size']} micros" in L["5.1"]["text"] and f"{ch['payout']['size']} micros" in L["5.1"]["text"]
    text = r["text"].splitlines()
    assert PO.LABEL in r["text"] and PS.CAVEAT in r["text"] and any(ln.startswith("SIM of syn_ok") and "LucidPro 50K" in ln for ln in text)
    assert all(any(ln.split()[:1] == [str(s)] for ln in text) for s in sizes), "one row of the table a size step"
    assert all(x["text"] in text for x in r["lines"]) and "v_good" in r["text"] and "2 of the 5" in r["text"]
    # saved through the app's idea store: sim/<account>.json, idea.json at phase 5, the status as it was
    f = ROOT / "syn_ok" / "sim" / f"{PRO}.json"
    assert r["saved"] == [str(f)] and read(f)["chosen"] == ch and read(f)["lines"] == r["lines"]
    idea = IS.read_idea("syn_ok", ROOT)
    assert (idea["status"], idea["phase"]) == ("proven_on_history", 5) and [x["line"] for x in idea["lines"]] == ["5.1", "5.2", "5.3", "5.4", "5.5"] and idea["next"] == r["next"]
    assert "eval-card syn_ok" in r["next"]
    assert (DRAFTS / "syn_ok.py").read_text().splitlines()[1].startswith("# syn_ok · PROVEN ON HISTORY · phase 5")       # its record in the Lab follows
    assert PO.sim("syn_ok", PRO, 3, 345.0, ROOT, paths=2000)["table"] == r["table"], "the same seed, the same answer"


def test_odds_under_one_strategys_bar_fail_line_5_5():
    proven("syn_thin", survivors=["v_thin"])                                      # only the thin variant survives
    r = PO.sim("syn_thin", FLEX, 2, 280.0, ROOT, paths=2000)
    L = by(r)
    assert r["chosen"]["variant"] == "v_thin" and r["chosen"]["margin"] < 1.0 and r["survivors"] == 1
    assert (L["5.1"]["passed"], L["5.2"]["passed"], L["5.3"]["passed"], L["5.4"]["passed"], L["5.5"]["passed"]) == (True, True, None, True, False) and L["5.5"]["text"].startswith("5.5 FAIL ")
    assert r["ok"] is True and r["status"] == "proven_on_history" and (ROOT / "syn_thin" / "sim" / f"{FLEX}.json").is_file()      # a fail is a result, and it is saved
    assert "do not meet" in r["next"] and "eval-card" not in r["next"]
    # the bar is read with the line's own comparison ("or more"), each phase against its own number
    met = lambda e, p: PO.bar({"eval": {"p": e}, "payout": {"p": p}})  # noqa: E731
    assert met(0.60, 0.75) and not met(0.5999, 0.75) and not met(0.60, 0.7499) and met(1.0, 1.0)             # line 5.3: the portfolio's numbers
    one = lambda e, p: PO.bar({"eval": {"p": e}, "payout": {"p": p}}, "5.5")  # noqa: E731
    assert one(0.50, 0.50) and not one(0.4999, 0.50) and not one(0.50, 0.4999) and not PO.bar({"eval": {"p": 0.55}, "payout": {"p": 0.55}})      # ... and line 5.5: one strategy's
    unconfirmed = PO.sim("syn_thin", "apex-eod-50k@2026-09-27b", 2, 280.0, ROOT, paths=200)
    assert unconfirmed["account"]["confirmed"] is False and "unconfirmed rules" in unconfirmed["text"]


# ================================================================ (g) the portfolio: several proven strategies on one account

UP = [SY.trade(d, 60.0 if i % 2 else -20.0, 10.0) for i, d in enumerate(SY.weekdays())]                # $20 a micro a day on average, a losing day every other day
DOWN = [SY.trade(d, -20.0 if i % 2 else 60.0, 10.0, at="10:15") for i, d in enumerate(SY.weekdays())]  # the same, on the OTHER days: together $40 a micro-pair every day
DRAG = [SY.trade(d, 6.0 if i % 2 else -5.0, 120.0, at="10:40") for i, d in enumerate(SY.weekdays())]    # next to nothing a day, far under water first


def member(name: str, trades: list, family: str) -> None:
    proven(name, cells={"v": trades}, worse={"v": trades}, survivors=["v"], lock_more={"spec": {"run": {"family": family}}})


def test_a_portfolio_is_read_on_lines_5_2_5_3_5_6_and_5_7():
    member("pf_up", UP, "orb")
    member("pf_down", DOWN, "ib")
    with SY.no_engine():
        r = RESULTS["portfolio"] = PO.portfolio(["pf_up", "pf_down"], PRO_FREE, ROOT, paths=2000)
    assert tuple(r)[:len(CONTRACT)] == CONTRACT and (r["ok"], r["command"], r["name"], r["phase"]) == (True, "portfolio", "pf_up+pf_down", 5)
    json.dumps(r)
    assert [x["line"] for x in r["lines"]] == ["5.2", "5.3", "5.6", "5.7"] and all(x["passed"] is True for x in r["lines"]), [x["text"] for x in r["lines"]]
    assert r["passed"] is True and "meets its bar" in r["next"]
    # the members: each one's DEFAULT variant (its lock's), on the days they share
    assert [(m["name"], m["variant"], m["survivor"], m["market"], m["trades"]) for m in r["members"]] == [("pf_up", "v", True, "NQ", 44), ("pf_down", "v", True, "NQ", 44)]
    assert r["range"] == {"start": SY.SPAN[0], "end": SY.SPAN[1]} and r["pool"] == {"days": 44, "traded": 44} and r["days"] == {"eval": 10, "payout": 20}
    # every member at the same size step, inside the account's maximum FOR ALL OF THEM: 40 micros in the eval, 20 from the funded account's start
    assert [x["size"] for x in r["table"]] == [1, 2, 3, 5, 7, 10, 15, 20] and [x["size"] for x in r["table"] if x["payout"]] == [1, 2, 3, 5, 7, 10]
    # ONE ledger: a day of the portfolio is the members' day together (no daily limit on this account: the plain sum)
    rules, cal = PS.load_rules(PRO_FREE), SY.weekdays()
    hu, hd = PO.handed("pf_up", ROOT), PO.handed("pf_down", ROOT)
    cu, cd = PO.cell(hu, "v"), PO.cell(hd, "v")
    both = PO.days(PO.together([cu, cd], 5, rules, cal), rules, cal)
    one = [PO.days(PO.ledger(c, 5, rules), rules, cal) for c in (cu, cd)]
    assert np.allclose(both[0], one[0][0] + one[1][0]) and both[0].min() > 0 and one[0][0].min() < 0 and both[3] == cal        # together: no losing day; alone: every other
    assert PO.table([cu, cd], rules, cal, paths=2000) == r["table"], "the same seed, the same answer"
    assert PO.together([cu, cd], 5, rules, cal[:10])[-1]["date"] == cal[9], "a day the members do not share is not in the ledger"
    # 5.3 the portfolio's bar, at its best sizes (line 5.3's odds: within its days)
    ch, L = r["chosen"], by(r)
    assert L["5.3"]["need"] == R.need("5.3") and L["5.3"]["number"] == {"eval": ch["eval"]["p"], "payout": ch["payout"]["p"]} and ch["margin"] >= 1.0
    assert ch["eval"]["p"] >= 0.60 and ch["payout"]["p"] >= 0.75 and PO.bar(ch) and "micros each" in L["5.3"]["text"]
    # 5.7 every member raises the portfolio's eval odds: without it the rest reads lower (alone, at its own best size of the whole account)
    assert all(m["helps"] and m["without"]["eval"] < ch["eval"]["p"] for m in r["members"])
    alone = PO.read("pf_down", PO.table(cd, rules, cal, paths=2000), "5.3")["eval"]["p"]
    assert r["members"][0]["without"]["eval"] == alone and "without pf_up" in L["5.7"]["text"] and "with all" in L["5.7"]["text"]
    assert L["5.6"]["number"] == 0 and "no two are the same idea on the same market" in L["5.6"]["text"] and r["doubles"] == []
    # saved in the ideas folder, beside the ideas
    f = ROOT / "_portfolios" / f"{PRO_FREE}__pf_up+pf_down.json"
    assert r["saved"] == [str(f)] and read(f)["lines"] == r["lines"] and read(f)["table"] == r["table"]
    text = r["text"].splitlines()
    assert text[0].startswith("PORTFOLIO of pf_up + pf_down (phase 5)") and PO.LABEL in r["text"] and all(x["text"] in text for x in r["lines"]) and text[-1] == r["next"]


def test_a_double_and_a_member_that_drags_fail_their_lines():
    member("pf_up", UP, "orb")
    member("pf_down", DOWN, "ib")
    member("pf_twin", DOWN, "orb")                                                # the same entry trigger as pf_up, on the same market
    member("pf_drag", DRAG, "vwap")
    r = PO.portfolio(["pf_up", "pf_twin"], PRO_FREE, ROOT, paths=2000)
    L = by(r)
    assert L["5.6"]["passed"] is False and L["5.6"]["number"] == 1 and "pf_up and pf_twin" in L["5.6"]["text"] and "the same entry trigger on the same market (orb, NQ)" in L["5.6"]["text"]
    assert r["passed"] is False and r["doubles"] == [{"a": "pf_up", "b": "pf_twin", "why": "the same entry trigger on the same market (orb, NQ)"}] and "5.6" in r["next"]
    r = PO.portfolio(["pf_up", "pf_down", "pf_drag"], PRO_FREE, ROOT, paths=2000)
    L, m = by(r), {x["name"]: x for x in r["members"]}
    assert m["pf_drag"]["helps"] is False and m["pf_drag"]["without"]["eval"] >= r["chosen"]["eval"]["p"]      # without it the other two read as well or better
    assert L["5.7"]["passed"] is False and "pf_drag" in L["5.7"]["text"].split(" -- ")[-1] and "stay" in L["5.7"]["text"] and r["passed"] is False and "5.7" in r["next"]
    assert [x["size"] for x in r["table"]] == [1, 2, 3, 5, 7, 10], "three members: 13 micros each would be 39, 15 each is past the account's 40"


def test_what_a_portfolio_refuses():
    member("pf_up", UP, "orb")
    member("pf_down", DOWN, "ib")
    proven("pf_failed", test_fail=("4.5",))
    before = sorted(p.name for p in (ROOT / "_portfolios").glob("*")) if (ROOT / "_portfolios").exists() else []
    refused(lambda: PO.portfolio(["pf_up"], PRO_FREE, ROOT), "two or more DIFFERENT ideas")
    refused(lambda: PO.portfolio(["pf_up", "pf_up"], PRO_FREE, ROOT), "two or more DIFFERENT ideas")
    refused(lambda: PO.portfolio(["pf_up", "pf_down"], "", ROOT), "--account=ID")
    refused(lambda: PO.portfolio(["pf_up", "pf_down"], "nobody@1", ROOT), "nobody@1", PRO)
    refused(lambda: PO.portfolio(["pf_up", "pf_failed"], PRO_FREE, ROOT), "pf_failed", "SHELVED", "did not pass")      # line 5.6: every member proven on its own
    refused(lambda: PO.portfolio(["pf_up", "pf_nobody"], PRO_FREE, ROOT), "no idea pf_nobody")
    assert before == (sorted(p.name for p in (ROOT / "_portfolios").glob("*")) if (ROOT / "_portfolios").exists() else [])
    rc, txt = _run(["portfolio", "pf_up", "pf_down", f"--account={PRO_FREE}", f"--root={ROOT}", "--json"])
    r = json.loads(txt)
    assert rc == 0 and r["command"] == "portfolio" and r["name"] == "pf_up+pf_down" and r["paths"] == PS.N_PATHS and [x["line"] for x in r["lines"]] == ["5.2", "5.3", "5.6", "5.7"]
    rc, txt = _run(["portfolio", "pf_up", f"--account={PRO_FREE}", f"--root={ROOT}", "--json"])
    assert rc == 2 and json.loads(txt)["ok"] is False and "two or more" in json.loads(txt)["error"]


def _run(argv: list, stdin: str = "") -> tuple:
    out, keep = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out):
            rc = C.main(argv)
    finally:
        sys.stdin = keep
    return rc, out.getvalue()


def test_the_command_line_as_the_connector_writes_it():
    proven("syn_cli")
    tail = [f"--root={ROOT}", "--json"]
    q = subprocess.run([sys.executable, str(W / "bp.py"), "sim", "syn_cli", f"--account={PRO}", "--attempts=3", "--fee-budget=345", *tail], capture_output=True,
                       text=True, timeout=280, cwd=str(W), stdin=subprocess.DEVNULL, env={**os.environ})
    assert q.returncode == 0 and q.stdout.count("\n") == 1, (q.stdout[-400:], q.stderr[-1500:])
    r = RESULTS["cli"] = json.loads(q.stdout)
    assert tuple(r)[:len(CONTRACT)] == CONTRACT and r["paths"] == PS.N_PATHS == 20_000 and [x["passed"] for x in r["lines"]] == [True, True, None, True, True]
    assert r["chosen"]["variant"] == "v_good" and r["fee_budget"] == 345.0 and (ROOT / "syn_cli" / "sim" / f"{PRO}.json").is_file()
    for argv, word in ((["sim", "syn_cli", f"--account={PRO}", "--attempts=3"], "fee budget"), (["sim", "syn_cli", f"--account={PRO}", "--fee-budget=345"], "attempts"),
                       (["sim", "syn_cli", "--attempts=3", "--fee-budget=345"], "--account"),
                       (["sim", "syn_cli", "--account=nobody@1", "--attempts=3", "--fee-budget=345"], "nobody@1"),
                       (["sim", "syn_nobody", f"--account={PRO}", "--attempts=3", "--fee-budget=345"], "no idea"), (["sim", f"--account={PRO}"], "name")):
        rc, out = _run([*argv, *tail])
        got = json.loads(out)
        assert rc == 2 and got["ok"] is False and word in got["error"] and got["command"] == "sim" and "not built yet" not in got["error"], (argv, got["error"])
    rc, out = _run(["sim", "syn_cli", f"--account={PRO_FREE}", "--attempts=1", "--fee-budget=0", f"--root={ROOT}"])        # for a person: the text, then the next step
    assert rc == 0 and out.startswith("SIM of syn_cli") and PO.LABEL in out and "\nNEXT: " in out and "5.4 PASS" in out


CONNECTOR = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from homebase.claude_mcp import tools
from homebase.claude_mcp.client import Client, ToolError
box, out = tools.Toolbox(Client("http://127.0.0.1:1"), sleep=lambda s: None), []
for tool, args in json.loads(sys.argv[2]):
    try:
        out.append(["ok", box.call(tool, args)])
    except ToolError as e:
        out.append(["error", str(e)])
print(json.dumps(out))
'''


def connector(calls: list, root=ROOT) -> list:
    """The app's own blueprint tools (homebase/claude_mcp), run with the app's Python against THIS toolkit in the temp folders."""
    q = subprocess.run([str(APP_PYTHON), "-B", "-c", CONNECTOR, str(S.REPO), json.dumps(calls)], capture_output=True, text=True, timeout=600, cwd=str(TMP),
                       env={**os.environ, "HOMEBASE_IDEAS_ROOT": str(root), "HOMEBASE_DRAFTS_DIR": str(DRAFTS), "HOMEBASE_BP": str(W / "bp.py"),
                            "HOMEBASE_BP_PYTHON": sys.executable})
    assert q.returncode == 0, q.stderr[-2000:]
    return json.loads(q.stdout)


def test_the_apps_connector_against_this_toolkit():
    if not APP_PYTHON.exists():
        import pytest
        pytest.skip("the app's Python is not there")
    proven("syn_conn")
    SY.proven(IS, ROOT, "syn_lead")
    (ok, text), (bad, why), (bad2, why2) = RESULTS["connector"] = connector([
        ["blueprint_sim", {"name": "syn_conn", "account": PRO, "attempts": 3, "fee_budget": 345}],
        ["blueprint_sim", {"name": "syn_lead", "account": PRO, "attempts": 3, "fee_budget": 345}],
        ["blueprint_sim", {"name": "syn_conn", "account": "nobody@1", "attempts": 3, "fee_budget": 345}]])
    out = text.splitlines()
    assert ok == "ok" and out[0] == "Blueprint sim · syn_conn · PROVEN ON HISTORY · phase 5" and PO.LABEL in text
    assert "Lines: 4 passed · 0 FAILED · 1 not judged or does not apply (5.3)" in out and any(ln.startswith("Next: ") for ln in out) and any(ln.startswith("Saved: ") and f"{PRO}.json" in ln for ln in out)
    assert all(text.count(f"\n{k} PASS ") == 1 for k in ("5.1", "5.2", "5.4", "5.5")), "each line once"
    assert bad == "error" and why.startswith("Refused (blueprint sim): ") and "out-of-sample test is not on file" in why and "Nothing was run." in why
    assert bad2 == "error" and "nobody@1" in why2 and PRO in why2


def test_nothing_was_written_outside_the_temp_folder():
    assert BEFORE == {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies")}
    assert not list((W / "runs_bp").glob("syn_*")) and not list((W / "runs_bp_test").glob("syn_*"))
    assert not list((S.REPO / "homebase" / "backtest" / "propsim").glob("__pycache__/*39*")), "bytecode was written into homebase/"
    assert not (TMP / "ideas_env").exists(), "a command fell back to the environment's idea folder"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        except Exception as e:  # noqa: BLE001 - pytest.skip outside pytest, a crash: said, and the run goes on
            skip = type(e).__name__ == "Skipped"
            rc = rc if skip else 1
            print(f"{'SKIP' if skip else 'CRASH'} {name}: {e}", flush=True)
        finally:
            teardown_function()
    if "sim" in RESULTS:
        print("\n" + RESULTS["sim"]["text"] + "\nNEXT: " + RESULTS["sim"]["next"])
    if "connector" in RESULTS:
        print("\nTHE CONNECTOR, blueprint_sim:\n" + RESULTS["connector"][0][1] + "\n\nrefused:\n" + RESULTS["connector"][1][1])
    sys.exit(rc)
