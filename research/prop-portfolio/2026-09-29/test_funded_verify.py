#!/usr/bin/python3
"""Adversarial tests for funded.py: hand-computed multi-day paths (expected numbers worked out by hand from FUNDED_RULES.md, written
BEFORE looking at the code's answers), an independent lifecycle reference (verify_funded_indep.ref_life, absolute-balance terms) fuzzed
against funded.simulate on random day outcomes for every firm / model / policy, and an independent day walk (RefWalk) compared with
funded.walk_day on random real-style trades incl. overlaps, take / stop / lock / MAE cut and the three Apex event orders.
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 -m pytest -q test_funded_verify.py"""
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                                            # noqa: E402
import funded as F                                              # noqa: E402
import verify_funded_indep as V                                 # noqa: E402


class Days:
    """Prescribed day results serving BOTH funded.simulate (8-tuples) and ref_life (dicts).
    day = dict(tot, worst, wreal, n, pts={order: [(kind, v)...]}, scale=(ref_cap)) ; scale: values defined at ref_cap micros, linear in cap."""

    def __init__(self, days):
        self.days = days
        self.n_days = len(days)
        self.log = []

    @property
    def caps(self):
        return [c for _, c, _, _ in self.log]

    def _d(self, i, cap, order):
        d = self.days[i]
        f = cap / d["scale"] if d.get("scale") else 1.0
        pts = d["pts"].get(order, []) if isinstance(d.get("pts"), dict) else d.get("pts", [])
        return dict(tot=d["tot"] * f, worst=d["worst"] * f, wreal=d["wreal"] * f, n=d["n"], pts=[(k, v * f) for k, v in pts], cut=d.get("cut", 0))

    def get(self, i, cap, dll=0.0, lim=0.0, order=None):               # ref side passes order=; funded side gets the 8-tuple
        self.log.append((i, cap, dll, lim))
        o = self._d(i, cap, order or "pess")
        if order is not None:
            return o
        ev = {k: tuple(self._d(i, cap, k)["pts"]) for k in ("pess", "opt", "nat")}
        return (o["tot"], o["worst"], o["wreal"], o["n"], ev["pess"], ev["opt"], o["cut"], ev["nat"])


def clean(x, scale=None, n=1):
    hi = max(x, 0.0)
    pts = [(1, hi), (0, x), (1, x), (0, x)]
    return dict(tot=x, worst=min(x, 0.0), wreal=min(x, 0.0), n=n if x else 0, pts={"pess": pts, "opt": pts, "nat": pts}, scale=scale)


class FDays(Days):
    """funded.simulate wants get() -> tuple; wrap so that the call signature has no `order`."""

    def get(self, i, cap, dll=0.0, lim=0.0):
        return Days.get(self, i, cap, dll, lim, None)


class RDays(Days):
    def get(self, i, cap, dll=0.0, lim=0.0, order="pess"):
        self.log.append((i, cap, dll, lim))
        return self._d(i, cap, order)


def both(spec, kind, days, T=500, model=None, H=None, dll=0.0, **opt):
    H = H or len(days)
    f, r = FDays(days), RDays(days)
    got = F.simulate(spec, f, 0, H, T, model)
    ref = V.ref_life(kind, r, 0, H, T, model or spec.primary, dll=dll, **opt)
    return got, ref, f, r


def pays(res):
    return [(d, round(g, 6), round(n, 6)) for d, g, n in res]


# ------------------------------------------------------------------ hand-computed Flex paths

def test_flex_hand_five_payouts_then_stop():
    # +200/day: day 5 profit 1000 -> cheque 500 (min) ; profit 500. then every 5 days profit +1000: cheque = half of profit.
    days = [clean(200.0, scale=None) for _ in range(40)]
    got, ref, f, r = both(F.make_spec("flex"), "flex", days)
    exp = [(5, 500.0, 450.0), (10, 750.0, 675.0), (15, 875.0, 787.5), (20, 937.5, 843.75), (25, 968.75, 871.875)]
    assert pays(got[1]) == exp and got[0] == 0
    assert pays(ref[1]) == exp
    assert len(f.log) == 25                                        # stopped after the 5th payout (no 26th day simulated)


