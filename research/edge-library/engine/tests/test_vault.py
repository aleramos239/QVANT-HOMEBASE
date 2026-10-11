"""VAULT: the `vault_break` entry (families/vault.py), written test-first from Conti's vault break (video A0G14JYYVTk, strategy 1).

THE RULE UNDER TEST (New York time, 30-minute bars):
    reference = the open of the 01:00 minute bar; A = the mean of the last 15 daily ATR(14) values; noise_up = reference + k x A (fixed)
    LONG      = a 30-minute bar closes strictly above noise_up AND above the VWAP from 01:00 -> market at the next bar's open
    window    = the bar that closes at 11:00 is the first that may trade, the one that closes at 15:00 the last; flat 15:30
    up to 3 trades a DAY, one at a time; after an exit the next close that still qualifies trades again
Synthetic days with EXACT numbers cover each behaviour; the real BUILD days check the invariants. No net, win rate or profit factor is read.
"""
import datetime as dt

import pytest

import families
import l2sim as S
from families import blocks as B
from families import noise as NB
from families import vault as VT
from test_blocks import D, days_of, minute_tape, ns, real_days

V = 40
P0 = 15000.0
# stop 75 points, target 40 (the video's $1,500 and $800 on one NQ)
BASE = {"hold_to": "day", "tf": "30", "sess": "nyam", "stop_mode": "pts", "stop_val": 75.0, "tgt_r": 40.0 / 75.0, "k": 0.3, "dir": "long"}


def sec(h, m=0):
    return h * 3600 + m * 60


def rows(ranges):
    return [{"date": (D - dt.timedelta(days=len(ranges) - i)).isoformat(), "h": 15000.0 + r, "l": 15000.0, "c": 15050.0, "contract": "NQM3"}
            for i, r in enumerate(ranges)]


DAILY = rows([100.0] * 40)                                          # every ATR(14) = 100 -> A = 100 -> noise_up = 15030 with k 0.3


def q(n, px):
    return [(px, px, px, px, V)] * n


