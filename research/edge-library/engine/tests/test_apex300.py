"""Tests for apex300.py (Apex Legacy 300K PA lifecycle + compliance gate). Hand-worked scenarios for every rule + parity with
R/funded.py.

Run: "~/ONYX TRADING/.venv/bin/python" -m pytest tests/test_apex300.py   (from L; or /usr/bin/python3 -m pytest)
Conventions (R): n micros, P&L = n x gross/10 - cost(n), 1 tick = $0.50 per micro. cost(n): R / Lucid (n // 10) x $4 + (n % 10) x $1
(spec SR = commission 'R', used for the hand-worked walks); Apex default (n // 10) x $3.98 + (n % 10) x $1.04.
All $ below are PROFIT = balance - 300,000. Fresh 300K PA: floor -7,500, lock at peak >= +7,600 -> floor +100, half size
170 micros (17 minis) until EOD profit > 7,600, MAE limit max(30% x start-of-day profit, 2,250), cheque (payouts 1-3) =
min(3,500, profit - 7,100). Defaults are the CONSERVATIVE readings (consistency on the profit since the last payout, payouts 4+
keep the minimum balance); `A.r_compat()` = R's readings.
"""
import datetime as dt
import json
import random
import sys
from pathlib import Path

import pytest

L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import apex300 as A                                              # noqa: E402

E, F = A.E, A.F
S300 = A.make_spec()                                             # conservative defaults, Apex commissions
SR = A.make_spec(commission="R")                                 # same rules on R's cost model: the hand-worked walks below
S300R = A.make_spec(**A.r_compat())                              # R's readings (bit-identical to R's loop)
S50R = A.make_spec("apex50_pa", **A.r_compat("apex50_pa"))


# ---------------------------------------------------------------- helpers

def day(tot, low=None, high=None, ntr=1, cuts=0):
    """Prescribed day result (funded.walk_day tuple): equity path relative to the day's start. pess = high first, opt = low first.
    Defaults = a clean day (equity goes straight from 0 to tot), as R/test_funded.Fake."""
    low = tot if low is None else low
    high = max(tot, 0.0) if high is None else high
    pess = ((1, high), (0, low), (1, tot), (0, tot))
    opt = ((0, low), (1, high), (1, tot), (0, tot))
    return (tot, min(low, tot), min(low, tot), ntr if (tot or low or high) else 0, pess, opt, cuts, pess if tot < 0 else opt)


class Fake:
    """Day source with prescribed results (floats = clean days, 0 = no trade; or day(...) tuples). Logs every request."""

    def __init__(self, days):
        self.days = [d if isinstance(d, tuple) else day(float(d)) for d in days]
        self.n_days = len(self.days)
        self.log = []

    def get(self, i, cap, dll=0.0, lim=0.0):
        self.log.append((i, cap, dll, lim))
        return self.days[i]

    @property
    def caps(self):
        return [c for _, c, _, _ in self.log]

    @property
    def lims(self):
        return [l for _, _, _, l in self.log]


def run(days, T=500, model=None, start="fresh", S=S300):
    src = Fake(days)
    return A.simulate(S, src, 0, len(days), T, model, start), src


def pays(days, T=500, **kw):
    return run(days, T, **kw)[0][1]


def weekdays(n, start=dt.date(2023, 3, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(1)
    return out


def tr(date, hhmm, gross, mae=0.0, mfe=None, side="long", dur=5, sl=None, qty=1, tp=None, **extra):
    """Trade dict in the R trades.json schema: gross / mae / mfe are per 1 NQ here and multiplied by the run qty (evalcore
    normalises back to 1 NQ). Self-consistent (gross = side x (exit - entry) x $20 x qty, net = gross - commission), so the rows
    also pass score.py's strict loader when that module is loaded in the same process."""
    h, m = map(int, hhmm.split(":"))
    ms = int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time(h, m), E.ET).timestamp() * 1000)
    sgn = 1.0 if side == "long" else -1.0
    mfe = max(gross, 0.0) if mfe is None else mfe
    return {"date": date, "side": side, "qty": qty, "entry_price": 15000.0, "exit_price": 15000.0 + sgn * gross / 20.0,
            "exit_reason": "tp" if gross > 0 else "sl", "gross": gross * qty, "commission": 4.0 * qty, "net": gross * qty - 4.0 * qty,
            "mae_usd": mae * qty, "mfe_usd": mfe * qty, "mae_pts": mae / 20.0, "mfe_pts": mfe / 20.0,
            "entry_ms": ms, "exit_ms": ms + dur * 60000, "sl": sl, "tp": tp, "order_price": None, **extra}   # order_price None = a market entry


def clean_trades(seed, ndays=110, scale=1.0, stop=30.0, target=20.0):
    """Compliant-looking ledger: at most two trades a day (10:00 and 13:00, <= 60 min: never overlapping), either side, every
    trade with a stop `stop` pts and a target `target` pts from the entry."""
    rng = random.Random(seed)
    cal = weekdays(ndays)
    ts = []
    for d in cal:
        for hh in ("10:00", "13:00")[:rng.choice([0, 1, 1, 2])]:
            g = rng.gauss(40, 350) * scale
            side = rng.choice(["long", "short"])
            sg = 1.0 if side == "long" else -1.0
            ts.append(tr(d, hh, g, mae=max(0.0, -g) + rng.random() * 250 * scale, mfe=max(g, 0.0) + rng.random() * 300 * scale,
                         side=side, dur=rng.randint(1, 60), sl=15000.0 - sg * stop, tp=15000.0 + sg * target))
    return ts, cal


def port(trades, cal, micros=10):
    return A.port_from_trades(trades, micros=micros, calendar=cal, start=cal[0], end=cal[-1])


def rand_trades(seed, ndays=130, scale=1.0, qty2_every=0):
    rng = random.Random(seed)
    cal = weekdays(ndays)
    ts = []
    for d in cal:
        for _ in range(rng.choice([0, 1, 1, 2, 3])):
            g = rng.gauss(40, 350) * scale
            ts.append(tr(d, f"{rng.randint(9, 14):02d}:{rng.randint(0, 59):02d}", g, mae=max(0.0, -g) + rng.random() * 250 * scale,
                         mfe=max(g, 0.0) + rng.random() * 300 * scale, side=rng.choice(["long", "short"]), dur=rng.randint(1, 120),
                         qty=2 if qty2_every and len(ts) % qty2_every == 0 else 1))
    return ts, cal


D1 = weekdays(1)[0]
CAL3 = weekdays(3)


# ---------------------------------------------------------------- spec (values: APEX300_RULES.md)

def test_spec_values_300k():
    S = S300
    assert (S.name, S.kind, S.primary) == ("apex300_pa", "apex", "pess")
    assert (S.mll, S.lock_at, S.lock_floor) == (7500.0, 7600.0, 100.0)
    assert (S.cap, S.half, S.unlock, S.sticky_full) == (350, 170, 7600.0, True)             # half = 17 minis (conservative)
    assert (S.mae_pct, S.mae_min, S.mae_pct_hi, S.mae_hi_at) == (0.30, 2250.0, 0.50, 15200.0)
    assert S.mae_min == S.mae_pct * S.mll and S.mae_hi_at == 2 * S.lock_at
    assert (S.min_days, S.win_days, S.win_day, S.cons, S.cons_until) == (8, 5, 50.0, 0.30, 5)
    assert (S.min_pay, S.pay_cap, S.cap_pays, S.net_pays) == (500.0, 3500.0, 5, 3)
    assert S.net_pay == S.lock_at - S.min_pay == 7100.0                     # $307,600 to request the $500 minimum
    assert (S.split_full, S.split_after, S.split_until) == (1.0, 0.9, 25000.0)
    assert S.dll == 0.0                                                     # no daily loss limit
    assert A.make_spec(micros_allowed=False).half == 170                    # 17 minis
    assert A.make_spec(**A.VARIANTS["half_175"](S)).half == 175             # the 17.5-mini reading is a variant
    # conservative defaults of the unconfirmed rules: consistency on the profit since the last payout; payouts 4+ keep the minimum
    assert (S.cons_base, S.post_req_min, S.post_net_min, S.post_cap_net) == ("cycle", 7600.0, 7600.0, 7600.0)
    assert (S.commission, S.comm_nq, S.comm_mnq) == ("apex", 3.98, 1.04)
    assert A.GRID["micros"][-1] == S.half == 170
    assert A.make_spec("flex").kind == "flex"                               # other firms: R's specs
    assert A.floor_of(S, 0.0) == -7500.0 and A.floor_of(S, 7599.0) == 99.0 and A.floor_of(S, 7600.0) == 100.0
    assert [A.mae_limit(S, p) for p in (-500.0, 0.0, 7500.0, 7600.0, 10000.0, 15199.0, 15200.0)] == \
        [2250.0, 2250.0, 2250.0, 0.3 * 7600.0, 3000.0, 0.3 * 15199.0, 7600.0]


def test_spec_50k_equals_R_apex():
    r = F.make_spec("apex").__dict__
    mine = S50R.__dict__                                                    # R's readings: R's `apex` spec, value for value
    assert all(mine[k] == v for k, v in r.items() if k != "name")
    assert mine["post_req_min"] == 0.0 and mine["post_cap_net"] == r["post_net_min"] and mine["comm_nq"] is None
    d = A.make_spec("apex50_pa")                                            # default: the same conservative readings as the 300K
    assert (d.cons_base, d.post_req_min, d.post_net_min, d.post_cap_net, d.half, d.commission) == ("cycle", 2600.0, 2600.0, 2600.0, 50, "apex")
    rc = A.r_compat()
    assert (S300R.cons_base, S300R.half, S300R.post_net_min, S300R.commission) == ("balance", 175, 200.0, "R") and rc["half"] == 175


def test_make_spec_rejects_unknown_overrides():
    with pytest.raises(ValueError, match="unknown spec override.*consistency"):
        A.make_spec(consistency=0.5)                                        # the key is `cons`
    with pytest.raises(ValueError, match="unknown commission"):
        A.make_spec(commission="ninjatrader")
    with pytest.raises(ValueError, match="cons_base"):
        A.make_spec(cons_base="total")
    with pytest.raises(ValueError):
        A.evaluate_funded(port([tr(D1, "10:00", 10.0)], weekdays(70)), micros=10, consitency=0.3)
    assert A.make_spec(cons=0.5).cons == 0.5 and A.make_spec(comm_nq=5.0, comm_mnq=1.5).commission == "custom"


# ---------------------------------------------------------------- 1. breach on OPEN equity (intraday trailing, uses MAE / MFE)

def test_breach_on_open_loss_fake_days():
    assert run([-7499.0], None)[0][0] == 0                                  # -7,499 > -7,500
    assert run([-7500.0], None)[0][0] == 1                                  # touches the threshold
    # day 1 +5,000 (peak 5,000 -> floor -2,500). Day 2 dips to -7,600 open (equity -2,600) and closes +200: bust on the open loss
    for m in A.ORDERS:
        assert run([5000.0, day(200.0, low=-7600.0)], None, m)[0][0] == 2
        assert run([5000.0, day(-100.0, low=-7500.0)], None, m)[0][0] == 2  # equity -2,500 touches the floor
        assert run([5000.0, day(-100.0, low=-7499.0)], None, m)[0][0] == 0  # equity -2,499 > -2,500
    # a green close does not help in the pessimistic order either: the day's +200 high lifts the floor to -2,300 first
    assert run([5000.0, day(200.0, low=-7350.0)], None, "pess")[0][0] == 2  # -2,350 <= -2,300
    assert run([5000.0, day(200.0, low=-7350.0)], None, "opt")[0][0] == 0   # low first: -2,350 > -2,500


def test_breach_on_open_loss_real_walk_trailing_peak():
    # 100 micros (10 NQ), cost 40. Per NQ: gross +100, MFE 600, MAE 200 -> exit +960, best +5,960, worst -2,040 (open loss 2,000 < 2,250: no cut)
    P = port([tr(D1, "10:00", 100.0, mae=200.0, mfe=600.0)], CAL3)
    src = F.DaySrc(P, None, 100, events=True)
    o = src.get(0, 175, 0.0, 2250.0)
    assert o[0] == 960.0 and o[6] == 0
    assert o[4] == ((1, 5960.0), (0, -2040.0), (1, 960.0), (0, 960.0))      # pess: MFE first -> floor 5,960 - 7,500 = -1,540 >= -2,040
    assert o[5] == ((0, -2040.0), (1, 5960.0), (1, 960.0), (0, 960.0))      # opt: MAE first (floor -7,500), then the peak
    assert [A.simulate(SR, src, 0, 3, None, m)[0] for m in ("pess", "opt", "nat")] == [1, 0, 0]
    assert S300.primary == "pess"