def test_flex_hand_scaling_tiers_and_cap2000():
    # pnl = 20 * cap: day1-3 cap 20 (+400 each -> 1200); day 4 cap 30 (profit >= 1000) +600 = 1800; day 5 cap 30 -> 2400 and 5 wins ->
    # cheque min(1200, 2000) = 1200 -> profit 1200 -> tier 30 again; day 6 +600 = 1800, day 7 (cap 30) 2400, day 8 cap 40 +800 = 3200,
    # day 9 +800 = 4000, day 10 +800 = 4800 (5 wins) -> cheque min(2400, 2000) = 2000 -> profit 2800
    days = [dict(tot=20.0, worst=0.0, wreal=0.0, n=1, pts={"pess": [], "opt": [], "nat": []}, scale=1) for _ in range(12)]
    got, ref, f, r = both(F.make_spec("flex"), "flex", days)
    assert f.log[:10] and [c for _, c, _, _ in f.log[:10]] == [20, 20, 20, 30, 30, 30, 30, 40, 40, 40]
    assert pays(got[1])[:2] == [(5, 1200.0, 1080.0), (10, 2000.0, 1800.0)]
    assert pays(ref[1])[:2] == pays(got[1])[:2]


def test_flex_hand_150_threshold_and_cycle_net():
    # 4 days of +150 and one of +149: only 4 qualifying wins -> no payout at day 5; a 6th day +300 gives win #5 -> profit 1049.. cheque 524.5
    d = [150, 150, 150, 150, 149, 300]
    days = [clean(float(x)) for x in d]
    got, ref, _, _ = both(F.make_spec("flex"), "flex", days)
    assert pays(got[1]) == [(6, 524.5, 472.05)] == pays(ref[1])
    # cycle net must be > 0: 5 wins of +150 (750, cheque 375 < 500 so no payout), then -800 (profit -50, net -50, wins 5 stay) then +1200
    d = [150] * 5 + [-800, 1200]
    days = [clean(float(x)) for x in d]
    got, ref, _, _ = both(F.make_spec("flex"), "flex", days)
    assert pays(got[1]) == [(7, 575.0, 517.5)] == pays(ref[1])


def test_flex_hand_post_payout_mll_is_plus_100_boundary():
    base = [200] * 5                                              # payout 500 at day 5 -> profit 500, floor +100 (locked)
    for loss, expect_bust in ((-399.0, 0), (-400.0, 6)):
        days = [clean(float(x)) for x in base] + [clean(loss)]
        got, ref, _, _ = both(F.make_spec("flex"), "flex", days)
        assert got[0] == ref[0] == expect_bust, loss
    # without a payout (policy None): profit 1000 floor is peak-2000 = -1000: a -2000 day busts, -1999 survives
    for loss, expect_bust in ((-1999.0, 0), (-2000.0, 6)):
        days = [clean(200.0)] * 5 + [clean(loss)]
        got, ref, _, _ = both(F.make_spec("flex"), "flex", days, T=None)
        assert got[0] == ref[0] == expect_bust, loss


def test_flex_hand_lock_at_2100_without_payout():
    # peak 2100 -> floor locks at +100: afterwards a fall to profit 100 busts (balance <= MLL) but 101 survives, whatever the peak
    days = [clean(2100.0), clean(-1999.0)]                         # profit 101
    got, ref, _, _ = both(F.make_spec("flex"), "flex", days, T=None)
    assert got[0] == ref[0] == 0
    days = [clean(2100.0), clean(-2000.0)]                         # profit 100 -> breach
    got, ref, _, _ = both(F.make_spec("flex"), "flex", days, T=None)
    assert got[0] == ref[0] == 2
    # a peak of 2099 has not locked: floor 99 (peak - 2000): profit 100 survives
    days = [clean(2099.0), clean(-1999.0)]
    got, ref, _, _ = both(F.make_spec("flex"), "flex", days, T=None)
    assert got[0] == ref[0] == 0


def test_lucid_breach_models_hand():
    # one day, floor -2000: eod model ignores intraday; realized tests wreal; intraday tests worst
    mk = lambda tot, worst, wreal: dict(tot=tot, worst=worst, wreal=wreal, n=1, pts={"pess": [], "opt": [], "nat": []})
    for model, w, wr, bust in (("eod", -2500, -2500, 0), ("realized", -2500, -1999, 0), ("realized", -2500, -2000, 1),
                               ("intraday", -2000, -1000, 1), ("intraday", -1999, -1999, 0)):
        got, ref, _, _ = both(F.make_spec("flex"), "flex", [mk(100.0, float(w), float(wr))], model=model, H=1)
        assert got[0] == ref[0] == bust, (model, w, wr)


