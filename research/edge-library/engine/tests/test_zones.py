"""ZONE BLOCKS: engine/zones.py and their glue in families/blocks.py -- premium / discount (pdz), OTE (ote), the 15- and 60-minute trend
(htf15, htf60) and SMT (smt: NQ against ES). First-guess definitions of 2026-10-06 (the module docstring of zones.py).

A synthetic Globex day with EXACT numbers (19:58 ET the evening before .. 11:00): flat 15000 until the leg, then an UP leg (low 14900 at
02:00, high 15100 at 07:00) or the mirror DOWN leg, then a flat price from 09:30 -- the decision's close. The flat bars carry a tick of range, so the extremes are 15100.25 and 14899.75: R = 200.5, midpoint 15000, the OTE zone of the
up leg 14941.86 .. 14975.94, of the down leg 15024.06 .. 15058.15.
(i) each block's verdict at the thresholds and in both directions; (ii) the trend blocks against an independent loop on random days;
(iii) SMT on hand-made 5-minute bars of two markets; (iv) NO LOOK-AHEAD: prints (and the partner's bars) after the decision change nothing;
(v) the markets the blocks run on and the caches they ask for. No net, win rate or profit factor is read.
"""
import numpy as np
import pytest

import l2sim as S
import levels as LV
import zones as Z
from families import blocks as B
import run_menus as RM
from test_blocks import D, QUIET, W, days_of, minute_tape, ns, real_days
from test_liq import PREV, TICK, daily, flatg


