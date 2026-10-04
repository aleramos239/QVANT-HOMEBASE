#!/usr/bin/python3
"""Tests for the breach models 'eod' / 'realized' / 'intraday' and the apex_eod firm variant of evalcore.
Hand cases first (10 micros: cost $4, 1 tick = $5, so a trade with gross g nets g - 4), then a monotonicity property
on random portfolios. Run: /usr/bin/python3 test_evalcore_models.py  (or pytest)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                                            # noqa: E402
from test_evalcore import tr, port, APEX                        # noqa: E402
from test_evalcore_adv import week                              # noqa: E402
from test_evalcore_take import trm                              # noqa: E402

_, AP = APEX
_, AEOD = E.firm_rules("apex_eod")
CAL = week(0, 1, 2, 3, 4)
D1 = CAL[0]
IDX = np.arange(5)[None, :]


def res(P, rules, firm, cap=100, dll=0.0):
    """-> {model: (outcome, day)} for the single attempt starting on day 1 (0 neither, 1 pass, 2 bust)."""
    A = E.walk(P, cap, E.norm_rules(rules), want_chk=True, dll=dll, day_take=E.take_rules(rules)[0])
    tt = E.take_rules(rules)[1]
    return A, {b: tuple(int(x[0]) for x in E.race(IDX, A, firm, b, False, tt)) for b in E.MODELS}


# ---------------------------------------------------------------- definitions / plumbing

def test_firm_variants_and_primary_map():
    rid, r = E.firm_rules("apex_eod")
    assert rid == "apex-eod-50k@2026-09-27b" and r["cap_micros"] == 60 and r["trailing_mll"] == 2000
    assert r["daily_loss_limit"] == 1000 and r["consistency"] is None and r["eval_min_days"] == 1
    assert "apex_eod" not in E.FIRMS                                  # default firm list unchanged
    want = {"lucid": "realized", "lucidpro": "realized", "lucidpro_nodll": "realized",
            "apex": "intraday", "apex_eod": "intraday"}
    for k, m in want.items():
        assert E.primary_model(k) == m and E.primary_model(E.firm_rules(k)[0]) == m, k
    assert E.MODELS == ("eod", "realized", "intraday")
    try:
        E.race(IDX, E.DayArr(np.zeros(5), np.zeros(5), np.zeros(5, bool)), AP, "bogus")
        raise AssertionError("unknown breach model accepted")
    except ValueError:
        pass


def test_hand_built_series_without_realised_falls_back_to_worst():
    A = E.DayArr(np.array([500.0, 0, 0, 0, 0]), np.array([-2100.0, 0, 0, 0, 0]), np.array([1, 0, 0, 0, 0], bool))
    assert [int(E.race(IDX, A, AP, b)[0][0]) for b in E.MODELS] == [0, 2, 2]


# ---------------------------------------------------------------- eod passes, realized busts

def test_realised_intraday_loss_recovered_by_later_trade():
    # -2004 realised after the first close (floor -2000) -> realized bust; the +2496 winner brings EOD to +492 (alive)
    ts = [trm(D1, "10:00", -2000.0, mae=2000.0), trm(D1, "11:00", 2500.0)]
    A, out = res(port([(ts, 10)], CAL), {}, AP)
    assert abs(A.tot[0] - 492) < 1e-9 and abs(A.wreal[0] - (-2004)) < 1e-9
    assert out == {"eod": (0, 0), "realized": (2, 1), "intraday": (2, 1)}
    # the same loss just above the floor (-1994 realised; the 2nd trade's -4 cost keeps intraday at -1998) does not breach
    ts = [trm(D1, "10:00", -1990.0, mae=1990.0), trm(D1, "11:00", 2500.0)]
    _, out = res(port([(ts, 10)], CAL), {}, AP)
    assert out == {"eod": (0, 0), "realized": (0, 0), "intraday": (0, 0)}
    # eod passes outright: -2004 then +5500 -> EOD +3492 >= 3000 (day-1 pass); realized/intraday bust first
    ts = [trm(D1, "10:00", -2000.0, mae=2000.0), trm(D1, "11:00", 5500.0)]
    _, out = res(port([(ts, 10)], CAL), {}, AP)
    assert out == {"eod": (1, 1), "realized": (2, 1), "intraday": (2, 1)}


def test_bust_only_on_the_realised_close_not_a_later_recovery_order():
    # multi-day: floor is the EOD-set one in force that day. Day 1 +1500 (peak 1496 -> floor -504); day 2 realised
    # low -1996 -> profit 1496 - 1996 = -500 > -504 alive; -2000 -> -504 <= -504 bust (realized), eod +100 alive
    d2 = CAL[1]
    for g, want in ((-1992.0, 0), (-1996.0, 2)):
        ts = [trm(D1, "10:00", 1500.0), trm(d2, "10:00", g, mae=-g), trm(d2, "11:00", 2600.0)]
        _, out = res(port([(ts, 10)], CAL), {}, AP)
        assert out["eod"][0] == 0 and out["realized"][0] == want, (g, out)


# ---------------------------------------------------------------- realized vs intraday (open MAE dip)

def test_open_drawdown_alone_never_breaches_realized():
    ts = [trm(D1, "10:00", 100.0, mae=2200.0)]                       # dips to -2204 open, closes +96
    A, out = res(port([(ts, 10)], CAL), {}, AP)
    assert abs(A.worst[0] - (-2204)) < 1e-9 and abs(A.wreal[0] - 0) < 1e-9 and abs(A.tot[0] - 96) < 1e-9
    assert out == {"eod": (0, 0), "realized": (0, 0), "intraday": (2, 1)}
    # a losing trade that ends below the floor is a realised breach for both realized and intraday
    ts = [trm(D1, "10:00", -2100.0, mae=2100.0)]
    _, out = res(port([(ts, 10)], CAL), {}, AP)
    assert out == {"eod": (2, 1), "realized": (2, 1), "intraday": (2, 1)}


def test_concurrent_open_worst_points_do_not_count_for_realized():
    # two overlapping winners each dip -1100 open (sum -2200 - costs): intraday busts, realised never below +96
    a = trm(D1, "10:00", 100.0, mae=1100.0, dur=60)
    b = trm(D1, "10:10", 100.0, mae=1100.0, dur=60, side="short")
    A, out = res(port([([a], 10), ([b], 10)], CAL), {}, AP)
    assert A.worst[0] <= -2200 and abs(A.wreal[0]) < 1e-9
    assert out == {"eod": (0, 0), "realized": (0, 0), "intraday": (2, 1)}


# ---------------------------------------------------------------- portfolio ordering by exit time

def test_overlap_closes_are_ordered_by_exit_time():
    # A enters first and exits last; B enters later and exits first.
    a = trm(D1, "10:00", 500.0, mae=0.0, dur=60)                     # +496, closes 11:00
    b = trm(D1, "10:10", -1997.0, mae=1997.0, dur=10, side="short")  # -2001, closes 10:20 (before A)
    A, out = res(port([([a], 10), ([b], 10)], CAL), {}, AP)
    assert abs(A.wreal[0] - (-2001)) < 1e-9                          # B closes first: realised -2001 before A's +496
    assert out["realized"] == (2, 1) and out["eod"] == (0, 0)
    # swap the roles: the entry-first trade LOSES and exits LAST; the later entry wins and exits first -> never below 0
    a = trm(D1, "10:00", -1997.0, mae=1997.0, dur=60)                # -2001, closes 11:00
    b = trm(D1, "10:10", 2500.0, dur=10, side="short")               # +2496, closes 10:20
    A, out = res(port([([a], 10), ([b], 10)], CAL), {}, AP)
    assert abs(A.wreal[0] - 0) < 1e-9 and abs(A.tot[0] - 495) < 1e-9
    assert out["realized"] == (0, 0) and out["intraday"][0] == 2     # open worst of A: -2001 still busts intraday


# ---------------------------------------------------------------- take rules

def test_take_interplay_realised_path_and_mae():
    # day_take 1000: MFE 1500 fires, trade closes at +995; its MAE (-2104) still busts intraday, not realized
    ts = [trm(D1, "10:00", 300.0, mae=2100.0, mfe=1500.0)]
    A, out = res(port([(ts, 10)], CAL), {"day_take": 1000}, AP)
    assert abs(A.tot[0] - 995) < 1e-9 and abs(A.worst[0] - (-2104)) < 1e-9 and abs(A.wreal[0]) < 1e-9
    assert out == {"eod": (0, 0), "realized": (0, 0), "intraday": (2, 1)}
    # a realised loser BEFORE the taker: -1504 realised (alive), then the taker's exit brings the day to +995
    ts = [trm(D1, "10:00", -1500.0, mae=1500.0), trm(D1, "11:00", 300.0, mfe=3000.0)]
    A, out = res(port([(ts, 10)], CAL), {"day_take": 1000}, AP)
    assert abs(A.tot[0] - 995) < 1e-9 and abs(A.wreal[0] - (-1504)) < 1e-9
    assert out == {"eod": (0, 0), "realized": (0, 0), "intraday": (0, 0)}
    # a take never rescues a realised breach that already happened: -2004 first, then the take trade
    ts = [trm(D1, "10:00", -2000.0, mae=2000.0), trm(D1, "11:00", 300.0, mfe=4000.0)]
    A, out = res(port([(ts, 10)], CAL), {"day_take": 1000}, AP)
    assert abs(A.tot[0] - 995) < 1e-9 and out == {"eod": (0, 0), "realized": (2, 1), "intraday": (2, 1)}


def test_target_take_rewalk_carries_realised_low():
    # target_take: level = 3000 - profit; the taker exits at the pass level, the earlier -1504 close stays in wreal
    ts = [trm(D1, "10:00", -1500.0, mae=1500.0), trm(D1, "11:00", 300.0, mfe=6000.0)]
    P = port([(ts, 10)], CAL)
    A = E.walk(P, 100, E.norm_rules({}), want_chk=True)
    o = {b: int(E.race(IDX, A, AP, b, False, True)[0][0]) for b in E.MODELS}
    assert o == {"eod": 1, "realized": 1, "intraday": 1}             # -1504 alive, then the take path passes
    assert abs(A.rewalk(0, 3000.0)[3] - (-1504)) < 1e-9 and abs(A.rewalk(0, 3000.0)[0] - 3000) < 1e-9


# ---------------------------------------------------------------- apex_eod: DLL day-stop and cap 60

def test_apex_eod_dll_day_stop_via_mae_and_cap():
    dll = E.PS._dll(AEOD)
    assert dll == 1000.0
    # MAE -1500 breaches the $1,000 soft limit: closed at -1000 - 1 tick (n=10 -> -1005), later trade skipped
    ts = [trm(D1, "10:00", 200.0, mae=1500.0), trm(D1, "11:00", 900.0)]
    A, out = res(port([(ts, 10)], CAL), {}, AEOD, cap=60, dll=dll)
    assert abs(A.tot[0] - (-1005)) < 1e-9 and A.st["executed"] == 1 and A.st["skipped"] == 1
    assert abs(A.worst[0] - (-1005)) < 1e-9 and abs(A.wreal[0] - (-1005)) < 1e-9
    assert out == {"eod": (0, 0), "realized": (0, 0), "intraday": (0, 0)}
    # without the DLL the same day dips -1504 and wins
    A, _ = res(port([(ts, 10)], CAL), {}, AEOD, cap=60, dll=0.0)
    assert A.st["executed"] == 2 and A.tot[0] > 0
    # the DLL floor: three such days cannot reach -2000 (each stops at -1005) -> day 2 realised -1005-1005 = -2010 busts
    d2 = CAL[1]
    ts = [trm(D1, "10:00", 200.0, mae=1500.0), trm(d2, "10:00", 200.0, mae=1500.0)]
    _, out = res(port([(ts, 10)], CAL), {}, AEOD, cap=60, dll=dll)
    assert out == {"eod": (2, 2), "realized": (2, 2), "intraday": (2, 2)}


def test_apex_eod_cap_60():
    # 80 micros requested -> clipped to the 60-micro cap: 60*300/10 - cost(60) = 1800 - 24
    ts = [trm(D1, "10:00", 300.0)]
    P = port([(ts, 80)], CAL)
    A = E.walk(P, AEOD["cap_micros"], E.norm_rules({}), dll=1000.0)
    assert A.st["clipped"] == 1 and abs(A.tot[0] - (1800 - 24)) < 1e-9
    A = E.walk(P, 100, E.norm_rules({}))                              # legacy apex cap 100: not clipped
    assert A.st["clipped"] == 0 and abs(A.tot[0] - (2400 - 32)) < 1e-9


def test_evaluate_reports_all_models_and_primary():
    ts = [trm(D1, "10:00", -2000.0, mae=2000.0), trm(D1, "11:00", 2500.0)] + \
         [trm(d, "10:00", 100.0 if i % 3 else -300.0) for i, d in enumerate(week(*[i for i in range(100) if i % 7 < 5][:64])[1:])]
    cal = week(*[i for i in range(100) if i % 7 < 5][:64])
    cfg = {"members": [{"src": ts, "micros": 10}], "start": cal[0], "end": cal[-1], "firms": ["lucid", "apex_eod", "lucidpro"]}
    r = E.evaluate(cfg, calendar=cal, mc=200, boots=50, eventual=0, funded=True)
    assert set(r["firms"]) == {E.firm_rules(k)[0] for k in ("lucid", "apex_eod", "lucidpro")}
    for rid, f in r["firms"].items():
        assert all(m in f for m in E.MODELS) and f["primary"] == E.primary_model(rid) and f["econ"]["model"] == f["primary"]
        assert f["eod"]["p_pass"] >= f["realized"]["p_pass"] >= f["intraday"]["p_pass"]
        assert all(m in f["funded"] for m in E.MODELS) and f["mc_iid"]["model"] == f["primary"]
    assert "real=" in E.line(r)


# ---------------------------------------------------------------- monotonicity property on random paths

def _rand_port(rng, ndays=40, members=2):
    cal = week(*[i for i in range(ndays * 7 // 5 + 2) if i % 7 < 5][:ndays])
    ms = []
    for _ in range(members):
        ts = []
        for d in cal:
            for h in sorted(rng.choice(np.arange(9, 15), size=int(rng.integers(0, 4)), replace=False)):
                g = float(rng.normal(0, 900))
                mae = float(abs(rng.normal(0, 700)) + max(0.0, -g))
                mfe = float(abs(rng.normal(0, 700)) + max(0.0, g))
                ts.append(trm(d, f"{int(h):02d}:{int(rng.integers(0, 50)):02d}", g, mae=mae, mfe=mfe,
                              dur=int(rng.integers(3, 120)), side="long" if rng.random() < .5 else "short"))
        ms.append((ts, int(rng.choice([10, 20, 30, 40]))))
    return port(ms, cal), len(cal)


RULE_SETS = [{}, {"day_stop": 800}, {"day_lock": 600}, {"day_take": 1500}, {"target_take": True}, {"target_stop": True},
             {"day_take": 1000, "day_stop": 1200, "max_day_tr": 2}, {"after_loss": 0.5, "day_lock": 900, "target_take": True}]
MONO_FIRMS = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")


def _monotone_pass(n_ports=25, seed=11):
    """-> (#checks, #strict-gap checks, violations). Attempt-wise: pass(intraday) <= pass(realized) <= pass(eod)
    with identical pass days, and bust(eod) <= bust(realized) <= bust(intraday) as day-of-first-bust ordering."""
    rng = np.random.default_rng(seed)
    n, gaps, viol = 0, 0, []
    for k in range(n_ports):
        P, D = _rand_port(rng, members=1 + k % 2)
        idx = np.arange(D - 5 + 1)[:, None] + np.arange(5)
        for firm in MONO_FIRMS:
            rid, r = E.firm_rules(firm)
            for rules in RULE_SETS:
                rl, dtk = E.norm_rules(rules), E.take_rules(rules)
                A = E.walk(P, r["cap_micros"], rl, want_chk=True, dll=E.PS._dll(r) or 0.0, day_take=dtk[0])
                if not (np.all(A.worst <= A.wreal + 1e-9) and np.all(A.wreal <= A.tot + 1e-9)):
                    viol.append(("day arrays", k, firm, rules))
                o = {b: E.race(idx, A, r, b, rl[5], dtk[1]) for b in E.MODELS}
                pe, pr, pi = (o[b][0] == 1 for b in E.MODELS)
                de, dr, di = (o[b][1] for b in E.MODELS)
                n += 1
                if not (np.all(pi <= pr) and np.all(pr <= pe)) or not (pi.mean() <= pr.mean() <= pe.mean()):
                    viol.append(("P5", k, firm, rules, pi.mean(), pr.mean(), pe.mean()))
                if not (np.all((di == dr)[pi]) and np.all((dr == de)[pr])):
                    viol.append(("pass day", k, firm, rules))
                be, br, bi = (o[b][0] == 2 for b in E.MODELS)
                bad = (be & ~br) | (br & ~bi) | (be & (dr > de)) | (br & (di > dr))
                if bad.any():
                    viol.append(("bust order", k, firm, rules))
                gaps += int(pe.mean() > pr.mean() or pr.mean() > pi.mean())
    return n, gaps, viol


def test_stop_and_take_flatten_the_whole_book_together():
    # A (open until 11:40, +196, dips -504) is open when B (exits 10:50 first) is stopped by day_stop 1000: B's p absorbs A's
    # final P&L (-1205) so the day total is -1005, and the book is flattened at once: realised goes 0 -> -1005, never through -1205.
    a = trm(D1, "10:00", 204.0, mae=500.0, dur=100)
    b = trm(D1, "10:30", -1204.0, mae=1300.0, dur=20, side="short")
    A, out = res(port([([a], 10), ([b], 10)], CAL), {"day_stop": 1000}, AP)
    assert abs(A.tot[0] - (-1005)) < 1e-9 and abs(A.wreal[0] - (-1005)) < 1e-9 and abs(A.worst[0] - (-1709)) < 1e-9
    assert out["realized"] == (0, 0) and out["intraday"] == (0, 0)
    # same for day_take: the taking trade (exits first) absorbs the still-open winner's final P&L (2000): its own p is -1005,
    # yet the flattened book is +995 at once, so realised never dips to -1005
    a = trm(D1, "10:00", 2004.0, mae=0.0, dur=100)                   # open winner, final +2000
    b = trm(D1, "10:30", 300.0, mae=0.0, mfe=4000.0, dur=10, side="short")
    A, _ = res(port([([a], 10), ([b], 10)], CAL), {"day_take": 1000}, AP)
    assert abs(A.tot[0] - 995) < 1e-9 and abs(A.wreal[0]) < 1e-9


def test_monotone_p5_intraday_le_realized_le_eod_random_paths():
    n, gaps, viol = _monotone_pass()
    assert n == 25 * len(MONO_FIRMS) * len(RULE_SETS)
    assert gaps > 20, gaps                                            # the property is not vacuous: the models differ
    assert not viol, viol[:5]


def test_monotone_funded_bust_any():
    rng = np.random.default_rng(3)
    P, D = _rand_port(rng, ndays=60)
    idx = np.arange(D - 40 + 1)[:, None] + np.arange(40)
    for firm in ("lucid", "apex_eod"):
        _, r = E.firm_rules(firm)
        rl = E.norm_rules({})
        As, thr, _ = E._funded_levels(P, r, rl)
        b = {m: (E.race_funded(idx, As, thr, r, m)["bust"] > 0).mean() for m in E.MODELS}
        assert b["eod"] <= b["realized"] <= b["intraday"], (firm, b)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:                                  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:300])
    sys.exit(1 if fails else 0)