def test_flex_dll_clamps_day_at_minus_1200():
    days = [clean(-1500.0), clean(200.0)]
    spec = F.make_spec("flex", 1200)
    got, ref, f, _ = both(spec, "flex", days, T=None, dll=1200.0)
    assert got[0] == ref[0] == 0
    assert f.log[0][2] == 1200.0                                   # the DLL is passed to the day walk
    # w/o DLL the -1500 day stays -1500 (no bust, floor -2000) and a following -600 busts only with the clamp absent
    days = [clean(-1500.0), clean(-600.0)]
    got_n, ref_n, _, _ = both(F.make_spec("flex"), "flex", days, T=None)
    got_d, ref_d, _, _ = both(spec, "flex", days, T=None, dll=1200.0)
    assert got_n[0] == ref_n[0] == 2 and got_d[0] == ref_d[0] == 0   # -1500-600 = -2100 <= -2000 (bust); with clamp -1200-600 = -1800


# ------------------------------------------------------------------ hand-computed Pro paths

def test_pro_hand_first_payout_buffer_and_cap():
    # 900/day: day 3 profit 2700 cycle max 900 <= 0.4*2700 -> cheque min(2000, 2700-2100) = 600 -> net 540; profit 2100
    days = [clean(900.0) for _ in range(12)]
    got, ref, _, _ = both(F.make_spec("pro", 0), "pro", days)
    # next: cycle profit needs >= 500 and cmax 900 <= 0.4*cp: day 4: cp 900 (max 900 > 360) blocked; day 5: cp 1800, 900 <= 720? no;
    # day 6: cp 2700 -> 900 <= 1080 ok: balance profit 4800 -> cheque min(2500, 4800-2100=2700) = 2500 -> net 2250
    assert pays(got[1])[:2] == [(3, 600.0, 540.0), (6, 2500.0, 2250.0)]
    assert pays(ref[1]) == pays(got[1])


def test_pro_hand_consistency_40pct_boundary():
    # profit 3250 = [1300, 650, 650, 650]: cmax 1300 = 0.4*3250 exactly -> allowed (<=); cheque min(2000, 3250-2100) = 1150
    days = [clean(float(x)) for x in (1300, 650, 650, 650)]
    got, ref, _, _ = both(F.make_spec("pro", 0), "pro", days)
    assert pays(got[1]) == [(4, 1150.0, 1035.0)] == pays(ref[1])
    # 1301 > 0.4*(3251) = 1300.4 -> blocked
    days = [clean(float(x)) for x in (1301, 650, 650, 650)]
    got, ref, _, _ = both(F.make_spec("pro", 0), "pro", days)
    assert pays(got[1]) == [] == pays(ref[1])


def test_pro_hand_min_payout_balance_and_policy_max():
    # profit exactly 2600 -> cheque 500 (balance 52,600); 2599 -> none. spread to satisfy 40%: 5 x 520 = 2600 (max 520 <= 1040)
    for tot, expect in ((520.0, 1), (519.8, 0)):
        days = [clean(tot) for _ in range(5)]
        got, ref, _, _ = both(F.make_spec("pro", 0), "pro", days)
        assert len(got[1]) == len(ref[1]) == expect
    # policy 'max': waits for cheque 2000 -> needs profit 4100: 1000/day -> day 5 (5000, max 1000 <= 2000): cheque min(2000, 2900) = 2000
    days = [clean(1000.0) for _ in range(6)]
    got, ref, _, _ = both(F.make_spec("pro", 0), "pro", days, T="max")
    assert pays(got[1]) == [(5, 2000.0, 1800.0)] == pays(ref[1])
    # day 4 would have allowed 1900 only: confirmed by T=500 paying on day 3 (3000 profit -> 900)
    got, _, _, _ = both(F.make_spec("pro", 0), "pro", days, T=500)
    assert got[1][0][:2] == (3, 900.0)