class Ask(B.Blocks, S.Template):
    """Records allowed(long) and allowed(short) at the first decision of the session (and at every one after it)."""
    DEFAULTS = {"go": "long"}
    SCHEMA = {"go": ("choice", ("long", "short"))}
    SCREEN_TFS = ("1", "5")
    FEATURES = ()
    asked: list = []

    def fam_signal(self, ctx):
        type(self).asked.append(((ctx.now_ns - ns("00:00")) // S.NS, self.allowed("long"), self.allowed("short")))


def run(params, bars, root="NQ", tape=None, rolls=()):
    cls = type("A", (Ask,), {"asked": []})
    st = cls({"hold_to": "day", **QUIET, "tf": "5", "sess": "nyam", **params})
    st.ROLLS = frozenset(rolls)
    if tape is None:
        t = minute_tape(bars, "19:58", PREV)
        tape = S.Tape(root, D, "NQM3", t.ts, t.px, t.size)
    S.run_session(st, tape, daily=daily(), on_error="raise")
    return cls.asked


def first(params, bars, **kw):
    got = run(params, bars, **kw)
    assert got
    return got[0][1], got[0][2]                                       # (long allowed, short allowed) at the first decision


def leg_day(px, up=True, g=None):
    """19:58 .. 09:30 with the leg of the module docstring, then G (default: 60 flat minutes at `px`)."""
    a, b = (14900.0, 15100.0) if up else (15100.0, 14900.0)
    bars = flatg(242, 15000.0) + flatg(120, 15000.0)                  # 19:58 .. 01:59
    bars += [(15000.0, 15000.25, a, a, 40)] if up else [(15000.0, a, 14999.75, a, 40)]          # 02:00: the first extreme
    bars += flatg(299, a)                                             # 02:01 .. 06:59
    bars += [(a, b, a, b, 40)] if up else [(a, a, b, b, 40)]          # 07:00: the second extreme
    bars += flatg(149, b)                                             # 07:01 .. 09:29
    assert len(bars) == 812
    return bars + (g if g is not None else flatg(60, px))


# ---- (i) premium / discount -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("up", [True, False])
def test_pdz_buys_the_discount_and_sells_the_premium_and_the_midpoint_has_no_signal(up):
    assert first({"f_pdz": "with"}, leg_day(15050.0, up)) == (False, True)            # premium: a short is cheap here
    assert first({"f_pdz": "with"}, leg_day(14950.0, up)) == (True, False)            # discount
    assert first({"f_pdz": "against"}, leg_day(15050.0, up)) == (True, False)
    assert first({"f_pdz": "against"}, leg_day(14950.0, up)) == (False, True)
    assert first({"f_pdz": "with"}, leg_day(15000.0, up)) == (False, False)           # exactly the midpoint
    assert first({"f_pdz": "against"}, leg_day(15000.0, up)) == (False, False)


def test_pdz_needs_a_range_of_one_atr_and_reads_only_the_minutes_since_midnight():
    flat = flatg(812 + 60, 15000.0)
    assert first({"f_pdz": "with"}, flat) == (False, False)                           # the range is 0.5 points: smaller than an ATR
    # the evening before 00:00 is not part of the range: a spike at 20:00 changes nothing
    bars = leg_day(15050.0)
    bars[130] = (15000.0, 16000.0, 14000.0, 15000.0, 40)
    assert first({"f_pdz": "with"}, bars) == first({"f_pdz": "with"}, leg_day(15050.0)) == (False, True)


# ---- OTE ------------------------------------------------------------------------------------------------------------------------------------

def test_ote_is_the_62_to_79_percent_retracement_zone_of_a_leg_that_points_the_trades_way():
    for px, inside in ((14960.0, True), (14942.0, True), (14975.75, True), (14941.75, False), (14976.0, False), (15050.0, False)):
        assert first({"f_ote": "in"}, leg_day(px, up=True)) == (inside, False), px
        assert first({"f_ote": "out"}, leg_day(px, up=True)) == (not inside, False), px           # a short has no UP leg: no signal either way
    for px, inside in ((15040.0, True), (15024.25, True), (15058.0, True), (15024.0, False), (15058.25, False), (14950.0, False)):
        assert first({"f_ote": "in"}, leg_day(px, up=False)) == (False, inside), px
        assert first({"f_ote": "out"}, leg_day(px, up=False)) == (False, not inside), px


def test_ote_has_no_signal_without_a_leg():
    assert first({"f_ote": "in"}, flatg(812 + 60, 15000.0)) == (False, False)
    assert first({"f_ote": "out"}, flatg(812 + 60, 15000.0)) == (False, False)
    one = flatg(812 + 60, 15000.0)
    one[663] = (15000.0, 15100.0, 14900.0, 15000.0, 40)                               # 07:00: ONE minute holds both extremes: no leg
    assert first({"f_ote": "in"}, one) == first({"f_ote": "out"}, one) == (False, False)


# ---- (ii) the higher-timeframe trend vs an independent loop ---------------------------------------------------------------------------------

def walk_day(seed, drift):
    rng = np.random.default_rng(seed)
    c = 15000.0 + np.cumsum(rng.normal(drift, 1.2, 812 + 60)).round(2)
    c = np.round(c / TICK) * TICK
    o = np.concatenate(([15000.0], c[:-1]))
    return [(float(a), float(max(a, b) + TICK), float(min(a, b) - TICK), float(b), 40) for a, b in zip(o, c)], c


def expected_trend(closes, mins, n, now_min):
    """The sign of (last closed big close - EMA), from the minute closes (index 0 = 19:58): the loop, no shared code. now_min = minutes since 00:00."""
    off = 2 * 60 + 0                                                    # index 0 is 19:58 = -242 min from 00:00
    minute_of = lambda i: i - 242
    buckets = {}
    for i, px in enumerate(closes):
        m = minute_of(i)
        if m < 0 or m >= now_min:
            continue
        k = m // mins
        if (k + 1) * mins <= now_min:
            buckets[k] = px
    seq = [buckets[k] for k in sorted(buckets)]
    if len(seq) < n:
        return None
    e = seq[0]
    for x in seq[1:]:
        e += 2 / (n + 1) * (x - e)
    return None if seq[-1] == e else (1 if seq[-1] > e else -1)


@pytest.mark.parametrize("blk,mins,n", [("htf15", 15, 20), ("htf60", 60, 8)])
def test_the_trend_blocks_match_a_loop_on_random_days_and_use_closed_bars_only(blk, mins, n):
    seen = set()
    for seed, drift in ((1, 0.05), (2, -0.05), (3, 0.0), (4, 0.08), (5, -0.08), (6, 0.02)):
        bars, closes = walk_day(seed, drift)
        for mode in ("with", "against"):
            got = run({f"f_{blk}": mode}, bars)
            for sec, long_ok, short_ok in got[:6]:
                want = expected_trend(closes, mins, n, sec // 60)
                exp = (False, False) if want is None else ((want == 1) == (mode == "with"), (want == -1) == (mode == "with"))
                assert (long_ok, short_ok) == exp, (blk, seed, mode, sec)
                seen.add(want)
    assert {1, -1} <= seen                                              # both trends were met


def test_the_trend_blocks_need_enough_bars_and_a_close_off_the_line():
    assert first({"f_htf60": "with"}, flatg(812 + 60, 15000.0)) == (False, False)      # a flat day: the close IS the EMA
    run_ = run({"f_htf60": "with", "sess": "asia"}, flatg(812 + 60, 15000.0))          # asia decisions at 00:05 ...: fewer than 8 hours of bars
    assert run_ and all(not a and not b for _, a, b in run_)


# ---- (iii) SMT -----------------------------------------------------------------------------------------------------------------------------

def nq_tape(spike=None):
    """A flat NQ day; `spike` = (minute index, high, low) of one minute inside the window of the first decision (09:05 .. 09:35)."""
    bars = flatg(812 + 60, 15000.0)
    if spike:
        i, h, l = spike
        bars[i] = (15000.0, h, l, 15000.0, 40)
    t = minute_tape(bars, "19:58", PREV)
    return S.Tape("NQ", D, "NQM3", t.ts, t.px, t.size)


SPIKE_MIN = 812 - 20                                                    # 09:10: inside the last 6 5-minute bars of the 09:35 decision


def partner(monkeypatch, tape, hi=None, lo=None, root="ES", after=None):
    """The partner's 5-minute bars = a FLAT day's bars with a new high `hi` / new low `lo` at 09:10, and `after` = (high) on every bar from 09:40 on."""
    end, h, l = LV.session_arrays(nq_tape())
    h, l = h.copy(), l.copy()
    k = int(np.searchsorted(end, ns("09:10") + 300 * S.NS))
    if hi:
        h[k] = hi
    if lo:
        l[k] = lo
    if after:
        h[end > ns("09:40")] = after
    monkeypatch.setattr(LV, "session_bars", lambda r, iso, tf=LV.SW_TF: (end, h, l) if r == root else None)


def test_smt_is_a_divergence_at_a_new_extreme_of_exactly_one_market(monkeypatch):
    spike_hi, spike_lo = (SPIKE_MIN, 15100.0, 15000.0 - TICK), (SPIKE_MIN, 15000.0 + TICK, 14900.0)
    for tape_args, es, side in (((spike_hi, dict(), "bear")), ((spike_lo, dict(), "bull")),
                                ((None, dict(hi=15100.0), "bear")), ((None, dict(lo=14900.0), "bull"))):
        tape = nq_tape(tape_args)
        partner(monkeypatch, tape, **es)
        long_a, short_a = first({"f_smt": "agree"}, None, tape=tape)
        long_d, short_d = first({"f_smt": "disagree"}, None, tape=tape)
        assert (long_a, short_a, long_d, short_d) == ((False, True, True, False) if side == "bear" else (True, False, False, True)), (tape_args, es)
    tape = nq_tape(spike_hi)                                            # both made a new high: no divergence
    partner(monkeypatch, tape, hi=15100.0)
    assert first({"f_smt": "agree"}, None, tape=tape) == first({"f_smt": "disagree"}, None, tape=tape) == (False, False)
    tape = nq_tape(spike_hi)                                            # NQ a new high, ES a new low: bear AND bull at once: no signal
    partner(monkeypatch, tape, lo=14900.0)
    assert first({"f_smt": "agree"}, None, tape=tape) == (False, False)
    tape = nq_tape()                                                    # nothing new in either
    partner(monkeypatch, tape)
    assert first({"f_smt": "agree"}, None, tape=tape) == (False, False)


def test_smt_works_the_other_way_round_for_es_and_has_no_signal_for_gc_or_without_the_partner(monkeypatch):
    t = minute_tape(flatg(812 + 60, 15000.0), "19:58", PREV)
    tape = S.Tape("ES", D, "ESM3", t.ts, t.px, t.size)
    partner(monkeypatch, tape, hi=15100.0, root="NQ")                   # the partner of ES is NQ: it made the new high, ES did not
    assert first({"f_smt": "agree"}, None, tape=tape) == (False, True)
    tape = S.Tape("GC", D, "GCM3", t.ts, t.px, t.size)
    assert first({"f_smt": "agree"}, None, tape=tape) == (False, False)
    monkeypatch.setattr(LV, "session_bars", lambda r, iso, tf=LV.SW_TF: None)
    assert first({"f_smt": "agree"}, None, tape=nq_tape(SPIKE_MIN and (SPIKE_MIN, 15100.0, 14999.75))) == (False, False)


# ---- (iv) no look-ahead ------------------------------------------------------------------------------------------------------------------

def test_nothing_after_the_decision_changes_it(monkeypatch):
    for params, make in (({"f_pdz": "with"}, lambda: leg_day(15050.0)), ({"f_ote": "in"}, lambda: leg_day(14960.0)),
                         ({"f_htf15": "with"}, lambda: walk_day(1, 0.05)[0]), ({"f_htf60": "against"}, lambda: walk_day(4, 0.08)[0])):
        a = make()
        b = list(a)
        for k in range(812 + 12, len(b)):                               # from 09:42 on: wild prints
            b[k] = (15005.0, 16500.0, 13000.0, 15005.0, 40) if k % 2 else (15005.0, 15010.0, 12000.0, 12500.0, 40)
        assert run(params, a)[0] == run(params, b)[0], params
    tape = nq_tape((SPIKE_MIN, 15100.0, 14999.75))
    partner(monkeypatch, tape)
    one = first({"f_smt": "agree"}, None, tape=tape)
    partner(monkeypatch, tape, after=20000.0)                           # the partner prints a huge high after 09:40: unknown at 09:35
    assert first({"f_smt": "agree"}, None, tape=tape) == one == (False, True)


# ---- (v) markets and caches ---------------------------------------------------------------------------------------------------------------

def test_prep_roots_and_markets():
    assert Z.prep_roots("NQ", "liq", None) == ["NQ"] and Z.prep_roots("ES", "orb", ("swept", "with")) == ["ES"]
    assert Z.prep_roots("NQ", "orb", ("smt", "agree")) == ["NQ", "ES"] and Z.prep_roots("ES", "orb", ("smt", "agree")) == ["ES", "NQ"]
    assert Z.prep_roots("NQ", "orb", ("channel", "with")) == [] and Z.prep_roots("NQ", "orb", None) == []
    assert B.BLOCK_MARKETS == {"smt": ("NQ", "ES")}
    assert {"pdz", "ote", "htf15", "htf60", "smt"} <= set(B.FILTERS)
    for blk in ("pdz", "ote", "htf15", "htf60", "smt"):
        assert all((blk, s) in B.PLAIN for s in B.FILTERS[blk]) and B.Blocks.DEFAULTS[f"f_{blk}"] == "off"


# ---- (vi) real days: the same trades at 1 and 8 workers ----------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_zone_blocks(root):
    real_days()
    days = days_of(root)
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0, "n": 10}
    specs = [(B.WRAPPED["donchian"], {**hd, "sess": sess, f"f_{blk}": mode})
             for sess in ("london", "nyam") for blk, modes in (("pdz", ("with", "against")), ("ote", ("in", "out")), ("htf15", ("with", "against")),
                                                              ("htf60", ("with", "against")), ("smt", ("agree", "disagree")))
             for mode in modes if not (blk == "smt" and root == "GC")]
    a = S.run_many(specs, days=days, root=root, workers=1)
    b = S.run_many(specs, days=days, root=root, workers=W)
    seen = {}
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        k = next(k for k in p if k.startswith("f_"))
        seen[k] = seen.get(k, 0) + len(x["trades"])
    assert all(v > 0 for v in seen.values()), seen                                    # every block let some trades through
    assert RM.hold_checks(a, root) == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