def test_breach_on_open_loss_real_walk_without_and_with_mae_cut():
    # 100 micros, MAE 760 / NQ: open loss 7,600 (+40 commission) <= -7,500 although the trade closes +960
    P = port([tr(D1, "10:00", 100.0, mae=760.0, mfe=100.0)], CAL3)
    nocut = A.make_spec(mae_min=1e9, commission="R")
    src = F.DaySrc(P, None, 100, events=True)
    assert [A.simulate(nocut, src, 0, 3, None, m)[0] for m in A.ORDERS] == [1, 1, 1]
    # with the MAE rule the desk cuts at -2,250 (-$50 slippage, -$40 commission): no breach, 1 cut counted, day = -2,340
    r = A.simulate(SR, src, 0, 3, None)
    assert r == (0, [], 1, 1)
    assert src.get(0, 175, 0.0, 2250.0)[0] == -2340.0


# ---------------------------------------------------------------- 2. threshold lock at +7,600 -> +100

def test_trailing_floor_locks_at_safety_net():
    assert run([8000.0, -7800.0], None)[0][0] == 0                          # locked floor +100: profit 200 alive
    assert run([8000.0, -7800.0, -100.0], None)[0][0] == 3                  # 100 <= 100
    assert run([7000.0, -7400.0], None)[0][0] == 0                          # not locked: floor -500, profit -400
    assert run([7000.0, -7500.0], None)[0][0] == 2                          # -500 <= -500
    # an UNREALISED peak of 7,600 locks it: pess (high first) busts on the dip to 0 the same day; opt survives and stays locked
    d = day(1000.0, low=0.0, high=7600.0)
    assert run([d, -900.0], None, "pess")[0][0] == 1
    assert run([d, -899.0], None, "opt")[0][0] == 0                         # 101 > 100
    assert run([d, -900.0], None, "opt")[0][0] == 2                         # 100 <= 100: the lock came from the intraday peak
    # sensitivity trail='eod' (account holder's reading): peak = closes only -> floor 1,000 - 7,500
    eod = A.make_spec(trail="eod")
    assert run([d, -900.0], None, "pess", S=eod)[0][0] == 0
    assert run([d, -8500.0], None, "pess", S=eod)[0][0] == 2                # 1,000 - 8,500 = -7,500 <= -6,500
    # a payout keeps the lock
    r, _ = run([1000.0] * 8 + [-6900.0, -100.0], 500)
    assert r[1] == [(8, 900.0, 900.0)] and r[0] == 10                       # 7,100 - 6,900 = 200 alive; 100 <= 100 bust


# ---------------------------------------------------------------- 3. half size until the safety net

def test_half_size_until_eod_profit_above_7600():
    _, src = run([3800.0, 3800.0, 1.0, 1.0, -5000.0, 1.0], None)
    assert src.caps == [170, 170, 170, 350, 350, 350]                       # 7,600 is not above 7,600; 7,601 is; sticky afterwards
    _, src = run([3800.0, 3800.0, 1.0, 1.0, -5000.0, 1.0], None, S=A.make_spec(sticky_full=False))
    assert src.caps == [170, 170, 170, 350, 350, 170]
    _, src = run([3800.0, 3800.0, 1.0, 1.0], None, S=A.make_spec(**A.VARIANTS["half_175"](S300)))
    assert src.caps == [175, 175, 175, 350]


def test_half_size_switch_real_walk():
    # a 300-micro config is executed at 170 while in the half phase: 170 x 10 / 10 - cost(170) = 170 - 68 = 102; full: 300 - 120 = 180
    cal = weekdays(3)
    P = port([tr(cal[0], "10:00", 10.0), tr(cal[1], "10:00", 10.0), tr(cal[2], "10:00", 10.0)], cal)
    src = F.DaySrc(P, None, 300, events=True)
    assert src.get(0, 170, 0.0, 0.0)[0] == 102.0 and src.get(0, 350, 0.0, 0.0)[0] == 180.0
    src = F.DaySrc(P, None, 300, events=True)
    A.simulate(SR, src, 0, 3, None, start=A.Start(7500.0))                 # 7,500 -> 7,602 (> 7,600) -> full from day 2
    assert sorted(k[:2] for k in src.memo) == [(0, 170), (1, 350), (2, 350)]


# ---------------------------------------------------------------- 4. MAE (30% negative P&L) rule

def test_mae_limit_passed_to_the_walk():
    _, src = run([1000.0, 7000.0, 5000.0, 3000.0, 100.0], None)             # start-of-day profit 0, 1000, 8000, 13000, 16000
    assert src.lims == [2250.0, 2250.0, 2400.0, 3900.0, 8000.0]             # 30% x max(profit, 7,500); 50% from 15,200
    _, src = run([100.0], None, start="plus7600")
    assert src.lims == [0.3 * 7600.0]


def test_mae_cut_real_walk_and_counts():
    # 30 micros: open loss 30 x 800 / 10 = 2,400 >= 2,250 -> cut at -2,250 - 30 x 0.50 - cost(30) = -2,277 (the trade would have made +888)
    P = port([tr(D1, "10:00", 300.0, mae=800.0, mfe=400.0)], CAL3)
    src = F.DaySrc(P, None, 30, events=True)
    o = src.get(0, 175, 0.0, 2250.0)
    assert o[0] == -2277.0 and o[6] == 1 and o[3] == 1
    assert src.get(0, 175, 0.0, 2400.0)[0] == -2427.0                       # MAE exactly at the limit is cut
    o = src.get(0, 175, 0.0, 2401.0)
    assert o[0] == 888.0 and o[6] == 0                                      # below the limit: untouched
    assert A.simulate(SR, src, 0, 3, None) == (0, [], 1, 1)                 # fresh: limit 2,250 -> 1 cut, account alive
    assert A.simulate(SR, src, 0, 3, None, start=A.Start(8010.0)) == (0, [], 0, 1)     # limit 2,403 > 2,400: no cut
    # a config that relies on the cut is non-compliant on the MAE criterion (the other two are proven here: one direction
    # declared, stop 30 pts <= 5 x target 20 pts on the row)
    P = port([tr(D1, "10:00", 300.0, mae=800.0, mfe=400.0, sl=14970.0, tp=15020.0)], CAL3)
    out = A.evaluate_funded(P, micros=30, policy=None, H=3, both_sides=False)
    assert out["pess"]["cut_share"] == 1.0 and out["noncompliant"] is True
    assert out["compliance"] == {"one_direction": "ok", "stop_5x_target": "ok", "mae_rule": "FAIL"}
    assert "mae30_cuts_1.000_NONCOMPLIANT" in out["flags"]
    assert out["mae_limit_at_start"] == 2250.0 and out["mae_over_limit_share"] == 1.0
    out = A.evaluate_funded(P, micros=20, policy=None, H=3, both_sides=False)           # 20 micros: open loss 1,600 < 2,250
    assert out["pess"]["cut_share"] == 0.0 and out["noncompliant"] is False and out["mae_over_limit_share"] == 0.0
    assert out["flags"] == [] and set(out["compliance"].values()) == {"ok"}


# ---------------------------------------------------------------- 5. payout eligibility and timing

def test_payout_needs_8_traded_days_5_win_days_and_307600():
    assert pays([950.0] * 8) == [(8, 500.0, 500.0)]                         # 7,600 on day 8 -> the $500 minimum
    assert pays([950.0] * 7 + [949.0]) == []                                # 7,599: below the minimum balance
    assert pays([1100.0] * 7) == []                                         # 7,700 but only 7 trading days
    assert pays([1100.0] * 8) == [(8, 1700.0, 1700.0)]                      # 8,800 - 7,100
    assert [p[0] for p in pays([1000.0, 0, 1000.0, 0] + [1000.0] * 6)] == [10]          # no-trade weekdays are not trading days
    assert pays([1900.0] * 4 + [10.0] * 4) == []                            # 8 days, 7,640, but only 4 days >= $50
    assert pays([1900.0] * 4 + [10.0] * 4 + [49.0]) == []
    assert pays([1900.0] * 4 + [10.0] * 4 + [60.0]) == [(9, 600.0, 600.0)]  # 5th day >= $50; 7,700 - 7,100
    assert pays([1400.0] * 8) == [(8, 3500.0, 3500.0)]                      # cap $3,500 (4,100 available); 100% split


def test_payout_cycles_payouts_4plus_conservative_default_and_variants():
    free = A.make_spec(**A.VARIANTS["pay4_free"](S300))                      # R's optimistic reading: no minimum after payout 3
    req = A.make_spec(**A.VARIANTS["pay4_req_only"](S300))                   # request needs 307,600; payouts 4-5 may leave +200
    assert (free.post_req_min, free.post_net_min, free.post_cap_net) == (0.0, 200.0, 200.0)
    assert (req.post_req_min, req.post_net_min, req.post_cap_net) == (7600.0, 200.0, 7600.0)
    # payouts 1-3 at the minimum (profit back to 7,100 each time), then 8 x +90 -> 7,820.
    days = [950.0] * 8 + [62.5] * 16 + [90.0] * 8
    first3 = [(8, 500.0, 500.0), (16, 500.0, 500.0), (24, 500.0, 500.0)]
    # DEFAULT (conservative): from the 4th payout the minimum required balance (307,600) must REMAIN: 7,820 - 7,600 = 220 is
    # below the $500 minimum -> no payout yet
    assert pays(days) == first3
    # optimistic readings: no safety net -> min(3,500, 7,820 - 200) = 3,500, leaving the account $4,320 over the start
    assert pays(days, S=free) == first3 + [(32, 3500.0, 3500.0)]
    assert pays(days, S=req) == first3 + [(32, 3500.0, 3500.0)]              # 7,820 >= 7,600: may request
    # 8 x +150 instead -> 8,300: the default pays 8,300 - 7,600 = 700 and leaves exactly 307,600
    days = [950.0] * 8 + [62.5] * 16 + [150.0] * 8
    assert pays(days) == first3 + [(32, 700.0, 700.0)] and pays(days, S=req) == first3 + [(32, 3500.0, 3500.0)]
    # losing 4th cycle (profit 6,450 < 7,600, cycle profit -650): the default and 'pay4_req_only' pay nothing; 'pay4_free' is
    # blocked by the consistency rule under the 'cycle' reading (no profit since the last payout) and pays 3,500 (leaving
    # 2,950) only under R's readings (balance base: 50 <= 30% x 6,450)
    days = [950.0] * 8 + [62.5] * 16 + [-1000.0] + [50.0] * 7
    assert pays(days) == first3 and pays(days, S=req) == first3 and pays(days, S=free) == first3
    assert pays(days, S=S300R)[3] == (32, 3500.0, 3500.0)
    # an account that already took 3 payouts and sits at +300 (threshold locked at +100): default pays nothing; 'pay4_free'
    # pays 500 at balance 300,700 and leaves the account $100 above the liquidation level (the verifier's example)
    st = A.Start(300.0, peak=8000.0, pays=3)
    assert pays([50.0] * 8, start=st) == [] and pays([50.0] * 8, start=st, S=free) == [(8, 500.0, 500.0)]
    # 6th payout: no cap, no consistency check. Default / 'pay4_req_only' leave 307,600; 'pay4_free' leaves 300,200.
    # Split: 100% of the first 25k gross (17,500 already paid), then 90%
    st = A.Start(20000.0, pays=5, paid_gross=17500.0)
    assert pays([100.0] * 8, start=st) == [(8, 13200.0, 7500.0 + 5700.0 * 0.9)]
    assert pays([100.0] * 8, start=st, S=req) == [(8, 13200.0, 7500.0 + 5700.0 * 0.9)]
    assert pays([100.0] * 8, start=st, S=free) == [(8, 20600.0, 7500.0 + 13100.0 * 0.9)]
    big = day(9000.0)                                                        # a 9,000 day > 30% of the cycle profit: irrelevant from the 6th payout
    assert len(pays([big] + [100.0] * 7, start=st)) == 1
    # 5th payout: 9,000 > 30% x 9,700 (cycle profit, default) and > 30% x 29,700 (balance reading) -> blocked under both
    assert pays([big] + [100.0] * 7, start=A.Start(20000.0, pays=4)) == []
    assert pays([big] + [100.0] * 7, start=A.Start(20000.0, pays=4), S=A.make_spec(cons_base="balance")) == []