def test_pro_hand_dll_applies_while_balance_below_52100_literal():
    spec = F.make_spec("pro")
    assert spec.dll_sticky is False
    # profits at each session start: 0, -100, 2200, 2000: the DLL is on at 0 and -100, off at 2200 (>= 2100), back on at 2000 (< 2100)
    days = [clean(-100.0), clean(2300.0), clean(-200.0), clean(10.0)]
    f = FDays(days)
    F.simulate(spec, f, 0, 4, None, "realized")
    assert [d for _, _, d, _ in f.log] == [1200.0, 1200.0, 0.0, 1200.0]
    # exactly 2100 is OFF (balance 52,100 is not below 52,100)
    f = FDays([clean(2100.0), clean(5.0)])
    F.simulate(spec, f, 0, 2, None, "realized")
    assert [d for _, _, d, _ in f.log] == [1200.0, 0.0]
    # the old sticky behaviour is still available and differs on the same path
    f = FDays(days)
    F.simulate(F.make_spec("pro", dll_sticky=True), f, 0, 4, None, "realized")
    assert [d for _, _, d, _ in f.log] == [1200.0, 1200.0, 0.0, 0.0]


def test_pro_dll_off_after_payout_balance_52100_and_on_again_below():
    # 3000 profit via 4 x 750 (max 750 <= 40%): payout day 4 profit 3000 -> cheque 900 -> profit 2100 (balance 52,100: DLL off); a -300 day
    # (profit 1800) then switches the DLL back on
    days = [clean(750.0)] * 4 + [clean(-300.0), clean(5.0)]
    spec = F.make_spec("pro")
    f = FDays(days)
    res = F.simulate(spec, f, 0, 6, 500, "realized")
    assert pays(res[1]) == [(4, 900.0, 810.0)]
    assert [d for _, _, d, _ in f.log] == [1200.0] * 3 + [0.0, 0.0, 1200.0]


# ------------------------------------------------------------------ hand-computed Apex paths

def test_apex_hand_half_size_until_above_2600_eod():
    days = [clean(500.0) for _ in range(9)]
    f = FDays(days)
    F.simulate(F.make_spec("apex"), f, 0, 9, None, "pess")
    # EOD profit 500,1000,1500,2000,2500 (not > 2600), 3000 after day 6 -> day 7 is the first full-size day
    assert f.caps == [50] * 6 + [100] * 3
    days = [clean(2600.0), clean(1.0), clean(1.0)]                # exactly 2600 is NOT above -> still half; 2601 is
    f = FDays(days)
    F.simulate(F.make_spec("apex"), f, 0, 3, None, "pess")
    assert f.caps == [50, 50, 100]


def test_apex_hand_payout_eight_days_five_wins_and_safety_net():
    # eight 325 days = 2600 -> cheque 500 on day 8 (safety net: balance 52,600 -> post 52,100)
    days = [clean(325.0) for _ in range(8)]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [(8, 500.0, 500.0)] == pays(ref[1])
    days = [clean(324.9) for _ in range(8)]                         # 2599.2: cheque 499.2 < 500 -> none
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [] == pays(ref[1])
    # seven days is not enough, even with a huge balance
    days = [clean(1000.0) for _ in range(7)]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [] == pays(ref[1])
    # eight days of which only 4 are >= $50 (the others +49): the 8th day (+600) is the 5th win -> profit 2747, 600 <= 0.3*2747 -> cheque 647
    days = [clean(x) for x in (500.0, 500, 500, 500, 49, 49, 49, 600, 100)]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [(8, 647.0, 647.0)] == pays(ref[1])
    # only 4 wins in 8 days (day 8 = +49): no payout on day 8
    days = [clean(x) for x in (500.0, 500, 500, 500, 49, 49, 49, 49)]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [] == pays(ref[1])


def test_apex_hand_consistency_30pct_boundary():
    # [1000, 300 x7] = 3100: 1000 > 0.3*3100 = 930 -> blocked on day 8; day 9 (+300): 3400 -> 1020 >= 1000 -> payout min(2000, 3400-2100) = 1300
    days = [clean(float(x)) for x in [1000] + [300] * 8]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [(9, 1300.0, 1300.0)] == pays(ref[1])
    # exactly 30%: [900, 300 x 7] = 3000: 900 <= 900 -> allowed on day 8: min(2000, 900) = 900
    days = [clean(float(x)) for x in [900] + [300] * 7]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    assert pays(got[1]) == [(8, 900.0, 900.0)] == pays(ref[1])


