#!/usr/bin/python3
"""Plain-assert tests for evalcore. Run: /usr/bin/python3 test_evalcore.py  (also collectable by pytest)."""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                                   # noqa: E402
from evalcore import PS                                # noqa: E402

B1 = "20260929-181648-draft_nq_long_930_sltp-3e90"    # 752 trades 2022-2024
B2 = "20260929-180142-nq930-aa4f"                     # 2021-2024 trades only (2025+ dropped at load)
LUCID, APEX = E.firm_rules("lucid"), E.firm_rules("apex")
CAL = [(dt.date(2023, 3, 6) + dt.timedelta(i)).isoformat() for i in range(21)
       if (dt.date(2023, 3, 6) + dt.timedelta(i)).weekday() < 5]        # 15 weekdays


def tr(date, hhmm, gross, mae=0.0, side="long", dur=5, sl=None):
    """Synthetic trade dict (per 1 NQ) entering at hhmm ET for `dur` minutes."""
    h, m = map(int, hhmm.split(":"))
    ms = int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time(h, m), E.ET).timestamp() * 1000)
    return {"date": date, "side": side, "gross": gross, "mae_usd": mae, "entry_ms": ms, "exit_ms": ms + dur * 60000,
            "entry_price": 15000.0, "sl": sl}


def port(members, cal=CAL):
    """members: list of (trades, micros)."""
    return E.build({"members": [{"src": t, "micros": n} for t, n in members], "start": cal[0], "end": cal[-1]}, cal)


def day0(members, rules, cap=40, want_chk=True):
    P = port(members)
    return P, E.walk(P, cap, E.norm_rules(rules), want_chk=want_chk)


def path_arr(pnls, flags=None):
    pnls = np.asarray(pnls, float)
    return E.DayArr(pnls, pnls.copy(), np.asarray(flags if flags is not None else pnls != 0, bool))


def one(pnls, r, flags=None, breach="eod"):
    o, d = E.race(np.arange(len(pnls))[None, :], path_arr(pnls, flags), r, breach)
    return int(o[0]), int(d[0])


# ---------------------------------------------------------------- engine parity

def test_eod_equals_propsim_run_eval():
    rng = np.random.default_rng(7)
    for rid, r in (LUCID, APEX):
        N, H = 500, 60
        pnl = rng.normal(40, 480, (N, H)) * (rng.random((N, H)) > 0.2)      # ~20% no-trade days
        flg = pnl != 0
        A = E.DayArr(pnl.ravel(), pnl.ravel().copy(), flg.ravel())
        out, day = E.race(np.arange(N * H).reshape(N, H), A, r, "eod")
        cnt = {0: 0, 1: 0, 2: 0}
        for i in range(N):
            ref = PS.run_eval([(float(p), bool(f)) for p, f in zip(pnl[i], flg[i])], r)
            code = {"timeout": 0, "pass": 1, "bust": 2}[ref["outcome"]]
            assert out[i] == code, (rid, i, out[i], ref)
            if code:
                assert day[i] == ref["day"], (rid, i, day[i], ref)
            cnt[code] += 1
        assert cnt[1] >= 20 and cnt[2] >= 20, (rid, cnt)      # not a degenerate comparison


def test_funded_equals_propsim_run_funded():
    rng = np.random.default_rng(11)
    for rid, r in (LUCID, APEX):
        N, H = 300, 60
        pnl = rng.normal(90, 350, (N, H)) * (rng.random((N, H)) > 0.15)
        A = E.DayArr(pnl.ravel(), pnl.ravel().copy(), pnl.ravel() != 0)
        x = E.race_funded(np.arange(N * H).reshape(N, H), [A], [], r, "eod")
        n_pay = 0
        for i in range(N):
            ref = PS.run_funded([float(p) for p in pnl[i]], r)
            assert x["pay"][i] == (ref["payout_at"] or 0) and x["mx"][i] == (ref["max_payout_at"] or 0)
            assert x["bust"][i] == (ref["bust_at"] or 0)
            assert abs(x["chq"][i] - (ref["cheque"] or 0.0)) < 1e-9
            n_pay += ref["payout_at"] is not None
        assert n_pay >= 20