def test_split_100pct_of_first_25k_then_90():
    S = A.make_spec(split_until=1000.0)
    assert pays([1100.0] * 8, S=S) == [(8, 1700.0, 1000.0 + 700.0 * 0.9)]
    # five capped payouts (17,500 gross, 100%): profit 11,200 -> 7,700 -> (+4,000) 11,700 -> 8,200 -> 8,700 -> 9,200 -> 9,700
    days = [1400.0] * 8 + [500.0] * 56
    five = [(8, 3500.0, 3500.0), (16, 3500.0, 3500.0), (24, 3500.0, 3500.0), (32, 3500.0, 3500.0), (40, 3500.0, 3500.0)]
    # DEFAULT: the uncapped 6th leaves 307,600: 13,700 - 7,600 = 6,100 (all inside the 25k band: 23,600 paid); then 4,000 per
    # cycle: 1,400 at 100% + 2,600 at 90% = 3,740, then 90% = 3,600
    p = pays(days)
    assert p[:5] == five
    assert p[5:] == [(48, 6100.0, 6100.0), (56, 4000.0, 1400.0 + 2600.0 * 0.9), (64, 4000.0, 3600.0)]
    # 'pay4_free' (R): the uncapped 6th takes 13,500 (7,500 at 100% + 6,000 at 90%) and leaves $200, then 90%
    p = pays(days, S=A.make_spec(**A.VARIANTS["pay4_free"](S300)))
    assert p[:5] == five
    assert p[5:] == [(48, 13500.0, 7500.0 + 6000.0 * 0.9), (56, 4000.0, 3600.0), (64, 4000.0, 3600.0)]


# ---------------------------------------------------------------- 6. 30% consistency

def test_consistency_30pct_blocks_then_allows():
    # 3,000 + 7 x 700 = 7,900 on day 8: 3,000 > 30% x 7,900 = 2,370 -> blocked; needs 3,000 / 0.3 = 10,000 -> day 11; cheque 10,000 - 7,100
    bal = A.make_spec(cons_base="balance")                                   # the optimistic reading (worked example on the Apex pages)
    assert S300.cons_base == "cycle"                                         # selection default: profit since the last payout
    assert pays([3000.0] + [700.0] * 10) == [(11, 2900.0, 2900.0)]
    assert pays([3000.0] + [700.0] * 9) == []
    assert pays([3000.0] + [700.0] * 10, S=bal) == [(11, 2900.0, 2900.0)]   # same in the first cycle of a fresh account
    # with a +7,600 cushion the two readings differ: 'balance' base 15,500 -> allowed day 8; 'cycle' base 7,900 -> blocked until
    # the cycle profit reaches 10,000 on day 11
    assert pays([3000.0] + [700.0] * 10, start="plus7600") == [(11, 3500.0, 3500.0)]
    assert pays([3000.0] + [700.0] * 10, start="plus7600", S=bal) == [(8, 3500.0, 3500.0)]
    # a cushion earned in the CURRENT cycle counts in the 'cycle' base (Start cpnl) and its 3 traded days count too: the 8th
    # traded day is day 5 (profit 13,400, all of it cycle profit: 3,000 <= 30% x 13,400) -> cheque min(3,500, 13,400 - 7,100)
    st = A.Start(7600.0, cd=3, cw=3, cmax=2000.0, cpnl=7600.0)
    assert pays([3000.0] + [700.0] * 10, start=st) == [(5, 3500.0, 3500.0)]
    assert A.other_cons(S300).cons_base == "balance" and A.other_cons(bal).cons_base == "cycle"


# ---------------------------------------------------------------- 7. request policy (search dimension)

def test_policy_request_at_min_vs_wait():
    days = [1000.0] * 12
    got = {T: pays(days, T)[:1] for T in (500, 1500, 2500, "max", None)}
    assert got[500] == [(8, 900.0, 900.0)]                                  # 8,000 - 7,100
    assert got[1500] == [(9, 1900.0, 1900.0)]
    assert got[2500] == [(10, 2900.0, 2900.0)]
    assert got["max"] == [(11, 3500.0, 3500.0)]                             # 11,000: 3,900 available, capped
    assert got[None] == []
    assert A.POLICIES["apex300_pa"] == (500, 1500, 2500, "max")


# ---------------------------------------------------------------- 8. start states

def test_start_states():
    assert A.as_start("fresh") == A.Start() and A.as_start(3000) == A.STARTS["plus3000"] and A.start_name(7600.0) == "plus7600"
    # +3,000: trailing floor 3,000 - 7,500 = -4,500, half size, MAE limit 2,250
    r, src = run([-7499.0], None, start="plus3000")
    assert r[0] == 0 and src.caps == [170] and src.lims == [2250.0]
    assert run([-7500.0], None, start="plus3000")[0][0] == 1
    assert run([-4501.0], None, start=A.Start(3000.0, peak=6000.0))[0][0] == 1          # a higher past peak: floor -1,500
    # +7,600: threshold LOCKED at +100, still half size until an EOD above 7,600, MAE limit 30% x 7,600
    r, src = run([-7499.0, 1.0], None, start="plus7600")
    assert r[0] == 0 and src.lims[0] == 0.3 * 7600.0
    assert run([-7500.0], None, start="plus7600")[0][0] == 1
    _, src = run([1.0, 1.0], None, start="plus7600")
    assert src.caps == [170, 350]
    _, src = run([1.0, 1.0], None, start=A.Start(7600.0, full=True, peak=7700.0))      # closed above 307,600 before, fell back
    assert src.caps == [350, 350]
    # the payout clock starts at day 0: 8 x +100 -> 8,400 -> cheque 1,300 on day 8
    assert pays([100.0] * 8, start="plus7600") == [(8, 1300.0, 1300.0)]
    assert pays([100.0] * 8, start="plus3000") == []                        # 3,800: far below 7,600
    with pytest.raises(ValueError):
        A.simulate(F.make_spec("flex"), Fake([1.0]), 0, 1, None, None, "plus3000")
    with pytest.raises(ValueError):
        run([1.0], None, "eod")


# ---------------------------------------------------------------- parity with R/funded.py

def test_fresh_start_is_bit_identical_to_R_loop():
    n = busts = npays = 0
    for seed in range(4):
        for S, apex, scale, mi in ((S50R, F.make_spec("apex"), 1.0, 50), (S300R, S300R, 2.5, 100)):
            ts, cal = rand_trades(seed, ndays=140, scale=scale)
            P = port(ts, cal)
            for rules in (None, {"day_take": 400 * scale, "max_day_tr": 2}):
                src = F.DaySrc(P, rules, mi, events=True)
                for order in A.ORDERS:
                    for T in (500, 1000, "max", None):
                        ref = F.lifecycle(apex, src, T, 60, order)
                        got = A.lifecycle(S, src, T, 60, order, "fresh")
                        assert got == ref, (seed, S.name, rules, order, T)
                        n += len(ref)
                        busts += sum(r[0] > 0 for r in ref)
                        npays += sum(len(r[1]) for r in ref)
    assert n > 5000 and busts > 200 and npays > 200                         # not a degenerate comparison


def test_R_search_on_the_300k_spec_equals_this_search():
    # with R's readings (r_compat) R's funded.search on the spec gives the same rows as apex300.search from a fresh start
    ts, cal = rand_trades(8, ndays=120, scale=2.0)
    P = port(ts, cal)
    g = {"micros": [20, 60], "day_take": [0, 1500], "day_lock": [0], "day_stop": [0], "max_day_tr": [0, 1], "policy": [500, "max"]}
    ref = F.search(P, S300R, g)
    got = A.search(P, S300R, grid=g)
    assert len(ref) == len(got) == 16
    keys = ("micros", "day_take", "max_day_tr", "policy", "p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_net_40",
            "e_net_60", "p_bust_pre_first", "p_bust_any", "e_npay_60", "cut_share", "stab_e_net_40", "score_p_pay_20")
    assert [[r[k] for k in keys] for r in ref] == [[r[k] for k in keys] for r in got]
    assert any(r["p_pay_60"] > 0 for r in got) and any(r["p_bust_any"] > 0 for r in got)


def test_evaluate_matches_R_evaluate_funded_for_50k():
    ts, cal = rand_trades(11, ndays=140)
    P = port(ts, cal)
    ref = F.evaluate_funded(P, "apex", micros=30, rules={"day_take": 400}, policy=500)
    got = A.evaluate_funded(P, "apex50_pa", micros=30, rules={"day_take": 400}, policy=500, **A.r_compat("apex50_pa"))
    for m in A.ORDERS:
        assert got[m] == ref[m]
    assert got["cons_base"] == "balance" and got["cons_alt"]["cons_base"] == "cycle"
    assert A.evaluate_funded(P, "apex", micros=30, policy=500)["pess"] == F.evaluate_funded(P, "apex", micros=30, policy=500)["pess"]
    assert "realized" in A.evaluate_funded(P, "flex", micros=20, policy=500)            # other firms are delegated to R


# ---------------------------------------------------------------- trades in, metrics out; sizing; holdout seal

def test_trade_list_to_metrics_smoke():
    ts, cal = rand_trades(5, ndays=150, scale=2.0, qty2_every=3)          # every 3rd row at qty 2: normalised to 1 NQ
    P = port(ts, cal)
    P1 = port(rand_trades(5, ndays=150, scale=2.0)[0], cal)
    assert [[(round(x[3], 6), round(x[4], 6)) for x in d] for d in P.days] == [[(round(x[3], 6), round(x[4], 6)) for x in d] for d in P1.days]
    out = A.evaluate_funded(P, micros=30, rules={"day_take": 1500}, policy=500, strategy="bimb_follow", inputs={"tgt_r": 1.5})
    for m in A.ORDERS:
        x = out[m]
        assert x["n"] == 150 - 60 + 1 and 0 <= x["p_pay_20"] <= x["p_pay_40"] <= x["p_pay_60"] <= 1
        assert x["p_bust_pre_first"] <= x["p_bust_any"] + 1e-12
        for k in ("med_days_first", "e_first_gross", "e_first_net", "e_net_40", "e_net_60", "e_npay_60", "cut_share"):
            assert k in x
    assert out["opt"]["p_bust_any"] <= out["pess"]["p_bust_any"] + 1e-12    # the optimistic order never busts more
    assert out["primary"] == "pess" and out["start"] == "fresh" and out["micros"] == 30
    # both consistency readings are always reported: the selection default ('cycle') and the other one
    assert out["cons_base"] == "cycle" and out["cons_alt"]["cons_base"] == "balance" and out["commission"] == "apex"
    assert set(out["cons_alt"]) == {"cons_base", *A.ORDERS}
    assert out["cons_alt"]["pess"] == A.evaluate_funded(P, micros=30, rules={"day_take": 1500}, policy=500, cons_base="balance")["pess"]
    assert any(w.startswith("AUTOMATION_PROHIBITED") for w in out["warnings"]) and "half" in out["unconfirmed"]
    assert A.evaluate_funded(P, contracts=3, rules={"day_take": 1500}, policy=500)["pess"] == out["pess"]
    with pytest.raises(ValueError):
        A.evaluate_funded(P, micros=35, micros_allowed=False)
    with pytest.raises(ValueError):
        A.evaluate_funded(P, micros=400)
    with pytest.raises(ValueError):
        A.size_micros(contracts=1, micros=10)
    assert A.size_micros(contracts=1.5) == 15 and A.size_micros() is None
    by = A.evaluate_starts(P, micros=30, policy=500, models=("pess",))
    assert set(by) == {"fresh", "plus3000", "plus7600"}
    assert by["plus7600"]["pess"]["p_pay_60"] >= by["fresh"]["pess"]["p_pay_60"] - 1e-12
    # EOD-trail reading never busts more than the intraday trail (same P&L path, lower-or-equal floor)
    sens = A.sensitivity(P, micros=30, policy=500)
    assert set(v for v, _ in sens) == set(A.VARIANTS) == {"base", "cons_balance", "pay4_free", "pay4_req_only", "half_175", "trail_eod",
                                                          "comm_tradovate", "comm_rithmic"}
    assert sens[("trail_eod", "fresh")]["p_bust_any"] <= sens[("base", "fresh")]["p_bust_any"] + 1e-12
    assert sens[("base", "fresh")] == out_base(P)
    assert sens[("cons_balance", "fresh")] == A.evaluate_funded(P, micros=30, policy=500, models=("pess",))["cons_alt"]["pess"]


def out_base(P):
    return A.evaluate_funded(P, micros=30, policy=500, models=("pess",))["pess"]


def test_default_calendar_is_the_in_sample_window():
    cal = A.default_calendar(A.IS_START, A.IS_END)
    assert cal[0] == "2021-09-22" and cal[-1] == "2024-12-31" and len(cal) == 825 and all(d < A.HOLDOUT for d in cal)
    P = A.port_from_trades([tr("2023-03-06", "10:00", 50.0)])
    assert len(P.days) == 825 and P.n_trades == 1
    # outside the cached span: plain weekdays
    assert A.default_calendar("2020-01-06", "2020-01-12") == ["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10"]