def day(buckets, start=sec(10, 30)):
    """00:00 .. 15:59: quiet at 15000 until `start`, then one 30-minute bucket per entry of `buckets`: a number = the bucket sits at that
    price (its first minute moves there from the last close); a list of 30 minute bars = that bucket as written. Then quiet to the end."""
    b = q(start // 60, P0)
    last = P0
    for x in buckets:
        if isinstance(x, list):
            b += x
        else:
            b += [(last, max(last, x), min(last, x), x, V)] + q(29, x)
        last = b[-1][3]
    return b + q(960 - len(b), last)


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def run(params, bars, daily=DAILY, cls=None):
    st = (cls or VT.VaultBreak)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00", D), daily=daily, on_error="raise")
    return st, res


def decisions(params, bars, daily=DAILY):
    log = []

    class Spy(VT.VaultBreak):
        def _mkt(self, ctx, side, **kw):
            o = super()._mkt(ctx, side, **kw)
            log.append((sec_of(ctx), side, o is not None))
            return o

    run(params, bars, daily, Spy)
    return log


# ---- the band ------------------------------------------------------------------------------------------------------------------------------------

def wilder(rs):
    a = sum(rs[:14]) / 14.0
    out = [a]
    for x in rs[14:]:
        a = (a * 13.0 + x) / 14.0
        out.append(a)
    return out


def test_a_is_the_mean_of_the_last_15_daily_atr14_values_and_the_band_is_k_times_it():
    rs = [100.0] * 26 + [200.0] * 14                                # the last ATR(14) alone is much higher than the 15-session mean
    atrs = wilder(rs[1:])                                           # the first row has no bar before it: 39 true ranges
    a15 = sum(atrs[-15:]) / 15.0
    assert atrs[-1] > a15 + 10
    st, _ = run({}, day([P0]), daily=rows(rs))
    assert st.up == pytest.approx(P0 + 0.3 * a15) and st.ref == P0
    st, _ = run({"k": 0.5}, day([P0]))
    assert st.up == pytest.approx(15050.0)
    assert run({}, day([15100.0]), daily=rows([100.0] * 28))[1].trades == []      # 28 daily bars: no A, no trade


def test_a_close_above_the_band_and_the_vwap_buys_and_a_close_on_the_band_does_not():
    assert decisions({}, day([15030.0])) == []                      # ON the band
    assert decisions({}, day([15030.25])) == [(sec(11), "long", True)]
    assert not any(took for _, _, took in decisions({}, day([14900.0])))        # long only (the sheet's dir): a short is never taken


# ---- the window ----------------------------------------------------------------------------------------------------------------------------------

def test_the_bar_that_closes_at_11_00_is_the_first_that_may_trade():
    early = day([15060.0], start=sec(9, 30))                        # above the band from 09:30 on
    assert [d[0] for d in decisions({"max_tr": 1}, early)] == [sec(11)]
    at_1030 = day([15060.0, P0], start=sec(10))                     # above it only in the bar that closes at 10:30, back under by 11:00
    assert decisions({}, at_1030) == []


def test_the_bar_that_closes_at_15_00_is_the_last_and_a_trade_is_flat_at_15_30():
    late = day([15060.0], start=sec(15))                            # the first qualifying close is the one at 15:30: outside
    assert decisions({}, late) == []
    last = day([15060.0], start=sec(14, 30))                        # ... and here the one at 15:00
    assert [d[0] for d in decisions({"max_tr": 1}, last)] == [sec(15)]
    st, res = run({"max_tr": 1}, last)
    t = res.trades[0]
    assert t["exit_reason"] == "time" and t["exit_ms"] == ns("15:30") // 1_000_000


# ---- up to three trades a day ----------------------------------------------------------------------------------------------------------------------

def test_after_an_exit_the_next_close_that_still_qualifies_trades_again_three_times_at_most():
    climb = [15040.0, 15090.0, 15140.0, 15190.0, 15240.0, 15290.0]   # every bucket 50 points up: each trade hits its 40-point target
    got = decisions({}, day(climb))
    assert [d[0] for d in got] == [sec(11), sec(11, 30), sec(12)]   # three, then no more
    st, res = run({}, day(climb))
    assert len(res.trades) == 3 and all(t["exit_reason"] == "tp" for t in res.trades)
    assert all(t["tp"] - t["entry_price"] == pytest.approx(40.0) and t["entry_price"] - t["sl"] == pytest.approx(75.0) for t in res.trades)
    assert len(decisions({"max_tr": 1}, day(climb))) == 1


def test_one_position_at_a_time_and_no_new_trade_while_the_close_is_under_the_band():
    hold = [15040.0, 15050.0, 15055.0]                              # the first trade stays open (no target, no stop): nothing new
    assert [d[0] for d in decisions({}, day(hold))] == [sec(11)]
    out_and_back = [15040.0, 15090.0, 15010.0, 15010.0, 15060.0]    # target hit, a second trade, stopped; two closes under the band; above again
    assert [d[0] for d in decisions({}, day(out_and_back))] == [sec(11), sec(11, 30), sec(13)]


def test_only_the_nyam_pass_trades_and_its_window_holds_the_11_00_close():
    st = VT.VaultBreak({**BASE})
    assert st.fam_filter(["asia", "london", "pre", "nyam", "mid", "pm"]) == ["nyam"]
    assert st.fam_sessions() == {"nyam": (sec(11) - 1, sec(15, 30))}
    assert st.p["anchor"] == "globex" and st.p["max_tr"] == 3


# ---- real BUILD days ---------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES"])
def test_real_build_days_hold_the_window_the_day_cap_and_the_flat_time(root):
    real_days()
    days = days_of(root, 8)
    spec = (VT.VaultBreak, {**BASE})
    out = S.run_many([spec], root=root, days=days, period="build", workers=1, on_error="raise")
    again = S.run_many([spec], root=root, days=days, period="build", workers=1, on_error="raise")
    assert out[0]["trades"] == again[0]["trades"] and out[0]["skipped_by_error"] == 0
    per_day = {}
    for t in out[0]["trades"]:
        d = S._date(t["date"])
        es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
        assert t["side"] == "long" and sec(11) <= es <= sec(15) + 120, (t["date"], es)
        assert t["exit_ms"] <= S.et_ns(d, "15:30") // 1_000_000 + 60_000
        per_day[t["date"]] = per_day.get(t["date"], 0) + 1
    assert all(n <= 3 for n in per_day.values())


def test_the_registry_holds_vault_break_and_noise_band_is_untouched():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["vault_break"]
    assert cls is VT.VaultBreak and issubclass(cls, NB.NoiseBand) and cls.FEATURES == ()
    assert families.MODULE_OF["vault_break"] == "vault" and "vault_break" in B.BASES and "vault_break" in B.WRAPPED
    assert NB.NoiseBand.DEFAULTS == {"k": 0.3, "anchor": "rth", "max_tr": 3} and NB.NoiseBand.SCREEN_TFS == ("1", "5", "15", "30")