def test_apex_hand_six_payouts_caps_net_and_split():
    # +1000/day: payouts every 8 days (cap 2000), the 6th is uncapped and mixes the first-$25k 100% split with the 90% tail
    days = [clean(1000.0) for _ in range(56)]
    got, ref, _, _ = both(F.make_spec("apex"), "apex", days)
    g = [p[1] for p in got[1]]
    assert [p[0] for p in got[1]] == [8, 16, 24, 32, 40, 48, 56][:len(g)]
    assert g[:5] == [2000.0] * 5
    # profit before payout 6 (day 48): 6 x 8000 - 5 x 2000 = 38000 -> cheque 38000 - 200 = 37800 (post balance >= 50,200)
    assert g[5] == 37800.0
    assert got[1][5][2] == pytest.approx(15000.0 + 22800.0 * 0.9)   # 10k already paid at 100% -> 15k more at 100% then 90%
    assert pays(ref[1]) == pays(got[1])


def test_apex_mae_limit_formula_per_day():
    days = [clean(600.0) for _ in range(12)]
    f = FDays(days)
    F.simulate(F.make_spec("apex"), f, 0, 12, None, "pess")
    # start-of-day profit: 0, 600, ... -> lim = max(0.3 * profit, 750); at profit 5400 (day 10): 0.5 -> 2700
    lims = [l for _, _, _, l in f.log]
    prof = [600.0 * k for k in range(12)]
    exp = [max((0.5 if p >= 5200 else 0.3) * p, 750.0) for p in prof]
    assert lims == pytest.approx(exp)


def test_apex_hand_intraday_trailing_peak_includes_open_pnl():
    # trade equity path +2000 then back to -400 then close +100 (net +100): pess: peak 2000 (floor -500), low -400 survives;
    # lock needs peak >= 2600: with a +2700 peak the floor locks at +100 and -400 breaches
    ok = dict(tot=100.0, worst=-400.0, wreal=-400.0, n=1, pts={k: [(1, 2000.0), (0, -400.0), (1, 100.0), (0, 100.0)] for k in ("pess", "opt", "nat")})
    bad = dict(tot=100.0, worst=-400.0, wreal=-400.0, n=1, pts={k: [(1, 2700.0), (0, -400.0), (1, 100.0), (0, 100.0)] for k in ("pess", "opt", "nat")})
    for d, expect in ((ok, 0), (bad, 1)):
        got, ref, _, _ = both(F.make_spec("apex"), "apex", [d], H=1)
        assert got[0] == ref[0] == expect
    # trailing floor with peak 2400: floor -100 ... a low of -100 breaches (<=), -99 survives
    for low, expect in ((-100.0, 1), (-99.0, 0)):
        d = dict(tot=0.0, worst=low, wreal=low, n=1, pts={k: [(1, 2400.0), (0, low), (1, 0.0), (0, 0.0)] for k in ("pess", "opt", "nat")})
        got, ref, _, _ = both(F.make_spec("apex"), "apex", [d], H=1)
        assert got[0] == ref[0] == expect, low


# ------------------------------------------------------------------ fuzz: funded.simulate vs the independent reference

def rand_lucid_days(rng, n, scale=40):
    out = []
    for _ in range(n):
        if rng.random() < 0.25:
            out.append(dict(tot=0.0, worst=0.0, wreal=0.0, n=0, pts={}, scale=scale))
            continue
        tot = rng.gauss(150, 520)
        low = min(tot, 0.0) - abs(rng.gauss(0, 350))
        wr = low + rng.random() * (min(tot, 0.0) - low)
        out.append(dict(tot=tot, worst=low, wreal=wr, n=rng.randint(1, 4), pts={}, scale=scale))
    return out