def test_holdout_is_sealed(tmp_path):
    ok, bad = tr("2024-12-31", "10:00", 50.0), tr("2025-01-02", "10:00", 50.0)
    with pytest.raises(A.HoldoutError):
        A.port_from_trades([ok, bad])
    with pytest.raises(A.HoldoutError):
        A.load_trades([bad])
    f = tmp_path / "trades.json"
    f.write_text(json.dumps({"trades": [ok, bad]}))
    with pytest.raises(A.HoldoutError):
        A.load_trades(f)
    with pytest.raises(A.HoldoutError):
        A.port_from_trades(str(f))
    with pytest.raises(A.HoldoutError):
        A.port_from_trades([ok], end="2025-06-30")
    with pytest.raises(A.HoldoutError):
        A.port_from_trades([ok], calendar=["2024-12-31", "2025-01-02"])
    assert issubclass(A.HoldoutError, ValueError)
    assert len(A.load_trades(f, allow_holdout=True)) == 2
    P = A.port_from_trades([ok, bad], calendar=["2024-12-31", "2025-01-02"], start="2024-12-31", end="2025-01-02", allow_holdout=True)
    assert P.n_trades == 2
    assert A.port_from_trades([ok]).n_trades == 1
    # a Port that already holds holdout sessions is refused by the scoring entry points too
    for fn in (lambda: A.evaluate_funded(P, micros=10, H=2), lambda: A.search(P, H=2), lambda: A.five_accounts({"P": P, "micros": 10, "H": 2})):
        with pytest.raises(A.HoldoutError):
            fn()
    assert A.evaluate_funded(P, micros=10, H=2, allow_holdout=True)["pess"]["n"] == 1


def test_holdout_seal_covers_entry_and_exit_ms_and_bad_files(tmp_path):
    ok = tr("2024-12-31", "10:00", 50.0)
    ms25 = int(dt.datetime(2025, 3, 3, 10, 0, tzinfo=E.ET).timestamp() * 1000)
    assert A.HOLDOUT_MS == int(dt.datetime(2025, 1, 1, tzinfo=E.ET).timestamp() * 1000)
    # a row LABELLED in-sample whose entry (or only its exit) is in 2025 is a holdout row
    for bad in ({**ok, "entry_ms": ms25, "exit_ms": ms25 + 60000}, {**ok, "exit_ms": ms25}, {**ok, "exit_ms": A.HOLDOUT_MS}):
        with pytest.raises(A.HoldoutError):
            A.load_trades([ok, bad])
        with pytest.raises(A.HoldoutError):
            A.port_from_trades([ok, bad])
        with pytest.raises(A.HoldoutError):
            A.trade_checks([ok, bad])
        assert len(A.load_trades([ok, bad], allow_holdout=True)) == 2
    assert len(A.load_trades([{**ok, "exit_ms": A.HOLDOUT_MS - 1}])) == 1
    # date strings that are not ISO never pass a string comparison silently: refused (HoldoutError is a ValueError too)
    for d in ("01/02/2025", " 2025-01-02", "2024-12-31T10:00", "20241231", dt.date(2024, 12, 31), None):
        with pytest.raises(ValueError):
            A.load_trades([{**ok, "date": d}])
    with pytest.raises(A.HoldoutError):
        A.load_trades([{**ok, "date": dt.date(2025, 1, 2)}])
    # a file whose top-level key is not 'trades' is an error, not an empty ledger
    f = tmp_path / "rows.json"
    f.write_text(json.dumps({"rows": [ok]}))
    with pytest.raises(ValueError, match="'trades' list"):
        A.load_trades(f)
    (tmp_path / "trades.json").write_text(json.dumps({"trades": [ok]}))
    assert len(A.load_trades(tmp_path)) == 1                                # a bundle directory


# ---------------------------------------------------------------- compliance helpers

def test_flags():
    assert A.flags(S300, "donchian", {"tgt_r": 1.0}) == []
    assert A.flags(S300, "bimb_follow", {"tgt_r": 1.0}, {"day_stop": 2250}) == []       # 30% of the threshold: fine at 300K
    assert A.flags(S300, "bimb_follow", {"tgt_r": 1.0}, {"day_stop": 6000}) == ["day_stop_acts_as_trailing_threshold"]
    assert A.flags(S300, "straddle", {"tgt_r": 1.0}) == ["OCO_both_side_orders"]
    assert A.flags(S300, "wall_bounce", {"tgt_r": 1.0}, both_sides=True) == ["OCO_both_side_orders"]
    assert A.flags(S300, "open_dir", {"tgt_r": 0.19}) == ["no_target_or_stop_gt_5x_target"]
    assert A.flags(S300, "open_dir", {"tgt_r": 0.2}) == []
    assert A.flags(S300, "open_dir", {"tgt_r": 1.0}, None, 0.05) == ["mae30_cuts_0.050_NONCOMPLIANT"]
    assert A.flags(S300, "open_dir", {"tgt_r": 1.0}, None, 0.01) == ["mae30_cuts_0.010"]
    assert A.flags(S300, None, None, None, None, 170) == ["max_allowed_size_from_day1"]             # the half cap (17 minis)
    assert A.flags(S300, None, None, None, None, 169) == []
    assert A.flags(S300, None, None, None, None, 30, None, 0.25) == ["stop_ge_80pct_threshold_0.250"]
    # keyword call, as score.py makes it
    assert A.flags(S300, strategy="straddle", inputs={"tgt_r": 0.1}, rules={"day_stop": 7000}, cut_share=0.05, micros=30, both_sides=None,
                   stop_share=None) == ["OCO_both_side_orders", "no_target_or_stop_gt_5x_target", "mae30_cuts_0.050_NONCOMPLIANT",
                                        "day_stop_acts_as_trailing_threshold"]
    # hard = everything except the advisory size flag and MAE cuts within the 2% tolerance
    assert A.hard_flags(["mae30_cuts_0.010", "max_allowed_size_from_day1"]) == []
    assert A.hard_flags(["OCO_both_side_orders", "mae30_cuts_0.010", "mae30_cuts_0.050_NONCOMPLIANT", "one_direction_UNCHECKED"]) == \
        ["OCO_both_side_orders", "mae30_cuts_0.050_NONCOMPLIANT", "one_direction_UNCHECKED"]


# ---------------------------------------------------------------- the compliance gate: all three SPEC criteria

def brk(date, hhmm, stop=30.0, target=20.0, side="long", gross=40.0, entry=15000.0, **kw):
    """A trade with a bracket: stop `stop` pts and target `target` pts from the entry (None = not on the record)."""
    sg = 1.0 if side == "long" else -1.0
    t = tr(date, hhmm, gross, mae=kw.pop("mae", 20.0), mfe=kw.pop("mfe", 60.0), side=side, dur=kw.pop("dur", 5),
           sl=None if stop is None else entry - sg * stop, tp=None if target is None else entry + sg * target, **kw)
    return t


CAL70 = weekdays(70)


def gate(trades, micros=10, **kw):
    """evaluate_funded on a 70-session window (policy None: no payouts) -> the compliance part."""
    return A.evaluate_funded(port(trades, CAL70), micros=micros, policy=None, H=60, models=("pess",), **kw)


def test_trade_checks_per_trade():
    d = CAL70
    rows = [brk(d[0], "10:00"),                                              # 30 / 20 = 1.5
            brk(d[1], "10:00", stop=50.0, target=10.0),                      # exactly 5 : 1 -> allowed
            brk(d[2], "10:00", stop=50.25, target=10.0),                     # one tick over 5 : 1 -> NOT allowed: sl / tp are priced
            brk(d[3], "10:00", stop=51.75, target=10.0),                     # from the fill, there is no slippage allowance
            brk(d[4], "10:00", stop=50.0, target=5.0),                       # 10 : 1
            brk(d[5], "10:00", stop=None),                                   # no stop
            brk(d[6], "10:00", target=None),                                 # no target
            brk(d[7], "10:00", stop=30.0, target=-5.0),                      # 'target' on the wrong side of the entry
            brk(d[8], "10:00", side="short", stop=20.0, target=40.0)]
    c = A.trade_checks(rows)
    assert (c["n"], c["no_stop"], c["no_target"], c["stop_gt_5x"]) == (9, 1, 2, 3)
    assert (c["stamped"], c["resting_entries"], c["both_side_sessions"]) == (0, 0, 0)       # tr(): unstamped market entries
    assert c["max_stop_over_target"] == 10.0 and c["opposite_overlap"] == 0 and c["both_side_orders"] == 0
    # session + window filters (evalcore's session windows on the ET entry time): 10:00 = nyam, 14:00 = pm
    rows2 = [brk(d[0], "10:00", stop=None), brk(d[0], "14:00"), brk(d[40], "10:00", target=None)]
    assert A.trade_checks(rows2, "pm") == {**A.trade_checks([rows2[1]]), "n": 1}
    assert A.trade_checks(rows2, "nyam+pm", end=d[10])["n"] == 2 and A.trade_checks(rows2, "nyam", start=d[1])["no_target"] == 1
    assert A.trade_checks([{"src": rows2, "sess": "pm"}, {"src": rows2, "sess": "nyam"}])["n"] == 3
    assert A.trade_checks([{"src": None, "sess": "pm"}]) is None
    # opposite sides open at the same time (hedging) / a stop-and-reverse at the same millisecond is NOT an overlap
    hedge = [brk(d[0], "10:00", dur=30), brk(d[0], "10:10", side="short", dur=5), brk(d[0], "10:20", dur=5)]
    assert A.trade_checks(hedge)["opposite_overlap"] == 1
    flip = [brk(d[0], "10:00", dur=10), brk(d[0], "10:10", side="short", dur=5)]
    assert A.trade_checks(flip)["opposite_overlap"] == 0
    # rows stamped by the simulator
    assert A.trade_checks([brk(d[0], "10:00", oco=True), brk(d[1], "10:00", both_sides=1), brk(d[2], "10:00", oco=None)])["both_side_orders"] == 2
    # port_from_trades attaches the checks of the rows that went into the portfolio
    P = A.port_from_trades(rows2, sess="pm", calendar=d, start=d[0], end=d[-1])
    assert P.apex_trades == A.trade_checks(rows2, "pm") and A.port_checks(P) == {"n": 1, "no_stop": 0, "opposite_overlap": 0}
    assert A.port_checks(port(hedge + [brk(d[1], "10:00", stop=None)], d)) == {"n": 4, "no_stop": 1, "opposite_overlap": 1}
    # ready-made statistics are accepted in place of rows (score.py's stop_target_stats uses shares)
    assert A._as_checks({"n": 200, "no_stop_share": 0.0, "no_target_share": 0.005, "stop_gt_5x_target_share": 0.0, "max_stop_over_target": 1.5}) == \
        {"n": 200, "no_stop": 0, "no_target": 1, "stop_gt_5x": 0, "max_stop_over_target": 1.5, "opposite_overlap": 0, "both_side_orders": 0,
         "stamped": 0, "resting_entries": 200, "both_side_sessions": 0}      # statistics say nothing about resting orders
    assert A._as_checks({"n": 90})["unproven"] is True                       # nothing was counted: nothing is proven
    # the simulator's evidence: the stamp on every row, the entry kind, and a member's run-level count
    sim = [brk(d[0], "10:00", both_sides=False, oco=False), brk(d[1], "10:00", both_sides=False, oco=False, order_price=15000.0)]
    c = A.trade_checks([{"src": sim, "sess": "all", "both_sides_sessions": 2}])
    assert (c["stamped"], c["resting_entries"], c["both_side_orders"], c["both_side_sessions"]) == (2, 1, 0, 2)
    no_key = [{k: v for k, v in brk(d[0], "10:00").items() if k != "order_price"}]
    assert A.trade_checks(no_key)["resting_entries"] == 1                    # no order_price key: not a proven market entry


def test_gate_one_direction():
    rows = [brk(d, "10:00") for d in CAL70[:30]]
    ok = gate(rows, both_sides=False)
    assert ok["noncompliant"] is False and ok["flags"] == [] and ok["compliance"] == {"one_direction": "ok", "stop_5x_target": "ok", "mae_rule": "ok"}
    # not declared: fills cannot prove the absence of both-side working orders -> UNCHECKED = non-compliant (fail closed)
    un = gate(rows)
    assert un["noncompliant"] is True and un["compliance"]["one_direction"] == "UNCHECKED" and un["flags"] == ["one_direction_UNCHECKED"]
    assert gate(rows, strategy="donchian", inputs={"tgt_r": 1.0})["compliance"]["one_direction"] == "UNCHECKED"
    # the config flag
    bs = gate(rows, both_sides=True)
    assert bs["noncompliant"] is True and bs["compliance"]["one_direction"] == "FAIL" and bs["flags"] == ["OCO_both_side_orders"]
    # OCO / straddle families (R's table) fail whatever the caller declares
    for fam, inp in (("straddle", {"tgt_r": 1.0}), ("orb", {"tgt_r": 1.0}), ("draft_pp_lon_break", {"tgt_r": 1.0}),
                     ("squeeze", {"tgt_r": 1.0, "sq_type": "nr7"}), ("ib", {"tgt_r": 1.0})):
        g = gate(rows, strategy=fam, inputs=inp, both_sides=False)
        assert g["noncompliant"] is True and g["compliance"]["one_direction"] == "FAIL" and "OCO_both_side_orders" in g["flags"], fam
    assert gate(rows, strategy="squeeze", inputs={"tgt_r": 1.0, "sq_type": "bbkc"}, both_sides=False)["noncompliant"] is False
    # trade level: opposite-side positions that overlap, and rows the simulator stamped
    hedge = rows + [brk(CAL70[0], "10:02", side="short")]
    g = gate(hedge, both_sides=False)
    assert g["noncompliant"] is True and g["compliance"]["one_direction"] == "FAIL" and g["flags"] == ["opposite_side_overlap_1"]
    g = gate(rows[:-1] + [brk(CAL70[29], "10:00", oco=True)], both_sides=False)
    assert g["noncompliant"] is True and g["flags"] == ["OCO_both_side_orders"] and g["trade_checks"]["both_side_orders"] == 1


