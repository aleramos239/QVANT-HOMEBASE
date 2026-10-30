"""brk100 (families/brk100.py): six break families, each gate on exact synthetic days. No net or win rate read."""
import l2sim as S
from families import blocks as B
from families import brk100 as K
from test_noise import DAILY, bar, day, flat, tape_of

BASE = {"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "exit_bars": 3}


def sides(name, params, bars, daily=DAILY, **base):
    st = B.WRAPPED[name]({**BASE, **base, **params})
    st.ROLLS = frozenset()
    return [t["side"] for t in S.run_session(st, tape_of(bars), daily=daily, on_error="raise").trades]


def ramp(n, step, start=15000.0):
    return [bar(start + i * step, start + (i + 1) * step) for i in range(n)]


def rows(ranges, closes=None):
    out = [{**r, "h": 15000.0 + g, "c": 15000.0 + g / 2 if closes is None else closes[i]} for i, (r, g) in enumerate(zip(DAILY, ranges))]
    return out


def test_day_cond_nr_inside_outside():
    d = rows([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 60.0])
    assert K.day_cond(d, "nr7") and K.day_cond(d, "nr4")
    assert not K.day_cond(rows([100.0] * 6 + [150.0]), "nr7")
    assert not K.day_cond(rows([100.0] * 3), "nr7")                              # too few days
    assert K.day_cond(d, "inside") and not K.day_cond(d, "outside")             # same low, lower high = inside
    assert K.day_cond(rows([100.0, 140.0]), "outside") is False                 # same low: not outside (needs a lower low too)


def test_pd_cond_bracket_trades_only_on_the_condition():
    up = day(ramp(40, 4.0))
    assert sides("pd_cond_bracket", {"cond": "nr7"}, up, rows([100.0] * 24 + [60.0])) == ["long"]
    assert sides("pd_cond_bracket", {"cond": "nr7"}, up, rows([100.0] * 24 + [150.0])) == []
    assert sides("pd_cond_bracket", {"cond": "inside"}, up, rows([100.0] * 24 + [150.0])) == []


def test_nd_bracket_reads_the_last_n_days():
    old = rows([100.0] * 25)
    old[-10]["h"] = 15500.0                                                       # a high 10 days back
    up = day(ramp(40, 4.0))                                                       # reaches 15160
    assert sides("nd_bracket", {"n_d": 5}, up, old) == ["long"]
    assert sides("nd_bracket", {"n_d": 20}, up, old) == []
    assert sides("nd_bracket", {"n_d": 5}, up, old[:3]) == []                     # too few days


def test_orb_cond_gapout_and_inside():
    up = day(ramp(60, 3.0))                                                       # opens 15000, range break up after 10:00
    wide = rows([100.0] * 24 + [60.0])
    assert sides("orb_cond", {"cond": "inside"}, up, wide) == ["long"]
    assert sides("orb_cond", {"cond": "inside"}, up, rows([100.0] * 24 + [150.0])) == []
    assert sides("orb_cond", {"cond": "gapout"}, up, rows([100.0] * 25)) == []    # opens 15000 inside 15000 .. 15100
    assert sides("orb_cond", {"cond": "gapout"}, up, rows([-50.0] * 25)) == ["long"]    # high 14950: the open is above the range


def test_on_narrow_bracket_needs_a_quiet_overnight():
    brk = ramp(40, 3.0)
    quiet = day(brk)
    loud = day(brk, head=[bar(15000.0 + (i % 2) * 80, 15000.0 + ((i + 1) % 2) * 80) for i in range(570)])
    assert sides("on_narrow_bracket", {"k": 0.5}, quiet) == ["long"]
    assert sides("on_narrow_bracket", {"k": 0.5}, loud) == []


def test_orb_dtrend_takes_only_the_trend_side():
    down, up = day(ramp(60, -3.0)), day(ramp(60, 3.0))
    rising = rows([100.0] * 25, closes=[14000.0 + i for i in range(25)])         # prior close far above its mean
    falling = rows([100.0] * 25, closes=[16000.0 - i for i in range(25)])
    assert sides("orb_dtrend", {"n_d": 20}, up, rising) == ["long"] and sides("orb_dtrend", {"n_d": 20}, down, rising) == []
    assert sides("orb_dtrend", {"n_d": 20}, down, falling) == ["short"] and sides("orb_dtrend", {"n_d": 20}, up, falling) == []
    assert sides("orb_dtrend", {"n_d": 20}, up, rows([100.0] * 25)) == []         # equal closes: no trend, no trade


def test_atr_contract_break_needs_the_coil():
    noisy = [bar(15000.0 + (i % 2) * 10, 15000.0 + ((i + 1) % 2) * 10) for i in range(510)]
    coil = flat(60)
    pre = noisy + coil
    assert len(pre) == 570
    brk = ramp(10, 3.0)
    assert sides("atr_contract_break", {"k": 0.6, "n": 12}, day(brk, head=pre)) == ["long"]
    assert sides("atr_contract_break", {"k": 0.6, "n": 12}, day(brk, head=noisy + noisy[:60])) == []        # no coil: no trade