def rand_apex_days(rng, n):
    out = []
    for _ in range(n):
        if rng.random() < 0.2:
            out.append(dict(tot=0.0, worst=0.0, wreal=0.0, n=0, pts={"pess": [], "opt": [], "nat": []}))
            continue
        pts = {}
        for o in ("pess", "opt", "nat"):
            seq, x = [], 0.0
            for _ in range(rng.randint(1, 4)):
                hi = x + abs(rng.gauss(300, 500))
                lo = x - abs(rng.gauss(300, 450))
                seq += ([(1, hi), (0, lo)] if rng.random() < 0.5 else [(0, lo), (1, hi)])
                x = rng.gauss(x + 80, 400)
            pts[o] = seq + [(1, x), (0, x)]
        # the same final total for every order
        fin = rng.gauss(120, 450)
        for o in pts:
            pts[o][-2], pts[o][-1] = (1, fin), (0, fin)
        out.append(dict(tot=fin, worst=min(0, fin), wreal=min(0, fin), n=rng.randint(1, 3), pts=pts, cut=rng.choice([0, 0, 0, 1])))
    return out


@pytest.mark.parametrize("seed", range(40))
def test_fuzz_lucid_lifecycle_vs_reference(seed):
    rng = random.Random(1000 + seed)
    days = rand_lucid_days(rng, 60 + 20)
    for firm, kind, dll in (("flex", "flex", None), ("flex", "flex", 1200), ("pro", "pro", 1200), ("pro", "pro", 0)):
        spec = F.make_spec(firm, dll)
        for model in E.MODELS:
            for T in (500, 1000, 1500, "max", None):
                f, r = FDays(days), RDays(days)
                got = F.simulate(spec, f, 0, 60, T, model)
                ref = V.ref_life(kind, r, 0, 60, T, model, dll=float(dll or 0.0))
                assert got[0] == ref[0], (firm, dll, model, T, seed)
                assert pays(got[1]) == pays(ref[1]), (firm, dll, model, T, seed)
                if kind == "pro" and dll:                              # legacy sticky option vs the reference's sticky mode
                    f, r = FDays(days), RDays(days)
                    got = F.simulate(F.make_spec("pro", dll, dll_sticky=True), f, 0, 60, T, model)
                    ref = V.ref_life(kind, r, 0, 60, T, model, dll=float(dll), pro_sticky=True)
                    assert got[0] == ref[0] and pays(got[1]) == pays(ref[1]), ("sticky", model, T, seed)


@pytest.mark.parametrize("seed", range(40))
def test_fuzz_apex_lifecycle_vs_reference(seed):
    rng = random.Random(5000 + seed)
    days = rand_apex_days(rng, 60)
    spec = F.make_spec("apex")
    for model in F.ORDERS:
        for T in (500, 1000, "max", None):
            f, r = FDays(days), RDays(days)
            got = F.simulate(spec, f, 0, 60, T, model)
            ref = V.ref_life("apex", r, 0, 60, T, model)
            assert got[0] == ref[0], (model, T, seed)
            assert pays(got[1]) == pays(ref[1]), (model, T, seed)
            assert got[2] == ref[2], "cuts"
            assert [x[:3] for x in f.log] == [x[:3] for x in r.log] and [x[3] for x in f.log] == pytest.approx([x[3] for x in r.log]), \
                "caps / limits requested must match the reference's state tracking"


# ------------------------------------------------------------------ independent day walk vs funded.walk_day

def rand_trades(rng, overlap=True):
    ts, t0 = [], 9 * 60 * 60_000
    for _ in range(rng.choice([0, 1, 1, 2, 3, 4, 5])):
        g = rng.gauss(30, 320)
        mae = max(0.0, -g) + rng.random() * rng.choice([20, 120, 260])
        mfe = max(g, 0.0) + rng.random() * rng.choice([30, 150, 400])
        te = t0 + rng.randint(0, 300) * 60_000
        tx = te + rng.randint(1, 120 if overlap else 1) * 60_000
        ts.append(dict(te=te, tx=tx, side=rng.choice([1, -1]), g=g, mae=mae, mfe=mfe, m=10))
    ts.sort(key=lambda t: (t["te"]))
    return ts