def test_gate_one_direction_is_proven_not_declared():
    """The recheck's hole: straddle rows with no family name and both_sides=False used to pass. One direction is 'ok' only on
    evidence: the simulator's stamp on every row, or (unstamped rows) a declaration PLUS market entries only."""
    days = CAL70[:30]
    market = [brk(d, "10:00") for d in days]                                             # unstamped, order_price None
    resting = [brk(d, "10:00", order_price=15000.0) for d in days]                       # unstamped fills of resting orders
    stamped = [brk(d, "10:00", order_price=15000.0, both_sides=False, oco=False) for d in days]      # l2sim rows, one-sided limits
    oco = [brk(d, "10:00", order_price=15000.0, both_sides=True, oco=True) for d in days]            # l2sim rows of a straddle
    g = gate(market, both_sides=False)
    assert g["compliance"]["one_direction"] == "ok" and g["one_direction_basis"] == "market_entries"
    assert gate(market)["compliance"]["one_direction"] == "UNCHECKED"                    # market entries, nothing declared
    g = gate(resting, both_sides=False)                                                  # the straddle-rows case: declared, unproven
    assert g["compliance"]["one_direction"] == "UNCHECKED" and g["noncompliant"] is True and g["flags"] == ["one_direction_UNCHECKED"]
    for kw in (dict(), dict(both_sides=False), dict(strategy="wall_bounce", inputs={"tgt_r": 2.0})):
        g = gate(stamped, **kw)                                                          # the sim's stamp is the proof, declared or not
        assert g["compliance"]["one_direction"] == "ok" and g["one_direction_basis"] == "sim_rows" and g["noncompliant"] is False, kw
    assert gate(stamped, both_sides=True)["compliance"]["one_direction"] == "FAIL"       # a declared True always fails
    assert gate(stamped[:-1] + [resting[-1]], both_sides=False)["compliance"]["one_direction"] == "UNCHECKED"   # one unstamped row
    for kw in (dict(), dict(both_sides=False)):
        g = gate(oco, **kw)
        assert g["compliance"]["one_direction"] == "FAIL" and "OCO_both_side_orders" in g["flags"], kw
    # a session with both-side orders that never filled leaves no row: the run-level count fails the config
    P = port(stamped, CAL70)
    c = A.compliance(S300, P, micros=10, cut_share=0.0, trades=[{"src": stamped, "sess": "all", "both_sides_sessions": 3}])
    assert c["compliance"]["one_direction"] == "FAIL" and c["flags"] == ["OCO_both_side_orders"]
    c = A.compliance(S300, P, micros=10, cut_share=0.0, trades=[{"src": stamped, "sess": "all", "both_sides_sessions": 0}])
    assert c["noncompliant"] is False
    # compliant() keeps a search row only on proof
    g1 = {"micros": [10], "day_take": [0], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500]}
    assert A.compliant(A.search(port(resting, CAL70), grid=g1, both_sides=False)) == []
    assert len(A.compliant(A.search(port(stamped, CAL70), grid=g1))) == 1


def test_gate_stop_vs_target_per_trade():
    base = [brk(d, "10:00") for d in CAL70[:30]]
    kw = dict(both_sides=False)
    assert gate(base, **kw)["stop_5x_target_basis"] == "rows"
    for bad, flag, key in ((brk(CAL70[30], "10:00", stop=50.0, target=5.0), "no_target_or_stop_gt_5x_target", "stop_gt_5x"),     # 10 : 1
                           (brk(CAL70[30], "10:00", target=None), "no_target_or_stop_gt_5x_target", "no_target"),
                           (brk(CAL70[30], "10:00", stop=None), "no_stop_1", "no_stop")):
        g = gate(base + [bad], **kw)
        assert g["noncompliant"] is True and g["compliance"] == {"one_direction": "ok", "stop_5x_target": "FAIL", "mae_rule": "ok"}, key
        assert g["flags"] == [flag] and g["trade_checks"][key] == 1
    # the rows win over a config that claims a target (inputs say 1R, the records carry none)
    assert gate(base + [brk(CAL70[30], "10:00", target=None)], inputs={"tgt_r": 1.0}, **kw)["noncompliant"] is True
    # config level (R's rule): no target / tgt_r < 0.2
    g = gate(base, inputs={"tgt_r": 0.1}, **kw)
    assert g["noncompliant"] is True and g["flags"] == ["no_target_or_stop_gt_5x_target"] and g["compliance"]["stop_5x_target"] == "FAIL"
    assert gate(base, inputs={"tgt_r": 0.0}, **kw)["noncompliant"] is True and gate(base, inputs={"tgt_r": 0.2}, **kw)["noncompliant"] is False
    # no rows (a Port from elsewhere): the per-trade check cannot run -> `inputs` give the verdict, else UNCHECKED
    P = port(base, CAL70)
    del P.apex_trades
    ev = lambda **k: A.evaluate_funded(P, micros=10, policy=None, models=("pess",), both_sides=False, **k)
    g = ev()                                                                 # without rows NOTHING is proven, declared or not
    assert g["noncompliant"] is True and g["compliance"]["stop_5x_target"] == "UNCHECKED"
    assert g["flags"] == ["one_direction_UNCHECKED", "stop_vs_target_UNCHECKED"]
    g = ev(inputs={"tgt_r": 1.5})                                            # the declared target proves the 5:1 rule only
    assert g["compliance"] == {"one_direction": "UNCHECKED", "stop_5x_target": "ok", "mae_rule": "ok"} and g["noncompliant"] is True
    assert g["stop_5x_target_basis"] == "inputs" and g["trade_checks"] is None
    for inp in ({}, {"stop_val": 1.5}, {"tgt_r": "2"}, {"tgt_r": True}):     # FAIL-OPEN EDGE: inputs without a numeric tgt_r
        assert ev(inputs=inp)["compliance"]["stop_5x_target"] == "UNCHECKED", inp           # (R assumes 2.0) prove nothing
    assert ev(inputs={"tgt_r": None})["compliance"]["stop_5x_target"] == "FAIL"           # 'no target' (R's flag)
    assert ev(trades=base)["stop_5x_target_basis"] == "rows" and ev(trades=base)["noncompliant"] is False
    assert ev(trades=base + [brk(CAL70[30], "10:00", target=None)])["noncompliant"] is True
    stats = {"n": 30, "no_stop_share": 0.0, "no_target_share": 1 / 30, "stop_gt_5x_target_share": 0.0, "max_stop_over_target": 1.5}
    assert ev(trades=stats)["flags"] == ["one_direction_UNCHECKED", "no_target_or_stop_gt_5x_target"]
    ok = ev(trades={**stats, "no_target_share": 0.0})                        # complete statistics prove 5:1, never one direction
    assert ok["compliance"] == {"one_direction": "UNCHECKED", "stop_5x_target": "ok", "mae_rule": "ok"} and ok["noncompliant"] is True
    assert ev(trades={**stats, "no_target_share": 0.0, "resting_entries": 0})["noncompliant"] is False
    # FAIL-OPEN EDGES: a bare count, and rows that do not cover the portfolio (one clean row against 30 trades)
    for weak in ({"n": 30}, base[:1], base[:29]):
        g = ev(trades=weak, inputs={"tgt_r": 2.0})
        assert g["compliance"]["stop_5x_target"] == "UNCHECKED" and g["compliance"]["one_direction"] == "UNCHECKED", weak
        assert g["noncompliant"] is True and g["stop_5x_target_basis"] is None
    assert ev(trades=base + [brk(CAL70[40], "10:00")])["noncompliant"] is False          # MORE rows than the Port: still a proof
    # one tick over 5 : 1 on a single row fails (no slippage allowance)
    assert gate(base + [brk(CAL70[30], "10:00", stop=50.25, target=10.0)], **kw)["compliance"]["stop_5x_target"] == "FAIL"
    assert gate(base + [brk(CAL70[30], "10:00", stop=50.0, target=10.0)], **kw)["noncompliant"] is False
    # a Port trade without a stop fails even when `inputs` look fine
    Pn = port(base + [brk(CAL70[30], "10:00", stop=None)], CAL70)
    del Pn.apex_trades
    g = A.evaluate_funded(Pn, micros=10, policy=None, models=("pess",), both_sides=False, inputs={"tgt_r": 1.0})
    assert g["noncompliant"] is True and g["flags"] == ["one_direction_UNCHECKED", "no_stop_1"] and abs(g["no_stop_share"] - 1 / 31) < 1e-12
    assert g["compliance"]["stop_5x_target"] == "FAIL"
    # the trailing threshold used as the stop: a 300-pt stop at 10 micros = $6,000 = 80% of $7,500; or a $6,000 day stop
    g = gate(base + [brk(CAL70[30], "10:00", stop=300.0, target=100.0)], **kw)
    assert g["noncompliant"] is True and g["compliance"]["stop_5x_target"] == "FAIL" and g["flags"][0].startswith("stop_ge_80pct_threshold_")
    g = gate(base, rules={"day_stop": 6000}, **kw)
    assert g["noncompliant"] is True and g["flags"] == ["day_stop_acts_as_trailing_threshold"]
    assert gate(base, rules={"day_stop": 2250}, **kw)["noncompliant"] is False


def test_gate_mae_rule_and_unchecked():
    # 30 micros, MAE 800 / NQ -> open loss 2,400 >= 2,250: cut. 1 of 30 trades = 3.3% > 2% -> FAIL; 1 of 60 = 1.7% -> tolerated
    rows = [brk(d, "10:00") for d in CAL70[:29]] + [brk(CAL70[29], "10:00", mae=800.0)]
    g = gate(rows, micros=30, both_sides=False)
    assert g["pess"]["cuts"] > 0 and g["pess"]["cut_share"] > A.CUT_OK
    assert g["noncompliant"] is True and g["compliance"] == {"one_direction": "ok", "stop_5x_target": "ok", "mae_rule": "FAIL"}
    assert [f for f in g["flags"] if f.endswith("_NONCOMPLIANT")] and len(g["flags"]) == 1
    rows = [brk(d, "10:00") for d in CAL70[:59]] + [brk(CAL70[59], "10:00", mae=800.0)]
    g = gate(rows, micros=30, both_sides=False)
    assert 0 < g["pess"]["cut_share"] <= A.CUT_OK and g["noncompliant"] is False and g["compliance"]["mae_rule"] == "ok"
    assert len(g["flags"]) == 1 and g["flags"][0].startswith("mae30_cuts_") and A.hard_flags(g["flags"]) == []
    # the gate called on its own without a cut share cannot vouch for the MAE rule
    P = port(rows, CAL70)
    c = A.compliance(S300, P, micros=30, both_sides=False)
    assert c["noncompliant"] is True and c["compliance"]["mae_rule"] == "UNCHECKED" and c["flags"] == ["mae_rule_UNCHECKED"]
    assert A.compliance(S300, P, micros=30, both_sides=False, cut_share=0.0)["noncompliant"] is False
    # noncompliant <=> a hard flag, in every combination above
    for kw in (dict(), dict(both_sides=False), dict(both_sides=True), dict(both_sides=False, inputs={"tgt_r": 0.1}),
               dict(both_sides=False, rules={"day_stop": 7000}), dict(strategy="straddle")):
        for cs in (None, 0.0, 0.01, 0.5):
            c = A.compliance(S300, P, micros=170, cut_share=cs, **kw)
            assert c["noncompliant"] == bool(A.hard_flags(c["flags"])) == any(v != "ok" for v in c["compliance"].values()), (kw, cs)