# ---------------------------------------------------------------- lucid gates

def test_lucid_consistency_and_min_days():
    _, lu = LUCID
    _, ap = APEX
    assert one([3100], lu) == (0, 0)                        # single big day: min days + consistency
    assert one([3100], ap) == (1, 1)                        # Apex: 1 day, no consistency
    assert one([1600, 1500], lu) == (0, 0)                  # 1600 > 50% of 3100
    assert one([1600, 1500, 100], lu) == (1, 3)             # 1600 <= 50% of 3200 on day 3
    assert one([1400, 1400, 300], lu) == (1, 3)
    r2 = dict(lu, consistency=None)                         # min days alone (2 traded days)
    assert one([3100, 10], r2) == (1, 2)
    assert one([3100, 0], r2, flags=[True, False]) == (0, 0)   # a no-trade day is not a trading day
    for p in ([1600, 1500, 100], [3100], [1400, 1400, 300]):
        assert PS.run_eval([(x, True) for x in p], lu)["outcome"] == ("pass" if one(p, lu)[0] == 1 else "timeout")


def test_lock_at_2100():
    _, lu = LUCID
    # +2100, +700 -> peak 2800 locks the floor at +100 (unlocked it would trail to 800)
    assert one([2100, 700, -2000], lu) == (0, 0)            # 800 > 100: alive (would be a bust without the lock)
    assert one([2100, 700, -2000, -699], lu) == (0, 0)      # 101 > 100: alive
    assert one([2100, 700, -2000, -700], lu) == (2, 4)      # profit == floor is a breach (<=)
    assert one([2100, 700, -2000, -701], lu) == (2, 4)
    for p in ([2100, 700, -2000, -700], [2100, 700, -2000, -699], [2100, 700, -2000, -701], [1000, -2000]):
        ref = PS.run_eval([(x, True) for x in p], lu)
        o, d = one(p, lu)
        assert {"timeout": 0, "pass": 1, "bust": 2}[ref["outcome"]] == o, (p, ref, o)


# ---------------------------------------------------------------- cost model / sizing

def test_micros_cost_model():
    assert [E.cost(n) for n in (1, 9, 10, 15, 25, 40, 100)] == [1.0, 9.0, 4.0, 9.0, 13.0, 16.0, 40.0]
    _, A = day0([([tr("2023-03-06", "10:00", 200.0)], 25)], {})
    assert abs(A.tot[0] - 487.0) < 1e-9                                        # 25*200/10 - (2*4 + 5*1)
    _, A = day0([([tr("2023-03-06", "10:00", 200.0)], 1)], {})
    assert abs(A.tot[0] - 19.0) < 1e-9
    _, A = day0([([tr("2023-03-06", "10:00", 200.0, mae=100.0)], 10)], {})     # 1 NQ == tester net
    assert abs(A.tot[0] - 196.0) < 1e-9 and abs(A.worst[0] - (-100 - 4)) < 1e-9
    P = port([([tr("2023-03-06", "10:00", 200.0, sl=14990.0)], 10)])           # 10 pt stop = $200 on 10 micros
    a = E.walk(P, 40, E.norm_rules({}))
    assert abs(a.st["cost"] / a.st["risk"] - (4 + 10) / 200.0) < 1e-9
    _, A = day0([([tr("2023-03-06", "10:00", 200.0)], 60)], {}, cap=40)        # clipped to the firm cap
    assert abs(A.tot[0] - (40 * 20 - 16.0)) < 1e-9 and A.st["clipped"] == 1


def test_real_bundle_daily_series_equals_tester_net():
    t = E.load(B1)
    P = E.build({"members": [{"src": B1, "micros": 10}]})
    A = E.walk(P, 40, E.norm_rules({}))
    raw = json.loads((E.RUNS / B1 / "trades.json").read_text())
    by = {}
    for x in raw:
        by[x["date"]] = by.get(x["date"], 0.0) + x["net"]
    assert t.n == len(raw) == 752
    got = {P.iso[i]: A.tot[i] for i in range(len(P.iso)) if A.trd[i]}
    assert got.keys() == by.keys() and all(abs(got[k] - by[k]) < 1e-6 for k in by)
    assert len(P.iso) == 754                                                    # tester: 754 sessions
    t2 = E.load(B2)
    assert t2.date.max() < dt.date(2025, 1, 1).toordinal() and t2.n == 823      # 2025+ never loaded