@pytest.mark.parametrize("seed", range(30))
def test_independent_walk_matches_funded_walk_day(seed):
    rng = random.Random(777 + seed)
    for _ in range(60):
        tr = rand_trades(rng)
        rules = dict(max_day_tr=rng.choice([0, 1, 2]), day_stop=rng.choice([0, 300, 700]), day_lock=rng.choice([0, 300, 800]),
                     day_take=rng.choice([0, 250, 600, 1000]))
        micros, cap = rng.choice([20, 30, 40, 50, 100]), rng.choice([20, 40, 50, 100])
        dll = rng.choice([0.0, 1200.0])
        lim = rng.choice([0.0, 0.0, 750.0, 1500.0])
        W = V.RefWalk([tr], micros, rules, E.TICK_USD)
        trs = [(t["te"], t["tx"], t["side"], t["g"], t["mae"], t["m"], np.nan, 0) for t in tr]
        mf = [t["mfe"] for t in tr]
        rl = E.norm_rules(rules)
        got = F.walk_day(trs, mf, cap, rl, micros, dll, rules["day_take"], lim, True)
        for oi, order in ((4, "pess"), (5, "opt"), (7, "nat")):
            ref = W.get(0, cap, dll, lim, order)
            assert got[0] == pytest.approx(ref["tot"]), (seed, rules, order)
            assert got[1] == pytest.approx(ref["worst"])
            assert got[2] == pytest.approx(ref["wreal"])
            assert got[3] == ref["n"] and got[6] == ref["cut"]
            assert len(got[oi]) == len(ref["pts"])
            for (k1, v1), (k2, v2) in zip(got[oi], ref["pts"]):
                assert k1 == k2 and v1 == pytest.approx(v2), (seed, rules, order, got[oi], ref["pts"])


# ------------------------------------------------------------------ hand-computed Apex MAE cut through the real walk + lifecycle

class StubPort:
    def __init__(self, days, mfe):
        self.days, self.mfe = days, mfe


def test_apex_mae_cut_hand_numbers_real_walk():
    # 50 micros (half size): per-NQ mae $200 -> open loss 50*200/10 = $1,000 >= limit $750 (profit 0): cut at -750 - 1 tick (0.5 x 50 = 25) - cost(50) = 20
    #   -> -795.  A second trade with mae $140 -> $700 < $750: not cut, net = 50*(+100)/10 - 20 = +480.
    cut = (1, 10, 1, 100.0, 200.0, 100, float("nan"), 0)
    ok = (20, 30, 1, 100.0, 140.0, 100, float("nan"), 0)
    P = StubPort([[cut], [ok], [cut, ok]], [[100.0], [100.0], [100.0, 100.0]])         # day 2 sorted by entry time; MFE = final P&L (no round trips)
    src = F.DaySrc(P, None, 100, events=True)
    d0 = src.get(0, 50, 0.0, 750.0)
    assert (d0[0], d0[6]) == (-795.0, 1)                             # tot, cut count
    d1 = src.get(1, 50, 0.0, 750.0)
    assert (d1[0], d1[6]) == (480.0, 0)
    # lifecycle: day 1 profit -795 -> lim = max(0.3 x -795, 750) = 750 again; day 2 at profit -315 -> still 750: cut + ok = -795 + 480 = -315 more
    res = F.simulate(F.make_spec("apex"), src, 0, 3, None, "pess")
    assert res[0] == 0 and res[2] == 2                                # no bust, two cuts (day 0 and the cut trade of day 2)
    # independent walk agrees
    W = V.RefWalk([[dict(te=t[0], tx=t[1], side=1, g=t[3], mae=t[4], mfe=400.0, m=100)] for t in (cut,)], 100, {}, 0.5)
    r = W.get(0, 50, 0.0, 750.0, "pess")
    assert (r["tot"], r["cut"]) == (-795.0, 1)


def test_apex_mae_cut_threshold_is_30pct_of_start_of_day_profit():
    # at start-of-day profit 5000 the limit is 1,500 (30%): a $1,000 open loss is allowed; at profit 5200+ it is 50% (2,600)
    src = Days([clean(5000.0 / 8) for _ in range(8)] + [clean(10.0) for _ in range(3)])
    f = FDays(src.days)
    F.simulate(F.make_spec("apex"), f, 0, 11, None, "pess")
    lims = [l for _, _, _, l in f.log]
    assert lims[0] == 750.0 and lims[8] == pytest.approx(1500.0)       # day 8 starts at profit 5000 -> 0.3 x 5000
    f2 = FDays([clean(5200.0)] + [clean(1.0)] * 2)
    F.simulate(F.make_spec("apex"), f2, 0, 3, None, "pess")
    assert [l for _, _, _, l in f2.log][1] == pytest.approx(0.5 * 5200.0)   # 50% once start-of-day profit >= 2 x 2,600