def test_gate_is_the_same_in_evaluate_funded_and_search():
    """The verifier's case: a straddle with tgt_r 0.1 and a $7,000 day stop must be non-compliant in BOTH entry points, and
    compliant() must drop rows failing ANY of the three criteria."""
    ts, cal = clean_trades(4, ndays=100)
    P = port(ts, cal)
    g = {"micros": [10], "day_take": [0], "day_lock": [0], "day_stop": [0, 7000], "max_day_tr": [0], "policy": [500]}
    cases = {"straddle": dict(strategy="straddle", inputs={"tgt_r": 0.1}, both_sides=True),
             "oco_family_only": dict(strategy="orb", inputs={"tgt_r": 1.0}),
             "tight_target": dict(strategy="open_dir", inputs={"tgt_r": 0.1}, both_sides=False),
             "undeclared": dict(),
             "clean": dict(strategy="open_dir", inputs={"tgt_r": 0.67}, both_sides=False)}
    for name, kw in cases.items():
        rows = A.search(P, grid=g, **kw)
        for r in rows:
            ev = A.evaluate_funded(P, micros=10, rules={"day_stop": r["day_stop"]}, policy=500, models=("pess",), **kw)
            assert r["apex_noncompliant"] == ev["noncompliant"] and r["apex_flags"] == ";".join(ev["flags"]), (name, r["day_stop"])
            assert {k: r["apex_" + k] for k in ev["compliance"]} == ev["compliance"]
            assert r["mae_over_limit_share"] == ev["mae_over_limit_share"]
        ok = A.compliant(rows)
        if name == "clean":
            assert [r["day_stop"] for r in ok] == [0] and rows[1]["apex_stop_5x_target"] == "FAIL"     # the $7,000 day stop
        else:
            assert ok == [] and all(r["apex_noncompliant"] for r in rows), name
    ev = A.evaluate_funded(P, micros=10, rules={"day_stop": 7000}, policy=500, models=("pess",), **cases["straddle"])
    assert ev["flags"][:3] == ["OCO_both_side_orders", "no_target_or_stop_gt_5x_target", "day_stop_acts_as_trailing_threshold"] and ev["noncompliant"]
    # per-trade stops against targets through search: rows without a target sink the whole grid
    ts2 = [dict(t, tp=None) for t in ts]
    assert A.compliant(A.search(port(ts2, cal), grid=g, both_sides=False)) == []
    assert A.compliant(A.search(port(ts, cal), grid=g, both_sides=False)) != []                      # rows prove the 5:1 rule
    # rows without the verdict are never 'compliant'
    assert A.compliant([{"micros": 10}, {"apex_noncompliant": None}, {"apex_noncompliant": True}]) == []


def test_stop_over_threshold_share():
    # 100 micros x 30 pts x $2 = 6,000 = 80% of 7,500 -> counted; 29 pts -> not; a trade without a stop is reported apart
    ts = [tr(D1, "10:00", 10.0, sl=15030.0), tr(D1, "11:00", 10.0, sl=14971.0), tr(D1, "12:00", 10.0)]
    P = port(ts, CAL3)
    share, nos = A.stop_over_threshold_share(P, 100, 175, 7500.0)
    assert abs(share - 0.5) < 1e-12 and abs(nos - 1 / 3) < 1e-12
    assert A.stop_over_threshold_share(P, 300, 175, 7500.0)[0] == 1.0       # capped at 175: 175 x 29 x 2 = 10,150
    assert A.stop_over_threshold_share(port([tr(D1, "10:00", 10.0)], CAL3), 100, 175, 7500.0) == (None, 1.0)


def test_cross_account_conflicts():
    a = [tr(D1, "10:00", 10.0, side="long", dur=30), tr(D1, "12:00", 10.0, side="short", dur=5)]
    b = [tr(D1, "10:15", 10.0, side="short", dur=5), tr(D1, "12:10", 10.0, side="long", dur=5)]
    c = [tr(D1, "10:17", 10.0, side="long", dur=5)]
    r = A.cross_account_conflicts({"a": a, "b": b, "c": c})
    assert r["conflicts"] == 2 and r["by_pair"] == {("a", "b"): 1, ("b", "c"): 1}
    r = A.cross_account_conflicts({"a": a, "b": b})
    assert r["conflicts"] == 1 and r["by_pair"] == {("a", "b"): 1} and len(r["examples"]) == 1
    assert A.cross_account_conflicts({"a": a, "c": c})["conflicts"] == 0    # same side overlapping: fine
    assert A.cross_account_conflicts({"a": a + b})["conflicts"] == 0        # same account: not a cross-account hedge
    # side spellings are normalised (a silent 'everything that is not "long" is short' would hide a hedge)
    for lo, sh in (("long", "short"), ("buy", "sell"), ("Long", "Short"), ("BUY", "SELL"), (1, -1), ("1", "-1"), (1.0, -1.0), ("B", "S")):
        x = [dict(tr(D1, "10:00", 10.0, dur=30), side=lo)]
        y = [dict(tr(D1, "10:15", 10.0, dur=5), side=sh)]
        assert A.cross_account_conflicts({"x": x, "y": y})["conflicts"] == 1, (lo, sh)
        assert A.cross_account_conflicts({"x": x, "y": [dict(y[0], side=lo)]})["conflicts"] == 0
        assert (A.side_sign(lo), A.side_sign(sh)) == (1, -1)
    for bad in ("flat", "", None, 0, 2, True):
        with pytest.raises(ValueError, match="unknown trade side"):
            A.cross_account_conflicts({"x": [dict(tr(D1, "10:00", 10.0), side=bad)], "y": []})


# ---------------------------------------------------------------- search + compute windows

def test_search_rows_stability_and_workers():
    ts, cal = clean_trades(21, ndays=110)
    P = port(ts, cal)
    grid = {"micros": [20, 50, 400], "day_take": [0, 1500], "day_lock": [0], "day_stop": [0, 6000], "max_day_tr": [1, 0], "policy": [500, "max"]}
    kw = dict(strategy="open_dir", inputs={"tgt_r": 0.67}, both_sides=False)
    rows = A.search(P, grid=grid, **kw)
    assert len(rows) == 2 * 2 * 1 * 2 * 2 * 2 and sorted({r["micros"] for r in rows}) == [20, 50]      # 400 > 350 dropped
    assert {r["mae_over_limit_share"] > 0 for r in rows if r["micros"] == 50} == {True}
    assert all("stab_e_net_40" in r and "score_p_pay_20" in r and r["start"] == "fresh" and r["firm"] == "apex300_pa" for r in rows)
    assert all(r["apex_noncompliant"] for r in rows if r["day_stop"] == 6000)
    assert all(r["apex_noncompliant"] == (r["cut_share"] > A.CUT_OK) for r in rows if r["day_stop"] == 0)
    assert any(r["apex_noncompliant"] for r in rows if r["day_stop"] == 0) and not all(r["apex_noncompliant"] for r in rows)
    ok = A.compliant(rows)
    assert ok and all(r["day_stop"] == 0 and r["cut_share"] <= A.CUT_OK for r in ok)
    pk = A.pick_cells(ok, min_p60=0.0)
    assert pk["e40_raw"]["e_net_40"] == max(r["e_net_40"] for r in ok)
    # one row == evaluate_funded of the same config, the other consistency reading included
    r0 = next(r for r in rows if (r["micros"], r["day_take"], r["day_stop"], r["max_day_tr"], r["policy"]) == (50, 1500, 0, 1, 500))
    ev = A.evaluate_funded(P, micros=50, rules={"day_take": 1500, "max_day_tr": 1}, policy=500, models=("pess",), **kw)
    assert all(r0[k] == v for k, v in ev["pess"].items())
    assert r0["cons_base"] == "cycle" and all(r0[f"{k}_cons_balance"] == ev["cons_alt"]["pess"][k] for k in A.ALT_KEYS)
    assert r0["apex_noncompliant"] == ev["noncompliant"] and r0["apex_flags"] == ";".join(ev["flags"])
    assert "e_net_40_cons_balance" not in A.search(P, grid={**grid, "micros": [20], "day_stop": [0]}, both_cons=False)[0]
    assert "e_net_40_cons_cycle" in A.search(P, A.make_spec(cons_base="balance"), {**grid, "micros": [20], "day_stop": [0]})[0]
    # 2 workers == serial; a start state changes the answer
    g2 = {"micros": [30], "day_take": [0, 1500], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500, 1500]}
    a, b = A.search(P, grid=g2, workers=1, **kw), A.search(P, grid=g2, workers=2, **kw)
    assert [{k: v for k, v in r.items()} for r in a] == [{k: v for k, v in r.items()} for r in b]
    c = A.search(P, grid=g2, start="plus7600")
    assert all(r["start"] == "plus7600" for r in c) and [r["e_net_40"] for r in c] != [r["e_net_40"] for r in a]
    with pytest.raises(ValueError):
        A.search(P, F.make_spec("apex"))
    # the positional call score.py makes: (port, S, grid, model, H, workers, start) + the compliance keywords
    d = A.search(P, S300, g2, None, 60, 1, "fresh", strategy="open_dir", inputs={"tgt_r": 0.67}, both_sides=False)
    assert [r["e_net_40"] for r in d] == [r["e_net_40"] for r in a] and [r["apex_noncompliant"] for r in d] == [r["apex_noncompliant"] for r in a]


def test_search_workers_capped_at_8(monkeypatch):
    seen = []

    class FakePool:
        def __init__(self, n):
            seen.append(n)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, xs, chunksize=1):
            return [fn(x) for x in xs]

    class Ctx:
        Pool = FakePool

    monkeypatch.setattr(A.mp, "get_context", lambda kind: Ctx)
    ts, cal = rand_trades(3, ndays=70)
    g = {"micros": [20], "day_take": [0], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500]}
    A.search(port(ts, cal), grid=g, workers=64)
    assert seen == [8] and A.MAX_WORKERS == 8


# ---------------------------------------------------------------- clear errors (short window, unknown start)

def test_clear_errors_short_window_and_unknown_start():
    ts, cal = clean_trades(2, ndays=20)
    P = port(ts, cal)
    for fn in (lambda: A.evaluate_funded(P, micros=10), lambda: A.search(P), lambda: A.five_accounts({"P": P, "micros": 10})):
        with pytest.raises(ValueError, match="window too short: 20 sessions < the 60-session horizon"):
            fn()
    assert A.evaluate_funded(P, micros=10, H=20)["pess"]["n"] == 1          # a horizon that fits is fine
    assert A.lifecycle(S300, A.day_src(S300, P, None, 10)) == []             # low level (score.py reports 'skipped' itself)
    for bad in ("plus7500", "Fresh", "", None, [3000], True):
        with pytest.raises(ValueError, match="start"):
            A.as_start(bad)
    with pytest.raises(ValueError, match="unknown start state 'plus7500'.*fresh.*plus3000.*plus7600"):
        A.evaluate_funded(P, micros=10, H=20, start="plus7500")
    with pytest.raises(ValueError, match="unknown start state"):
        A.search(P, H=20, start="plus7500")


def test_start_validation():
    S = S300
    ok = lambda **k: A.resolve_start(S, A.Start(**k))
    # defaults filled in
    assert A.resolve_start(S, "fresh") == A.Start(0.0, 0.0, False, 0, 0.0, 0, 0, 0.0, 0.0)
    assert A.resolve_start(S, "plus7600") == A.Start(7600.0, 7600.0, False, 0, 0.0, 0, 0, 0.0, 0.0)
    assert A.resolve_start(S, 9000) == A.Start(9000.0, 9000.0, True, 0, 0.0, 0, 0, 0.0, 0.0)
    assert A.resolve_start(S, A.resolve_start(S, "plus3000")) == A.resolve_start(S, "plus3000")       # idempotent
    # approved payouts imply the locked threshold (floor +100, not 3,000 - 7,500), full size and a used-up split band
    st = ok(profit=3000.0, pays=3)
    assert (st.peak, st.full, st.paid_gross) == (7600.0, True, 10500.0) and A.floor_of(S, st.peak) == 100.0
    # 8 x +100 then -4,000: the old code paid 3,500 on day 8 and trailed from -4,500; now the floor is +100, no payout (3,800 < 7,600)
    # and the account dies on the -4,000 day (3,800 - 4,000 <= 100)
    assert run([100.0] * 8 + [-4000.0], 500, start=A.Start(3000.0, pays=3))[0][:2] == (9, [])
    assert ok(profit=20000.0, pays=7).paid_gross == 5 * 3500.0              # conservative default: capped payouts only
    # impossible states are refused with the reason
    for kw, msg in ((dict(profit=5000.0, peak=2000.0), "below the balance"),
                    (dict(profit=-8000.0), "already closed"),
                    (dict(profit=0.0, peak=7600.0), "already closed"),      # locked floor +100 >= balance
                    (dict(profit=500.0, peak=8200.0), None),
                    (dict(profit=-2000.0, peak=5600.0), "already closed"),  # floor 5,600 - 7,500 = -1,900
                    (dict(profit=3000.0, peak=4000.0, pays=1), "imply the peak reached"),
                    (dict(profit=3000.0, full=True), "full=True needs"),
                    (dict(profit=8000.0, paid_gross=500.0), "paid_gross > 0 with pays = 0"),
                    (dict(profit=8000.0, pays=2, paid_gross=600.0), "below 2 x the minimum payout"),
                    (dict(profit=8000.0, pays=2, paid_gross=7500.0), "exceeds 2 x the payout cap"),
                    (dict(profit=8000.0, cd=2, cw=3), "cw .* cannot exceed cd"),
                    (dict(profit=8000.0, cmax=500.0), "need cd >= 1"),
                    (dict(profit=8000.0, pays=-1), "must be >= 0")):
        if msg is None:
            assert ok(**kw).peak == 8200.0
            continue
        with pytest.raises(ValueError, match=msg):
            ok(**kw)
    with pytest.raises(ValueError, match="invalid start state"):
        A.evaluate_funded(port(*clean_trades(1, ndays=70)), micros=10, start=A.Start(5000.0, peak=2000.0))
    with pytest.raises(ValueError, match="invalid start state"):
        run([1.0], None, start=-8000.0)
    # the 50K spec has its own levels: +3,000 is above its safety net (2,600) -> locked and full size
    assert A.resolve_start(A.make_spec("apex50_pa"), "plus3000") == A.Start(3000.0, 3000.0, True, 0, 0.0, 0, 0, 0.0, 0.0)


