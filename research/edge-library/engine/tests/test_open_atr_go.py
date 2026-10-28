"""OPEN ATR GO: the `open_atr_go` entry (families/open_atr_go.py), written from its rule.

THE RULE UNDER TEST: reference = the open of the 09:30 ET minute bar; A = the Template's ATR(14) of the idea's own tf bars; the FIRST tf close
at least k x A away from the reference gives the signal (above = long, below = short), one signal a day. Synthetic minute days; no result is read.
"""
import l2sim as S
from families import open_atr_go as OA
from test_noise import DAILY, bar, day, flat, run, sec, sec_of

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "k": 1.0}


class Sig(OA.OpenAtrGo):
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append((sec_of(ctx), "long" if self.go > 0 else "short"))


def signals(params, bars):
    cls = type("Sig", (Sig,), {"seen": []})
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    from test_noise import tape_of
    S.run_session(st, tape_of(bars), daily=DAILY, on_error="raise")
    return st, list(cls.seen)


def ramp(n, step, start=15000.0):
    return [bar(start + i * step, start + (i + 1) * step) for i in range(n)]


def test_a_flat_morning_gives_no_signal():
    st, seen = signals({}, day(flat(60)))
    assert seen == [] and st.ref == 15000.0


def test_the_first_close_at_least_k_atr_from_the_open_is_followed_up_and_down():
    _, up = signals({}, day(flat(5) + ramp(30, 2.0)))
    _, dn = signals({}, day(flat(5) + ramp(30, -2.0)))
    assert len(up) == 1 and up[0][1] == "long"
    assert len(dn) == 1 and dn[0][1] == "short"
    assert up[0][0] == dn[0][0] and up[0][0] > sec(9, 35)


def test_only_the_first_move_of_the_day_is_taken():
    g = flat(5) + ramp(10, 3.0) + ramp(30, -6.0, 15030.0)          # up first, then a bigger move down through the open
    _, seen = signals({}, day(g))
    assert [s for _, s in seen] == ["long"]


def test_the_signal_is_a_close_not_a_wick_and_it_needs_k_times_the_atr():
    _, small = signals({"k": 1.0}, day(flat(5) + ramp(30, 2.0)))
    _, big = signals({"k": 4.0}, day(flat(5) + ramp(30, 2.0)))
    assert big and big[0][0] > small[0][0]


def test_the_vwap_version_waits_for_the_close_to_be_on_the_vwap_side():
    from families import open_atr_go_vwap as OV
    g = [(15000.0, 15100.0, 15000.0, 15040.0, 1000), (15040.0, 15060.0, 15040.0, 15060.0, 1)] + flat(20, 15060.0)
    _, plain = signals({}, day(g))
    cls = type("SigV", (OV.OpenAtrGoVwap,), {"seen": [], "fam_signal": Sig.fam_signal})
    st = cls({**BASE})
    st.ROLLS = frozenset()
    from test_noise import tape_of
    S.run_session(st, tape_of(day(g)), daily=DAILY, on_error="raise")
    assert [x[1] for x in plain] == ["long"] and [x[1] for x in cls.seen] == ["long"]
    assert cls.seen[0][0] == plain[0][0] + 60          # the first close (15040) is under the VWAP (15046.7): one minute later


def test_the_ema_version_needs_close_over_ema9_over_ema24():
    from families import open_atr_go_x as OX
    # flat 15000 all night, then a climb: EMA9 > EMA24 and the close above both -> long; a drop from a flat night -> short; EMAs flat = no stack
    cls = type("SigE", (OX.OpenAtrGoEma,), {"seen": [], "fam_signal": Sig.fam_signal})
    for bars, want in ((flat(5) + ramp(30, 2.0), ["long"]), (flat(5) + ramp(30, -2.0), ["short"])):
        cls.seen = []
        st = cls({**BASE, "tf": "5"})
        st.ROLLS = frozenset()
        from test_noise import tape_of
        S.run_session(st, tape_of(day(bars)), daily=DAILY, on_error="raise")
        assert [x[1] for x in cls.seen] == want
    assert cls({**BASE, "tf": "5"}).spans_used() == (9, 24)


def test_the_combined_family_needs_both_conditions():
    from families import open_atr_go_xx as XX
    c = XX.OpenAtrGoGvwapEma({**BASE, "tf": "5"})
    c.C, c.E = [100.0], {9: 99.0, 24: 98.0}
    c.ln = type("L", (), {"value": lambda self: 99.5})()              # long: close > EMA9 > EMA24 and close > VWAP
    assert c.ok(1) and not c.ok(-1)
    c.ln = type("L", (), {"value": lambda self: 100.5})()             # close under the VWAP: no long
    assert not c.ok(1)
    c.ln, c.E = type("L", (), {"value": lambda self: 99.5})(), {9: 98.0, 24: 99.0}   # EMAs not stacked: no long
    assert not c.ok(1)