def test_holdout_guard():
    try:
        E.build({"members": [{"src": B1}], "end": "2025-06-30"})
    except ValueError:
        return
    raise AssertionError("2025+ end must be refused without holdout=True")


# ---------------------------------------------------------------- day rules

D1 = "2023-03-06"


def test_day_stop_via_mae():
    a, b = tr(D1, "10:00", 500.0, mae=2500.0), tr(D1, "11:00", 300.0)
    _, A = day0([([a, b], 10)], {"day_stop": 1000})
    assert abs(A.tot[0] - (-1000 - 0.5 * 10)) < 1e-9 and A.st["executed"] == 1 and A.st["skipped"] == 1
    _, A = day0([([a, b], 10)], {})
    assert abs(A.tot[0] - (496 + 296)) < 1e-9 and abs(A.worst[0] - (-2504)) < 1e-9
    _, A = day0([([a, b], 20)], {"day_stop": 1000})                              # MAE scales with size
    assert abs(A.tot[0] - (-1000 - 0.5 * 20)) < 1e-9
    _, A = day0([([a, b], 20)], {})
    assert abs(A.worst[0] - (-2500 * 2 - 8)) < 1e-9
    c = tr(D1, "10:00", -100.0, mae=150.0)                                        # dip never reaches the limit
    _, A = day0([([c, b], 10)], {"day_stop": 1000})
    assert abs(A.tot[0] - (-104 + 296)) < 1e-9 and A.st["executed"] == 2


def test_day_lock_and_max_day_tr():
    a, b, c = tr(D1, "10:00", 604.0), tr(D1, "11:00", 300.0), tr(D1, "12:00", 300.0)
    _, A = day0([([a, b], 10)], {"day_lock": 600})                                # +600 closed -> stop
    assert abs(A.tot[0] - 600) < 1e-9 and A.st["executed"] == 1
    _, A = day0([([a, b], 10)], {"day_lock": 700})
    assert abs(A.tot[0] - 896) < 1e-9
    _, A = day0([([a, b, c], 10)], {"max_day_tr": 2})
    assert A.st["executed"] == 2 and A.st["skipped"] == 1


def test_after_loss_and_after_win():
    l, w = tr(D1, "10:00", -204.0), tr(D1, "11:00", 100.0)
    _, A = day0([([l, w], 20)], {"after_loss": 0.5})
    assert abs(A.tot[0] - ((20 * -204 / 10 - 8) + (10 * 100 / 10 - 4))) < 1e-9    # 2nd trade 10 micros
    _, A = day0([([l, w], 20)], {})
    assert abs(A.tot[0] - ((20 * -204 / 10 - 8) + (20 * 100 / 10 - 8))) < 1e-9
    win, w2 = tr(D1, "10:00", 100.0), tr(D1, "11:00", 100.0)
    _, A = day0([([win, w2], 20)], {"after_win": 1.5})                            # 20 -> 30 micros
    assert abs(A.tot[0] - ((20 * 10 - 8) + (30 * 10 - 12))) < 1e-9
    _, A = day0([([l, w], 1)], {"after_loss": 0.1})                               # floor at >= 1 micro
    assert A.st["executed"] == 2 and abs(A.tot[0] - ((-204 / 10 - 1) + (100 / 10 - 1))) < 1e-9
    w0, l0, x1 = tr(D1, "10:00", 100.0), tr(D1, "11:00", -204.0), tr("2023-03-07", "10:00", 100.0)
    _, A = day0([([w0, l0, x1], 20)], {"after_loss": 0.5})                        # day 1 ends on a loss; day 2 resets
    assert abs(A.tot[1] - (20 * 10 - 8)) < 1e-9