def test_resolve_start_is_idempotent_for_every_state():
    """Regression (recheck): Start(3000, pays=3) resolved to peak 7,600 / full=True, and the SECOND pass rejected that as
    'full=True needs an EOD balance above +7600' -> evaluate_funded / search / five_accounts (which resolve twice) crashed."""
    states = ["fresh", "plus3000", "plus7600", 9000, -3000.0, A.Start(3000.0, pays=3), A.Start(7600.0, pays=1), A.Start(100.5, pays=1),
              A.Start(8000.0, pays=2), A.Start(3000.0, pays=3, peak=9000.0), A.Start(20000.0, pays=7), A.Start(500.0, peak=8200.0),
              A.Start(9000.0, peak=9500.0, full=True, cd=3, cw=2, cmax=400.0, cpnl=700.0), A.Start(8000.0, pays=2, paid_gross=1200.0)]
    for S in (S300, S300R, A.make_spec("apex50_pa")):
        for st in states:
            if S.name == "apex50_pa" and (isinstance(st, str) or isinstance(st, (int, float))):
                st = {"fresh": 0.0, "plus3000": 1000.0, "plus7600": 2600.0}.get(st, 1500.0)
            try:
                once = A.resolve_start(S, st)
            except ValueError:
                continue                                                     # a state this spec does not allow
            assert A.resolve_start(S, once) == once, (S.name, st)
            assert A.resolve_start(S, A.resolve_start(S, once)) == once
    # the state the fix was written for runs through every entry point that resolves twice
    ts, cal = clean_trades(3, ndays=100)
    P = port(ts, cal)
    for st in (A.Start(3000.0, pays=3), A.Start(7600.0, pays=1)):
        ev = A.evaluate_funded(P, micros=20, policy=500, start=st, models=("pess",), both_sides=False)
        assert ev["pess"]["n"] == 41 and ev["start"].endswith("_custom")
        g = {"micros": [20], "day_take": [0], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500]}
        assert len(A.search(P, grid=g, start=st, both_sides=False)) == 1
        five = A.five_accounts(dict(P=P, micros=20, policy=500, start=st, both_sides=False))
        assert five["n_accounts"] == 5 and five["e_total_40"] == pytest.approx(5 * ev["pess"]["e_net_40"])
    # not a number is not a state
    for bad in (float("nan"), float("inf"), A.Start(3000.0, peak=float("nan")), A.Start(8000.0, pays=1, paid_gross=float("inf"))):
        with pytest.raises(ValueError, match="finite"):
            A.resolve_start(S300, bad)


def test_robustness_for_direct_callers():
    # an R day source built WITHOUT events would never show a breach: as_src rebuilds it with events
    ts, cal = rand_trades(2, ndays=140, scale=2.5)
    P = port(ts, cal)
    with_ev, no_ev = F.DaySrc(P, None, 100, events=True), F.DaySrc(P, None, 100, events=False)
    a = A.lifecycle(S300R, with_ev, 500, 60, "pess")
    assert A.lifecycle(S300R, no_ev, 500, 60, "pess") == a and sum(r[0] > 0 for r in a) > 10
    assert A.as_src(S300R, with_ev) is with_ev and A.as_src(S300R, no_ev) is not no_ev
    # five_accounts on a finished result that lacks the gate's verdict is not compliant
    one = A.evaluate_funded(P, micros=40, policy=500, models=("pess",), both_sides=False)
    bare = {k: v for k, v in one.items() if k not in ("noncompliant", "flags", "compliance")}
    assert A.five_accounts(bare)["noncompliant"] is True and A.five_accounts(one)["noncompliant"] == one["noncompliant"]


# ---------------------------------------------------------------- the Legacy 300K EVALUATION (score.py firm 'apex300_eval')

EV = A.make_eval_spec()


def ev_run(days, order="pess", S=EV, **kw):
    src = Fake(days)
    return A.eval_sim(S, src, 0, len(days), order, **kw), src


def test_eval_spec_values():
    assert (EV.target, EV.mll, EV.cap, EV.min_days, EV.trail, EV.lock_at, EV.primary) == (20000.0, 7500.0, 350, 7, "intraday", None, "pess")
    assert (EV.comm_nq, EV.comm_mnq) == A.COMMISSIONS["apex"]
    h = A.make_eval_spec(**A.EVAL_VARIANTS["holder_rule_file"])            # the homebase rule file (account holder's wording)
    rid, r = E.firm_rules(A.EVAL300["homebase_rule_id"])
    assert (h.target, h.mll, h.lock_at, h.lock_floor, h.min_days, h.cap) == (r["eval_target"], r["trailing_mll"], r["lock_at"], r["lock_floor"],
                                                                             r["eval_min_days"], r["cap_micros"])
    assert h.trail == "eod" and h.comm_nq is None
    for bad in (dict(target_usd=1), dict(commission="x"), dict(trail="hourly"), dict(lock_at=7600.0)):
        with pytest.raises(ValueError):
            A.make_eval_spec(**bad)


def test_eval_pass_needs_the_goal_at_a_close_and_seven_traded_days():
    assert ev_run([3000.0] * 7)[0] == (1, 7, 7)                              # 21,000 on the 7th traded day
    assert ev_run([3000.0] * 6)[0] == (0, 6, 6)                              # 18,000: not yet
    assert ev_run([4000.0] * 10)[0] == (1, 7, 7)                             # goal reached on day 5, days missing until day 7
    assert ev_run([20000.0] + [0.0] * 19)[0] == (0, 20, 1)                   # no-trade days are not trading days
    assert ev_run([20000.0] + [1.0] * 6)[0] == (1, 7, 7)
    assert ev_run([20000.0], S=A.make_eval_spec(min_days=1))[0] == (1, 1, 1)
    # the goal must hold at a CLOSE: an intraday high of +21,000 that closes at +19,000 is not a pass
    assert ev_run([3000.0] * 6 + [day(1000.0, high=3000.0)])[0] == (0, 7, 7)


def test_eval_threshold_trails_the_live_balance_and_never_locks():
    # the day's HIGH lifts the threshold before the low is tested (pess): +5,000 then -3,000 <= 5,000 - 7,500
    d = day(4000.0, low=-3000.0, high=5000.0)
    assert ev_run([d])[0] == (2, 1, 0)
    assert ev_run([d], order="opt")[0][0] == 0                               # low first: -3,000 > -7,500, then up
    assert ev_run([d], S=A.make_eval_spec(trail="eod"))[0][0] == 0           # the account holder's reading: closes only
    giveback = day(-3000.0, low=-3000.0, high=5000.0)                        # a close 8,000 below the day's high busts in ANY order
    assert ev_run([giveback])[0][0] == 2 and ev_run([giveback], order="opt")[0][0] == 2
    assert ev_run([giveback], S=A.make_eval_spec(trail="eod"))[0][0] == 0
    assert ev_run([day(-7499.0)])[0][0] == 0 and ev_run([day(-7500.0)])[0] == (2, 1, 0)
    # no lock: after a +10,000 close the threshold is +2,500; a low of 2,400 busts. The rule file's lock (+100) would survive.
    assert ev_run([10000.0, day(-7000.0, low=-7600.0)])[0] == (2, 2, 1)
    lock = A.make_eval_spec(lock_at=7600.0, lock_floor=100.0)
    assert ev_run([10000.0, day(-7000.0, low=-7600.0)], S=lock)[0] == (0, 2, 2)
    assert ev_run([10000.0, day(-9900.0)], S=lock)[0] == (2, 2, 1)           # 100 <= 100
    # a bust on the day the goal would have been reached is a bust
    assert ev_run([3000.0] * 6 + [day(3000.0, low=-8000.0)])[0] == (2, 7, 6)


def test_eval_coast_and_target_take():
    (res, src) = ev_run([10000.0, 10000.0] + [100.0] * 5, coast=1)
    assert res == (1, 7, 7) and src.caps == [350, 350, 1, 1, 1, 1, 1]        # goal reached after day 2: the rest at 1 micro
    assert ev_run([10000.0, 10000.0] + [100.0] * 5)[1].caps == [350] * 7
    # target_take on a real walk: 300 micros, six days of +$100 / NQ (= +3,000 - cost) then a trade that peaks at +$150 / NQ and
    # closes at -$50 / NQ. Without the take the 7th day loses; with it the day is flattened exactly at the goal.
    cal = weekdays(8)
    ts = [tr(cal[i], "10:00", 100.0, mfe=100.0) for i in range(6)] + [tr(cal[6], "10:00", -50.0, mae=50.0, mfe=150.0)]
    P = port(ts, cal)
    S = A.make_eval_spec(commission="R")
    src = A.eval_src(S, P, None, 300)
    c = E.cost(300)
    assert A.eval_sim(S, src, 0, 8, "pess") == (0, 8, 7)
    out = A.eval_sim(S, src, 0, 8, "pess", target_take=True)
    assert out == (1, 7, 7)
    level = 20000.0 - 6 * (3000.0 - c)
    assert src.take(6, 350, level)[0] == pytest.approx(level)                # R's target_take law: the day ENDS at the level
    Aw = E.walk(P, 350, E.norm_rules(None), micros=300)                      # ... and it is evalcore's own number for that day
    assert Aw.rewalk(6, level)[0] == pytest.approx(src.take(6, 350, level)[0])
    assert A.eval_sim(S, src, 0, 8, "opt", target_take=True)[0] == 1
    # the take is not used before the day count allows a pass
    ts2 = [tr(cal[i], "10:00", 100.0, mfe=100.0) for i in range(8)]
    src2 = A.eval_src(S, port(ts2, cal), None, 300)
    assert A.eval_sim(S, src2, 0, 8, "pess", target_take=True) == (1, 7, 7) and not any(k[2:3] == ("take",) for k in src2.memo if k[0] < 6)


def test_eval_holder_reading_equals_evalcore_race_on_the_homebase_rule_file():
    """The existing rule file (apex-legacy-300k@2026-09-28: EOD trail locking at +100, 1 day, R's costs) scored by R's own
    evalcore.race ('intraday' breach) must give the SAME attempt outcomes as eval_sim on the 'holder_rule_file' reading."""
    rid, r = E.firm_rules(A.EVAL300["homebase_rule_id"])
    S = A.make_eval_spec(**A.EVAL_VARIANTS["holder_rule_file"])
    n = passes = busts = 0
    for seed in range(4):
        ts, cal = rand_trades(seed, ndays=150, scale=3.0)
        P = port(ts, cal)
        idx = __import__("numpy").arange(len(cal) - 20 + 1)[:, None] + __import__("numpy").arange(20)
        for mi, rules in ((120, None), (250, {"day_take": 2500, "max_day_tr": 2}), (350, {"day_stop": 1500, "day_lock": 2000})):
            Aw = E.walk(P, r["cap_micros"], E.norm_rules(rules), micros=mi, dll=0.0, day_take=E.take_rules(rules)[0])
            ro, rd = E.race(idx, Aw, r, "intraday", False, False)
            for order in A.ORDERS:                                           # under an EOD trail the event order cannot matter
                o, d = A.eval_lifecycle(S, A.eval_src(S, P, rules, mi), 20, order)
                assert (o == ro).all() and (d[o > 0] == rd[ro > 0]).all(), (seed, mi, rules, order)
            n += len(ro)
            passes += int((ro == 1).sum())
            busts += int((ro == 2).sum())
    assert n > 1000 and passes > 50 and busts > 50                           # not a degenerate comparison
    # and the default (help-centre) reading is never easier than the account holder's on the same attempts
    ts, cal = rand_trades(1, ndays=150, scale=3.0)
    P = port(ts, cal)
    hold = A.eval_metrics(*A.eval_lifecycle(S, A.eval_src(S, P, None, 250), 20, "pess"))
    cons = A.eval_metrics(*A.eval_lifecycle(A.make_eval_spec(commission="R"), A.eval_src(EV, P, None, 250), 20, "pess"))
    assert cons["p_pass_20"] <= hold["p_pass_20"] and cons["bust_20"] >= hold["bust_20"]
    assert set(hold) == {"n", "p_pass_10", "bust_10", "neither_10", "p_pass_20", "bust_20", "neither_20", "med_days"}
    assert abs(hold["p_pass_10"] + hold["bust_10"] + hold["neither_10"] - 1.0) < 1e-12 and hold["p_pass_10"] <= hold["p_pass_20"]


# ---------------------------------------------------------------- Apex commission schedule

def test_apex_commissions_and_R_costs_stay_intact():
    assert A.COMMISSIONS == {"apex": (3.98, 1.04), "tradovate": (3.10, 1.04), "rithmic": (3.98, 1.02), "R": None}
    assert A.cost(13) == E.cost(13) == 7.0 and A.cost(13, (3.98, 1.04)) == 3.98 + 3 * 1.04 and A.cost(100, (3.10, 1.04)) == 31.0
    # per NQ: gross +100 -> 100 micros: 1,000 - 10 x commission; 13 micros: 130 - (1 NQ + 3 MNQ)
    P = port([tr(D1, "10:00", 100.0, mae=20.0, mfe=120.0)], CAL3)
    exp = {"apex": (1000 - 39.8, 130 - (3.98 + 3 * 1.04)), "tradovate": (1000 - 31.0, 130 - (3.10 + 3 * 1.04)),
           "rithmic": (1000 - 39.8, 130 - (3.98 + 3 * 1.02)), "R": (960.0, 123.0)}
    for name, (big, small) in exp.items():
        S = A.make_spec(commission=name)
        assert A.day_src(S, P, None, 100).get(0, 170, 0.0, 0.0)[0] == pytest.approx(big, abs=1e-9), name
        assert A.day_src(S, P, None, 13).get(0, 170, 0.0, 0.0)[0] == pytest.approx(small, abs=1e-9), name
        assert F.cost is E.cost                                             # R's cost model is restored after every walk
    # a plain R source is re-based on the spec's schedule by lifecycle / simulate (score.py passes R's funded.DaySrc) ...
    cal = weekdays(61)
    P = port([tr(cal[0], "10:00", 100.0, mae=20.0, mfe=120.0)], cal)
    rsrc = F.DaySrc(P, None, 100, events=True)
    assert A.as_src(S300, rsrc) is A.as_src(S300, rsrc) is not rsrc and A.as_src(S300, rsrc).comm == (3.98, 1.04)
    assert A.as_src(SR, rsrc) is rsrc                                       # commission 'R': R's source as is
    mine = A.day_src(S300, P, None, 100)
    assert A.as_src(S300, mine) is mine and A.as_src(SR, mine).comm is None
    # ... so the Apex-cost and R-cost lifecycles differ by exactly the commission, whatever source is passed
    never = dict(T=None, H=60)
    for src in (rsrc, mine):
        assert A.metrics(A.lifecycle(S300, src, **never), 60) == A.metrics(A.lifecycle(S300, mine, **never), 60)
    assert rsrc.get(0, 170, 0.0, 0.0)[0] == 960.0 and F.cost is E.cost     # the R source itself still walks on R's costs
    ev = A.evaluate_funded(P, micros=100, policy=None, models=("pess",))
    evr = A.evaluate_funded(P, micros=100, policy=None, models=("pess",), commission="R")
    assert ev["commission"] == "apex" and evr["commission"] == "R" and "commission" in A.UNCONFIRMED
    # Lucid specs are untouched (delegated to R) even right after an Apex walk
    ts, cal2 = rand_trades(11, ndays=140)
    P2 = port(ts, cal2)
    before = F.evaluate_funded(P2, "flex", micros=20, policy=500)
    A.evaluate_funded(P2, micros=20, policy=500)
    assert F.evaluate_funded(P2, "flex", micros=20, policy=500) == before == A.evaluate_funded(P2, "flex", micros=20, policy=500)
    # an exception inside a walk still restores R's cost function
    class Boom(A.DaySrc):
        def _bd(self, i, cap):
            raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        Boom(P, None, 100, True, (3.98, 1.04)).get(0, 170, 0.0, 5.0)
    assert F.cost is E.cost


# ---------------------------------------------------------------- five accounts copying one account

def test_five_accounts_identical_copies_are_one_bet_times_five():
    ts, cal = clean_trades(7, ndays=130, scale=2.5)
    P = port(ts, cal)
    plan = dict(P=P, micros=40, rules={"day_take": 1500}, policy=500, strategy="open_dir", inputs={"tgt_r": 0.67}, both_sides=False)
    one = A.evaluate_funded(P, micros=40, rules={"day_take": 1500}, policy=500, strategy="open_dir", inputs={"tgt_r": 0.67}, both_sides=False)
    m = one["pess"]
    assert 0 < m["p_pay_60"] < 1 and 0 < m["p_bust_any"] < 1                 # not a degenerate case
    five = A.five_accounts(plan)
    assert five["n_accounts"] == 5 and five["identical"] is True and five["model"] == "pess" and five["starts"] == ["fresh"] * 5
    assert five["e_total_40"] == pytest.approx(5 * m["e_net_40"]) and five["e_total_60"] == pytest.approx(5 * m["e_net_60"])
    for k in ("20", "40", "60"):                                             # copies: at least one pays <=> all pay <=> the one pays
        assert five[f"p_any_payout_{k}"] == five[f"p_all_payout_{k}"] == m[f"p_pay_{k}"]
    assert five["p_all_bust"] == five["p_any_bust"] == m["p_bust_any"] and five["p_all_bust_pre_first"] == m["p_bust_pre_first"]
    assert five["single"] == {"fresh": m} and "NO diversification" in five["note"] and five["n"] == m["n"]
    assert five["noncompliant"] == one["noncompliant"] and five["flags"] == one["flags"] and five["compliance"] == one["compliance"]
    # both consistency readings
    alt = one["cons_alt"]["pess"]
    assert five["cons_base"] == "cycle" and five["cons_alt"]["cons_base"] == "balance"
    assert five["cons_alt"]["e_total_40"] == pytest.approx(5 * alt["e_net_40"]) and five["cons_alt"]["p_all_bust"] == alt["p_bust_any"]
    # the same from a finished single-account result, and for another number of copies
    d = A.five_accounts(one)
    for k in ("e_total_40", "e_total_60", "p_any_payout_40", "p_all_payout_40", "p_all_bust", "p_all_bust_pre_first"):
        assert d[k] == pytest.approx(five[k]), k
    assert d["identical"] is True and d["cons_alt"]["e_total_40"] == pytest.approx(five["cons_alt"]["e_total_40"]) and d["noncompliant"] == one["noncompliant"]
    assert A.five_accounts(plan, n=3)["e_total_40"] == pytest.approx(3 * m["e_net_40"])
    # from trade rows (port built inside; the row checks ride on the Port)
    t5 = A.five_accounts(dict(trades=ts, micros=40, rules={"day_take": 1500}, policy=500, both_sides=False, end=cal[-1]))
    assert t5["compliance"]["stop_5x_target"] == "ok" and t5["n_accounts"] == 5
    with pytest.raises(ValueError):
        A.five_accounts({"micros": 10})
    with pytest.raises(ValueError):
        A.five_accounts({**plan, "starts": ["fresh"] * 4})
    with pytest.raises(ValueError):
        A.five_accounts({**plan, "firm": "flex"})


def test_five_accounts_with_different_balances_share_the_same_trades():
    ts, cal = clean_trades(7, ndays=130, scale=2.5)
    P = port(ts, cal)
    starts = ["fresh", "fresh", "plus3000", "plus7600", A.Start(7600.0, full=True, peak=9000.0)]
    plan = dict(P=P, micros=40, rules={"day_take": 1500}, policy=500, both_sides=False, starts=starts)
    five = A.five_accounts(plan)
    assert five["identical"] is False and five["starts"] == ["fresh", "fresh", "plus3000", "plus7600", "profit+7600_custom"]
    singles = [A.evaluate_funded(P, micros=40, rules={"day_take": 1500}, policy=500, both_sides=False, start=s, models=("pess",))["pess"]
               for s in starts]
    # $ add up account by account; probabilities do NOT multiply (same trades): any >= the best single, all-bust <= the safest single
    assert five["e_total_40"] == pytest.approx(sum(m["e_net_40"] for m in singles))
    assert five["e_total_60"] == pytest.approx(sum(m["e_net_60"] for m in singles))
    assert max(m["p_pay_40"] for m in singles) <= five["p_any_payout_40"] + 1e-12
    assert five["p_all_payout_40"] <= min(m["p_pay_40"] for m in singles) + 1e-12
    assert five["p_all_bust"] <= min(m["p_bust_any"] for m in singles) + 1e-12 <= five["p_any_bust"] + 2e-12
    indep = 1.0
    for m in singles:
        indep *= m["p_bust_any"]
    assert five["p_all_bust"] >= indep - 1e-12                               # far above what five INDEPENDENT accounts would give
    assert set(five["single"]) == {"fresh", "plus3000", "plus7600", "profit+7600_custom"} and five["single"]["fresh"] == singles[0]
    # brute force of the joint definition on the attempt tuples
    src = A.day_src(S300, P, {"day_take": 1500}, 40)
    life = [A.lifecycle(S300, src, 500, 60, "pess", s) for s in starts]
    n = len(life[0])
    assert five["p_all_bust"] == sum(all(a[i][0] > 0 for a in life) for i in range(n)) / n
    assert five["p_any_payout_40"] == sum(any(a[i][1] and a[i][1][0][0] <= 40 for a in life) for i in range(n)) / n
    assert five["e_total_40"] == pytest.approx(sum(sum(p[2] for a in life for p in a[i][1] if p[0] <= 40) for i in range(n)) / n)


# ---------------------------------------------------------------- the Legacy 300K evaluation (documented, not simulated)

def test_eval300_values_match_the_homebase_rule_file():
    ev = A.EVAL300
    assert (ev["start_balance"], ev["target"], ev["mll"], ev["cap"], ev["dll"], ev["min_days"]) == (300000.0, 20000.0, 7500.0, 350, 0.0, 7)
    assert (ev["price_month"], ev["price_month_coupon"], ev["pa_fee_lifetime"]) == (797.0, 79.70, 300.0) and "CONFLICT" in ev["status"]
    rid, r = E.firm_rules(ev["homebase_rule_id"])                           # read-only: the account holder's words
    assert (r["account_size"], r["eval_target"], r["trailing_mll"], r["cap_micros"]) == (300000, 20000, 7500, 350)
    assert r["confirmed"] is False and r["eval_min_days"] == 1               # != the help centre's 7 days / intraday trail: flagged


def test_compute_window_wait():
    ET = E.ET
    slept = []
    at = lambda y, m, d, h, mi: dt.datetime(y, m, d, h, mi, tzinfo=ET)
    assert A.compute_window_wait(at(2026, 9, 28, 9, 17), slept.append) == 0.0 and not slept          # Monday, before
    assert A.compute_window_wait(at(2026, 9, 26, 9, 25), slept.append) == 0.0 and not slept          # Saturday
    assert A.compute_window_wait(at(2026, 9, 28, 9, 36), slept.append) == 0.0 and not slept
    assert A.compute_window_wait(at(2026, 10, 1, 8, 20), slept.append) == 0.0 and not slept          # Thursday 08:20: no NFP window
    s = A.compute_window_wait(at(2026, 9, 28, 9, 18), slept.append)
    assert abs(s - (18 * 60 + 5)) < 1e-6 and slept == [s]
    s = A.compute_window_wait(at(2026, 10, 2, 8, 15), slept.append)                                  # Fri 2026-10-02 NFP 08:15-08:50
    assert abs(s - (35 * 60 + 5)) < 1e-6
    s = A.compute_window_wait(at(2026, 10, 2, 8, 49), slept.append)
    assert abs(s - 65) < 1e-6
    assert A.compute_window_wait(at(2026, 10, 2, 8, 50), slept.append) == 0.0
    s = A.compute_window_wait(at(2026, 10, 2, 9, 20), slept.append)
    assert abs(s - (16 * 60 + 5)) < 1e-6
    assert A.compute_window_wait(at(2026, 10, 9, 8, 20), slept.append) == 0.0                        # another Friday


def test_does_not_shadow_or_write_into_R():
    # checked in a fresh interpreter (inside a shared pytest process other modules also touch sys.path)
    import subprocess
    code = ("import sys; from pathlib import Path; sys.path.insert(0, %r); import apex300 as A; "
            "assert sys.dont_write_bytecode is True; "
            "assert Path(A.E.__file__).resolve().parent == A.R and Path(A.F.__file__).resolve().parent == A.R; "
            "assert sys.path.index(str(A.R)) > sys.path.index(%r) and sys.path.index(str(A.REPO)) > sys.path.index(%r); "
            "print('ok')") % (str(L), str(L), str(L))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(L))
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    assert Path(E.__file__).resolve().parent == A.R and Path(F.__file__).resolve().parent == A.R
    assert not (A.R / "__pycache__").exists()