def test_target_stop():
    _, ap = APEX
    _, lu = LUCID
    a, b = tr(D1, "10:00", 3104.0), tr(D1, "11:00", -1000.0)
    P = port([([a, b], 10)])
    idx = np.arange(5)[None, :]
    A0, A1 = (E.walk(P, 100, E.norm_rules({"target_stop": ts}), want_chk=True) for ts in (False, True))
    assert abs(A0.tot[0] - (3100 - 1004)) < 1e-9
    assert E.race(idx, A0, ap, "eod", False)[0][0] == 0                            # trades on, misses the target
    o, d = E.race(idx, A1, ap, "eod", True)
    assert (o[0], d[0]) == (1, 1)                                                  # stopped at +3100 -> pass day 1
    assert E.race(idx, A1, lu, "eod", True)[0][0] == 0                             # Lucid: consistency blocks
    # Lucid: day3 +400 first trade reaches 3,200 with consistency OK, then a -600 trade is skipped
    t = [tr("2023-03-06", "10:00", 1404.0), tr("2023-03-07", "10:00", 1404.0),
         tr("2023-03-08", "10:00", 404.0), tr("2023-03-08", "11:00", -596.0)]
    P = port([(t, 10)])
    for ts, want in ((False, 0), (True, 1)):
        A = E.walk(P, 40, E.norm_rules({"target_stop": ts}), want_chk=True)
        o, d = E.race(np.arange(5)[None, :], A, lu, "eod", ts)
        assert o[0] == want and (not want or d[0] == 3), (ts, o, d)


# ---------------------------------------------------------------- overlaps / portfolio

def test_overlap_conflicts_and_concurrency():
    a = tr(D1, "10:00", 100.0, mae=400.0, side="long", dur=30)
    b = tr(D1, "10:10", -50.0, mae=300.0, side="short", dur=30)
    P = port([([a], 10), ([b], 30)])
    A = E.walk(P, 40, E.norm_rules({}))
    assert A.st["conflicts"] == 1 and A.st["overlap"] == 1 and A.st["max_conc"] == 40 and A.st["cap_viol"] == 0
    assert abs(A.tot[0] - (96 + (30 * -5 - 12))) < 1e-9
    assert abs(A.worst[0] - (-404 + (-900 - 12))) < 1e-9                          # realised + concurrent worst points
    P = port([([a], 10), ([b], 35)])
    A = E.walk(P, 40, E.norm_rules({}))
    assert A.st["max_conc"] == 45 and A.st["cap_viol"] == 1
    c = tr(D1, "10:10", 50.0, mae=10.0, side="long", dur=30)                       # same-side overlap: no conflict
    A = E.walk(port([([a], 10), ([c], 10)]), 40, E.norm_rules({}))
    assert A.st["conflicts"] == 0 and A.st["overlap"] == 1
    A = E.walk(port([([a], 10), ([b], 30)]), 40, E.norm_rules({"day_stop": 1000}))  # stop counts concurrent worst
    assert abs(A.tot[0] - (-1000 - 0.5 * 30)) < 1e-9                               # whole day closed at -Y - 1 tick/contract


def test_sessions_and_news_filter():
    ts = [tr(D1, "01:00", 10.0), tr(D1, "04:00", 10.0), tr(D1, "09:30", 10.0), tr(D1, "12:00", 10.0),
          tr(D1, "14:00", 10.0)]
    for sess, n in (("asia", 1), ("london", 1), ("nyam", 1), ("mid", 1), ("pm", 1), ("all", 5), ("nyam+pm", 2)):
        P = E.build({"members": [{"src": ts, "sess": sess}], "start": CAL[0], "end": CAL[-1]}, CAL)
        assert P.n_trades == n, (sess, P.n_trades)


# ---------------------------------------------------------------- rolling starts

def test_rolling_start_counting_with_no_trade_weekdays():
    rid, ap = APEX
    cal = CAL[:12]
    # one trade day, 11 no-trade weekdays
    r = E.evaluate({"members": [{"src": [tr(cal[6], "10:00", 3110.0)], "micros": 10}], "start": cal[0], "end": cal[-1],
                    "firms": ["apex"]}, calendar=cal, mc=0, eventual=0, funded=False, boots=0)
    f = r["firms"][rid]["eod"]
    assert r["window"]["sessions"] == 12 and f["n"] == 8                            # every session starts an attempt
    assert abs(f["p_pass"] - 5 / 8) < 1e-12 and f["p_bust"] == 0
    assert f["med_days_pass"] == 3.0                                                # days 5,4,3,2,1 (no-trade days count)
    assert [round(x * 8) for x in f["pass_by"]] == [1, 2, 3, 4, 5]
    assert abs(f["p_neither"] - 3 / 8) < 1e-12
    # a weekday absent from the tape calendar is not a session
    cal2 = [d for d in cal if d != cal[3]]
    r = E.evaluate({"members": [{"src": [tr(cal[6], "10:00", 3110.0)], "micros": 10}], "start": cal[0], "end": cal[-1],
                    "firms": ["apex"]}, calendar=cal2, mc=0, eventual=0, funded=False, boots=0)
    assert r["window"]["sessions"] == 11 and r["firms"][rid]["eod"]["n"] == 7


def test_intraday_breach_is_a_sensitivity_only():
    rid, ap = APEX
    A = E.DayArr(np.array([500.0, 0, 0, 0, 0]), np.array([-2100.0, 0, 0, 0, 0]), np.array([1, 0, 0, 0, 0], bool))
    idx = np.arange(5)[None, :]
    assert E.race(idx, A, ap, "eod")[0][0] == 0                                     # EOD +500: alive
    assert E.race(idx, A, ap, "intraday")[0][0] == 2                                # same path busts intraday


# ---------------------------------------------------------------- real bundles + runtime

def test_real_bundles_runtime():
    times = []
    cases = [("B1 10mu plain", [{"src": B1, "micros": 10}], {}),
             ("B1 20mu day_stop 900 lock 600", [{"src": B1, "micros": 20}], {"day_stop": 900, "day_lock": 600}),
             ("B2 40mu day_stop 800 tstop", [{"src": B2, "micros": 40}], {"day_stop": 800, "target_stop": True}),
             ("B1+B2 portfolio 20+20", [{"src": B1, "micros": 20}, {"src": B2, "micros": 20}], {"max_day_tr": 3})]
    for name, mem, rules in cases:
        t = time.perf_counter()
        r = E.evaluate({"members": mem, "rules": rules, "tag": "test_tmp"}, eventual=0, funded=False)
        core = time.perf_counter() - t
        t = time.perf_counter()
        r2 = E.evaluate({"members": mem, "rules": rules, "tag": "test_tmp"})
        full = time.perf_counter() - t
        assert core <= 2.0, (name, core)                                            # spec: <= 2 s per config
        for rid, f in r2["firms"].items():
            e, i = f["eod"], f["intraday"]
            assert i["p_bust"] >= e["p_bust"] - 1e-12 and i["p_pass"] <= e["p_pass"] + 1e-12
            assert 0 <= e["p_pass"] <= 1 and abs(e["p_pass"] + e["p_bust"] + e["p_neither"] - 1) < 1e-9
        times.append((name, core, full))
        print(f"    {name}: core(no eventual/funded) {core:.2f}s, full {full:.2f}s | {E.line(r2)[:150]}")
    return times


def test_search_runtime_and_shape():
    t = time.perf_counter()
    rows = E.search({"members": [{"src": B1, "micros": 10}]}, {"micros": [10, 20], "day_lock": [0, 600],
                                                              "day_stop": [0, 900], "max_day_tr": [0, 1],
                                                              "after_loss": [1.0, 0.5], "target_stop": [False, True]})
    dt_ = time.perf_counter() - t
    assert len(rows) == 2 * 2 * 2 ** 5 and all("stab" in r for r in rows)
    print(f"    search {len(rows)} cells: {dt_:.2f}s ({dt_ / len(rows) * 1000:.1f} ms/cell)")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            t = time.perf_counter()
            try:
                fn()
                print(f"PASS {name} ({time.perf_counter() - t:.2f}s)")
            except Exception as e:                          # noqa: BLE001
                fails += 1
                import traceback
                print(f"FAIL {name}: {e!r}")
                traceback.print_exc(limit=3)
    print("ALL PASS" if not fails else f"{fails} FAILED")
    sys.exit(1 if fails else 0)
