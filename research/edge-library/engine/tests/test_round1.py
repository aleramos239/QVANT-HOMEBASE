"""EDGE_SPEC "STAGE 2b -- NEW-IDEA ROUND 1": the seven round1 families (engine/families/round1.py).

For every family: (i) the entry logic on small synthetic bars, (ii) NO LOOK-AHEAD -- garbage after a cut changes no signal
and no entry before it, entries are at the next bar's open or later, yesterday's value area reads yesterday's 09:30-16:00
prints only, the VWAP reads bars up to the signal bar, late_mom's signal price is strictly before its entry -- (iii)
identical trades at 1 and 8 workers (real BUILD days), (iv) the max-trades and stop-after-2-losses rules.
The real-day tests compare trades by fingerprint and assert counts only: no net, win rate or profit factor is printed."""
import datetime as dt
import hashlib
import json
import os

import numpy as np
import pytest

import families
import l2sim as S
import library as LB
import run_menus as RM
from families import round1 as R1

D = dt.date(2023, 3, 14)                            # a BUILD weekday (EDT), not a roll day
PREV = "2023-03-13"
DAILY = [{"date": PREV, "h": 15100.0, "l": 14900.0, "c": 15000.0, "contract": "NQM3"}]
DAYS = list(RM.SMOKE_DAYS)
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
WIDE = {"stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
NAMES = ["vwap_trend_pull", "va_reclaim", "orb_confirm", "late_mom", "open_fade", "vol_spike_break", "straddle_tight_0830",
         "straddle_tight_0930", "straddle_tight_1000"]


def real_days():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def ns(hms, d=D):
    return S.et_ns(d, hms)


def hms(ms):
    return dt.datetime.fromtimestamp(ms / 1000, S.ET).strftime("%H:%M:%S")


def minute_tape(bars, start="09:00", d=D, root="NQ", contract="NQM3"):
    """One (o, h, l, c, v) per minute from `start` -> 4 prints per minute at :00 (o), :15, :30 (the low then the high for
    an up bar, the high then the low for a down bar) and :45 (c), each of size v / 4."""
    ts, px, sz = [], [], []
    t0 = ns(start, d)
    for i, (o, h, l, c, v) in enumerate(bars):
        mid = (l, h) if c >= o else (h, l)
        for k, p in enumerate((o, mid[0], mid[1], c)):
            ts.append(t0 + i * 60 * S.NS + k * 15 * S.NS)
            px.append(p)
            sz.append(v // 4)
    return S.Tape(root, d, contract, np.array(ts, np.int64), np.array(px, float), np.array(sz, np.int64))


def path(closes, o0, v=40, vols=None):
    """Bars from a list of closes: each bar opens at the previous close, high / low = max / min(open, close)."""
    out, o = [], o0
    for i, c in enumerate(closes):
        out.append((o, max(o, c), min(o, c), c, v if vols is None else vols[i]))
        o = c
    return out


def spy(cls):
    """A subclass that logs every entry decision: ('mkt' | 'arm', decision ns, sides, reference prices, placed orders)."""
    class Spy(cls):
        log: list = []

        def _mkt(self, ctx, side, **kw):
            o = super()._mkt(ctx, side, **kw)
            type(self).log.append(("mkt", ctx.now_ns, side, kw.get("ref", self.C[-1]), None if o is None else (o.sl, o.tp)))
            return o

        def _arm(self, ctx, legs, **kw):
            out = super()._arm(ctx, legs, **kw)
            type(self).log.append(("arm", ctx.now_ns, tuple(x[0] for x in legs), tuple(x[1] for x in legs),
                                   tuple((o.price, o.sl, o.tp) for o in out)))
            return out
    Spy.log = []
    return Spy


def play(cls, params, tape, daily=DAILY, **kw):
    """One synthetic session through one instance (hold_to day) -> (trades, the Spy log)."""
    sp = spy(cls)
    st = sp({"hold_to": "day", **params})
    res = S.run_session(st, tape, daily=list(daily), on_error="raise", **kw)
    return res.trades, list(sp.log), st


def ident(t):
    return (t["side"], t["entry_ms"], t["entry_price"], t["sl"], t["tp"])


def sig(trades):
    """Fingerprint of a trade list: every field of every trade, in order (compared, never printed)."""
    return hashlib.blake2b(json.dumps(trades, sort_keys=True, default=str).encode(), digest_size=12).hexdigest()


# ---- the registry = the written round --------------------------------------------------------------------------------------

def test_the_registry_holds_the_seven_families_as_written():
    assert families.ERRORS == {}
    assert RM.group_families("round1") == sorted(NAMES)
    lib = {n: families.library(n) for n in NAMES}
    cls = {n: families.REGISTRY[n][0] for n in NAMES}
    assert all(lb["roots"] == ("NQ", "ES", "GC") and not lb["l2"] and not lb["weak"] and lb["complexity"] >= 1 for lb in lib.values())
    assert [v["x"] for v in lib["vwap_trend_pull"]["variants"]] == [0.05, 0.10, 0.20]
    assert [v["d_atr"] for v in lib["va_reclaim"]["variants"]] == [0.0, 0.25, 0.5]
    assert [(v["or_min"], v["dir"]) for v in lib["orb_confirm"]["variants"]] == [(m, d) for m in ("15", "30", "60") for d in ("long", "short")]
    assert [(v["sig"], v["thr"]) for v in lib["late_mom"]["variants"]] == [(s, t) for s in ("10:00", "12:00", "15:30") for t in (0.0, 0.25, 0.5)]
    assert [v["k"] for v in lib["open_fade"]["variants"]] == [0.5, 1.0, 1.5]
    assert [v["m"] for v in lib["vol_spike_break"]["variants"]] == [2.0, 3.0, 4.0]
    assert {n: cls[n].SCREEN_TFS for n in NAMES[:6]} == {
        "vwap_trend_pull": ("1", "5", "15", "30"), "va_reclaim": ("1", "5", "15", "30"), "orb_confirm": ("1", "5", "15"),
        "late_mom": ("30",), "open_fade": ("1", "5"), "vol_spike_break": ("1", "5", "15", "30")}
    # limits per day, windows
    d = {n: cls[n].defaults() for n in NAMES}
    assert [d[n]["max_tr"] for n in NAMES] == [4, 2, 1, 1, 3, 2, 1, 1, 1] and d["vwap_trend_pull"]["max_loss"] == 2
    assert (R1.VwapTrendPull.T0, R1.VwapTrendPull.T1) == (S._sec("10:30"), S._sec("15:30"))
    assert (R1.LateMom.AT_S, R1.LateMom.FLAT_S) == (S._sec("15:30"), S._sec("15:58")) and R1.VolSpikeBreak.N == 20
    # orb_confirm: long-only and short-only are MIRROR units
    assert lib["orb_confirm"]["mirror"] == "dir" and families.MIRROR["orb_confirm"] == "dir"
    assert all(lib[n]["mirror"] is None for n in NAMES if n != "orb_confirm")
    # the rationale is the spec's plain reason
    for n, words in (("vwap_trend_pull", "dips get bought"), ("va_reclaim", "traps the late side"), ("orb_confirm", "shows acceptance"),
                     ("late_mom", "last half hour"), ("open_fade", "overshoots"), ("vol_spike_break", "real participation"),
                     ("straddle_tight_0930", "tight bracket catches the burst")):
        assert words in lib[n]["rationale"]
    # time-fired: late_mom and the three straddle_tight entries (one instance, own null through shift_seed)
    assert [n for n in NAMES if RM.is_time_fired(cls[n])] == ["late_mom", "straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000"]


def test_the_sessions_each_family_runs_under_hold_to_day():
    def passes(name, tf):
        return [p.get("sess") for _, p in RM.cell_specs(families.unit_grid(name, "NQ", tf)[0])]
    assert passes("vwap_trend_pull", "5") == ["nyam", "mid", "pm"] == passes("orb_confirm", "5")
    assert passes("open_fade", "1") == ["nyam"]
    assert passes("va_reclaim", "15") == list(RM.DAY_PASSES) == passes("vol_spike_break", "30")
    for name in ("late_mom", "straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000"):
        (c, p), = RM.cell_specs(families.unit_grid(name, "NQ", "30")[0])
        assert p["hold_to"] == "day" and c(p).sessions() == ["t"]
    assert all(p["hold_to"] == "day" for n in NAMES[:3] for _, p in RM.cell_specs(families.unit_grid(n, "NQ", "5")[0]))


def test_straddle_tight_times_offsets_stops_and_targets_are_scaled_per_root():
    assert R1.TIGHT_TIMES == ("08:30", "09:30", "10:00")
    want = {"08:30": ("08:29:59", "09:30:00"), "09:30": ("09:29:59", "11:00:00"), "10:00": ("09:59:59", "11:00:00")}
    for t, (at, flat) in want.items():
        c, inputs, both, _ = families.REGISTRY["straddle_tight_" + t.replace(":", "")]
        assert c is R1.StraddleTight and inputs == {"at": at, "flat": flat} and both is True
        assert c(inputs).p["cancel_min"] == 5 and c(inputs).fam_times() == [at, S._hms(S._sec(at) + 300)]
    assert R1.StraddleTight.OFF == {"NQ": (3.0, 5.0, 8.0), "ES": (0.75, 1.25, 2.0), "GC": (0.6, 1.0, 1.6)}
    assert R1.StraddleTight.STOP == {"NQ": (5.0, 8.0, 10.0), "ES": (1.25, 2.0, 2.5), "GC": (1.0, 1.6, 2.0)}
    for root, k in (("ES", 4.0), ("GC", 5.0)):      # "scaled the same way" as the offsets
        assert [x * k for x in R1.StraddleTight.OFF[root]] == pytest.approx(R1.StraddleTight.OFF["NQ"])
        assert [x * k for x in R1.StraddleTight.STOP[root]] == pytest.approx(R1.StraddleTight.STOP["NQ"])
    for root in ("NQ", "ES", "GC"):
        g = families.unit_grid("straddle_tight_0930", root, "30")
        assert len(g) == 27 and not any(c.get("info") for c in g)
        assert [c["exit"] for c in g[:9]] == [{"stop_mode": "pts", "stop_val": s, "tgt_r": r}
                                              for s in R1.StraddleTight.STOP[root] for r in (1.0, 2.0, 3.0)]
        assert [c["variant"] for c in g[::9]] == [{"off": "A"}, {"off": "B"}, {"off": "C"}]
        tick = S.SPECS[root][1]
        assert all(abs(v / tick - round(v / tick)) < 1e-9 for v in R1.StraddleTight.OFF[root] + R1.StraddleTight.STOP[root])


# ---- author cells: run, stored, never judged ---------------------------------------------------------------------------------

def test_author_cells_are_information_only_cells_of_the_grid():
    g = families.unit_grid("vwap_trend_pull", "NQ", "15")
    info = [c for c in g if c.get("info")]
    assert len(g) == 96 + 3 and len(info) == 3 and g[:96] == [c for c in g if not c.get("info")]
    assert all(c["exit"] == {"stop_mode": "pts", "stop_val": 80.0, "tgt_r": 0.0} and c["variant"]["auth"] == "on"
               and c["spec"][1]["auth"] == "on" and c["xi"] == 32 for c in info) and [c["vi"] for c in info] == [0, 1, 2]
    assert R1.VwapTrendPull.AUTH == {"stop": 80.0, "long": 40.0, "short": 50.0}
    for root, tf in (("NQ", "5"), ("ES", "15"), ("GC", "15"), ("NQ", "1"), ("NQ", "30")):      # the author cell is NQ 15-min only
        assert len(families.unit_grid("vwap_trend_pull", root, tf)) == 96
    g = families.unit_grid("orb_confirm", "ES", "5")
    info = [c for c in g if c.get("info")]
    assert len(g) == 192 + 6 and [c["exit"]["stop_mode"] for c in info] == ["struct"] * 6 and [c["vi"] for c in info] == list(range(6))
    g = families.unit_grid("open_fade", "GC", "1")
    info = [c for c in g if c.get("info")]
    assert len(g) == 96 + 24 and [{k: c["exit"][k] for k in ("stop_mode", "stop_val")} for c in info[:8]] == S.menu_stops("GC")
    assert all(c["spec"][1]["auth"] == "on" and c["exit"]["tgt_r"] == 0.0 for c in info)
    for name in ("va_reclaim", "late_mom", "vol_spike_break"):
        gg = families.unit_grid(name, "NQ", "30")
        assert not any(c.get("info") for c in gg) and len(gg) == 32 * len(families.library(name)["variants"])
    assert len({c["id"] for c in g}) == len(g)


def test_the_plateau_leaves_information_only_rows_out():
    rows = [{"id": f"c{i}", "vi": 0, "xi": i, "net": float(n), "trades": 10} for i, n in enumerate([5, -1, 7, 3, -2])]
    base = LB.plateau(rows)
    with_info = rows + [{"id": "author", "vi": 0, "xi": 5, "net": 1e9, "trades": 10, "info": True},
                        {"id": "author2", "vi": 0, "xi": 6, "net": -1e9, "trades": 10, "info": True}]
    pl = LB.plateau(with_info)
    assert pl["info"] == 2 and base["info"] == 0
    assert {k: v for k, v in pl.items() if k != "info"} == {k: v for k, v in base.items() if k != "info"}
    assert pl["cells"] == pl["cells_all"] == 5 and pl["best"] == "c2" and pl["member"] != "author"
    assert [r["id"] for r in LB.judged_rows(with_info)[0]] == ["c0", "c1", "c2", "c3", "c4"]
    only = LB.plateau([{"id": "a", "net": 5.0, "info": True}])
    assert only["pass"] is False and only["cells"] == 0 and only["info"] == 1 and only["member"] is None


# ---- the plan ---------------------------------------------------------------------------------------------------------------

def test_the_round1_plan_and_the_raised_cap(tmp_path):
    assert LB.CAPS["cells"] == 80000
    g = RM.group_plan("round1", ledger=tmp_path / "none.csv", runs_dir=tmp_path)
    by = {(r["family"], r["root"]): r for r in g["rows"]}
    assert len(by) == 27 and g["run_units"] == 63
    want = {"vwap_trend_pull": (4, 384), "va_reclaim": (4, 384), "orb_confirm": (3, 594), "late_mom": (1, 288), "open_fade": (2, 240),
            "vol_spike_break": (4, 384), "straddle_tight_0830": (1, 27), "straddle_tight_0930": (1, 27), "straddle_tight_1000": (1, 27)}
    for (name, root), r in by.items():
        extra = 3 if (name, root) == ("vwap_trend_pull", "NQ") else 0
        assert (r["units"], r["cells"]) == (want[name][0], want[name][1] + extra), (name, root)
        timed = name in ("late_mom",) or name.startswith("straddle_tight")
        assert r["null_cells"] == (2 * r["cells"] if timed else 0) and ("shift" in r["control"]) == timed
    assert g["candidate_cells"] == 7068 and g["info_cells"] == 201 and g["unit_null_cells"] == 2214
    assert g["c1_pools_needed"] == 12 and len(g["c1_pools_missing"]) == 12          # an empty ledger: every pool is still to run
    assert g["ledger_cells_used"] == RM.PAPER_CELLS == 824 and g["pending_cells"] == 7068 and g["fits"]
    real = RM.group_plan("round1")
    assert real["ledger_cells_used"] == LB.ledger_used()["cells"] + 824
    assert real["cells_after"] == real["ledger_cells_used"] + real["pending_cells"] <= LB.CAPS["cells"] and real["fits"]


# ---- N1 vwap_trend_pull ------------------------------------------------------------------------------------------------------

def n1_bars(sign=1, red=("10:35",), start="09:00", end="11:00", step=1.0, dip=0.5):
    """15000 flat until 09:30, then `sign` x step per minute; the minutes in `red` close `dip` against the trend."""
    n0 = (S._sec("09:30") - S._sec(start)) // 60
    n = (S._sec(end) - S._sec(start)) // 60
    reds = {(S._sec(t) - S._sec(start)) // 60 for t in red}
    closes, c = [], 15000.0
    for i in range(n):
        if i >= n0:
            c += -sign * dip if i in reds else sign * step
        closes.append(c)
    return path(closes, 15000.0)


def test_n1_the_first_candle_against_a_vwap_trend_is_bought_at_the_next_open():
    tape = minute_tape(n1_bars(1, red=("10:20", "10:35", "10:36")))
    tr, log, st = play(R1.VwapTrendPull, {"tf": "1", "sess": "nyam", "x": 0.10, **WIDE}, tape)
    # 10:20 is before the 10:30 window; 10:35 is the first down bar; 10:36 is the second in a row (not a first)
    assert [(k, hms(t // 10**6), s) for k, t, s, _, _ in log] == [("mkt", "10:36:00", "long")]
    assert len(tr) == 1 and tr[0]["side"] == "long" and hms(tr[0]["entry_ms"]) == "10:36:15"      # the next bar, after the latency
    # mirror
    tr, log, _ = play(R1.VwapTrendPull, {"tf": "1", "sess": "nyam", "x": 0.10, **WIDE}, minute_tape(n1_bars(-1, red=("10:35",))))
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("10:36:00", "short")] and tr[0]["side"] == "short"
    # the 60-minute move is 60 points = 0.40 %: X = 0.20 trades, a larger X does not
    assert len(play(R1.VwapTrendPull, {"tf": "1", "sess": "nyam", "x": 0.20, **WIDE}, tape)[0]) == 1
    assert play(R1.VwapTrendPull, {"tf": "1", "sess": "nyam", "x": 0.45, **WIDE}, tape)[1] == []


def test_n1_no_signal_without_the_state_and_none_outside_1030_1530():
    # a down bar in a down drift (close below a falling VWAP) is not a long pullback, and not a short trigger either
    tape = minute_tape(n1_bars(-1, red=()))
    assert play(R1.VwapTrendPull, {"tf": "1", "sess": "nyam", **WIDE}, tape)[1] == []
    # a down bar that closes above the VWAP and 0.27 % above the close an hour ago, but the VWAP is LOWER than 3 bars ago
    # (09:40-10:10 at 15060, then 25 minutes at 15020 pull the VWAP down; 10:35 gaps up on thin volume and closes down)
    bars = path([15000.0] * 40 + [15060.0] * 30 + [15020.0] * 25, 15000.0) + [(15070.0, 15070.0, 15040.0, 15040.0, 4)] \
        + path([15040.0] * 20, 15040.0)

    class Probe(R1.VwapTrendPull):
        seen: dict = {}

        def fam_update(self, ctx):
            super().fam_update(ctx)
            Probe.seen[R1.bar_end(self)] = (self.C[-1], self.O[-1], list(self.vwh[-4:]), self.c_at.get(R1.bar_end(self) - 3600), self.go)

    Probe.seen = {}
    S.run_session(Probe({"tf": "1", "sess": "nyam", "hold_to": "day", **WIDE}), minute_tape(bars), daily=DAILY, on_error="raise")
    c, o, vw, c60, go = Probe.seen[S._sec("10:36")]
    assert c < o and c > vw[-1] and (c / c60 - 1) * 100 >= 0.10 and vw[-1] < vw[0] and go == 0
    assert all(v[4] == 0 for v in Probe.seen.values())
    # entries only 10:30 .. 15:30: the same pullback at 15:40 gives nothing, at 15:25 it trades (pm instance)
    late = minute_tape(n1_bars(1, red=("15:25", "15:40"), start="09:00", end="16:00", step=0.25, dip=0.25))
    tr, log, _ = play(R1.VwapTrendPull, {"tf": "1", "sess": "pm", "x": 0.05, **WIDE}, late)
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("15:26:00", "long")] and len(tr) == 1
    assert hms(tr[0]["exit_ms"]) <= "15:58:00"


def saw(start="09:00", end="15:00", fall2=0.0):
    """An up-trend with a pullback every 6 minutes from 09:30: +5, +5, +5, +5, -2 (the first down bar), then +2 -- or, with
    fall2, a second down bar of that size (the bar the entry is filled in)."""
    n0 = (S._sec("09:30") - S._sec(start)) // 60
    n = (S._sec(end) - S._sec(start)) // 60
    closes, c = [], 15000.0
    for i in range(n):
        if i >= n0:
            k = (i - n0) % 6
            c += 5.0 if k < 4 else -2.0 if k == 4 else (-fall2 if fall2 else 2.0)
        closes.append(c)
    return path(closes, 15000.0)


def test_n1_max_four_trades_and_stop_after_two_losing_trades():
    base = {"tf": "1", "sess": "mid", "x": 0.05}
    # winners: the bar after the entry rallies -> a 3-point target fills; a new pullback every 6 minutes
    tape = minute_tape(saw())
    tr, log, _ = play(R1.VwapTrendPull, {**base, "stop_mode": "pts", "stop_val": 3.0, "tgt_r": 1.0}, tape)
    assert len(tr) == 4 and all(t["net"] > 0 and t["exit_reason"] == "tp" for t in tr) and len(log) == 4       # max 4 trades a day
    assert len(play(R1.VwapTrendPull, {**base, "stop_mode": "pts", "stop_val": 3.0, "tgt_r": 1.0, "max_tr": 9}, tape)[0]) == 9
    # losers: the entry bar falls 6 more points through a 3-point stop -> after the 2nd loss nothing more is taken
    tape = minute_tape(saw(fall2=6.0))
    tr, log, _ = play(R1.VwapTrendPull, {**base, "stop_mode": "pts", "stop_val": 3.0, "tgt_r": 1.0}, tape)
    assert len(tr) == 2 and all(t["net"] < 0 and t["exit_reason"] == "sl" for t in tr) and len(log) == 2
    more = play(R1.VwapTrendPull, {**base, "stop_mode": "pts", "stop_val": 3.0, "tgt_r": 1.0, "max_loss": 20}, tape)[0]
    assert len(more) == 4 and all(t["net"] < 0 for t in more)       # without the loss rule the max-4 rule is the next limit
    # a win does not count as a loss: one loser, then winners up to the cap of 4
    mixed = saw(fall2=6.0)[:(S._sec("11:06") - S._sec("09:00")) // 60]
    c0 = mixed[-1][3]
    tail = saw()[len(mixed):]
    shift = c0 - tail[0][0]
    mixed += [(o + shift, h + shift, l + shift, c + shift, v) for o, h, l, c, v in tail]
    tr = play(R1.VwapTrendPull, {**base, "stop_mode": "pts", "stop_val": 3.0, "tgt_r": 1.0}, minute_tape(mixed))[0]
    assert len(tr) == 4 and [t["net"] < 0 for t in tr] == [True, False, False, False]


def test_n1_the_vwap_is_the_0930_vwap_of_the_bars_up_to_the_signal_bar():
    rng = np.random.default_rng(3)
    closes = 15000.0 + np.cumsum(rng.choice([-0.5, 0.25, 0.5, 0.75], 150))
    vols = [int(v) * 4 for v in rng.integers(5, 60, 150)]
    bars = path(list(closes), 15000.0, vols=vols)
    tape = minute_tape(bars)

    class Probe(R1.VwapTrendPull):
        seen: list = []

        def fam_update(self, ctx):
            super().fam_update(ctx)
            if self.vwh:
                Probe.seen.append((R1.bar_end(self), self.vwh[-1], len(self.vwh)))

    Probe.seen = []
    S.run_session(Probe({"tf": "5", "sess": "nyam", "hold_to": "day", **WIDE}), tape, daily=DAILY, on_error="raise")
    assert len(Probe.seen) > 10 and Probe.seen[0][0] == S._sec("09:35")       # the first tf close after 09:30
    for end, vw, n in Probe.seen:
        k0, k1 = 30, (end - S._sec("09:00")) // 60                            # the 1-minute bars 09:30 .. the signal bar's last minute
        num = sum(b[4] * (b[1] + b[2] + b[3]) / 3.0 for b in bars[k0:k1])
        den = sum(b[4] for b in bars[k0:k1])
        assert vw == pytest.approx(num / den, abs=1e-9)
    assert [n for _, _, n in Probe.seen] == list(range(1, len(Probe.seen) + 1))


def test_n1_author_cell_stop_80_target_40_long_50_short():
    cell = {"stop_mode": "pts", "stop_val": 80.0, "tgt_r": 0.0, "auth": "on", "tf": "1", "sess": "nyam"}
    tr, log, _ = play(R1.VwapTrendPull, cell, minute_tape(n1_bars(1)))
    assert len(tr) == 1 and tr[0]["tp"] - tr[0]["entry_price"] == pytest.approx(40.0) and tr[0]["entry_price"] - tr[0]["sl"] == pytest.approx(80.0)
    tr, log, _ = play(R1.VwapTrendPull, cell, minute_tape(n1_bars(-1)))
    assert len(tr) == 1 and tr[0]["entry_price"] - tr[0]["tp"] == pytest.approx(50.0) and tr[0]["sl"] - tr[0]["entry_price"] == pytest.approx(80.0)


# ---- N2 va_reclaim -----------------------------------------------------------------------------------------------------------

def ticks(rows, d, root="NQ", contract="NQM3"):
    """[(hms, price, size)] -> a tape."""
    return S.Tape(root, d, contract, np.array([S.et_ns(d, t) for t, _, _ in rows], np.int64),
                  np.array([p for _, p, _ in rows], float), np.array([s for _, _, s in rows], np.int64))


def test_n2_value_area_is_70_percent_of_the_rth_volume_by_price_hand_computed():
    d = dt.date(2023, 3, 13)
    rth = [("09:30:00", 100.00, 10), ("10:00:00", 100.25, 30), ("11:00:00", 100.50, 25), ("12:00:00", 100.50, 15),
           ("13:00:00", 100.75, 15), ("15:59:59", 101.00, 5)]
    # 100 lots: the busiest row is 100.50 (40); below it 30, above it 15 -> add 100.25 -> 70 >= 70 % : VAL 100.25, VAH 100.50
    assert R1.value_area_of(ticks(rth, d)) == (100.25, 100.50)
    # prints outside 09:30-16:00 never count, whatever their size
    noisy = [("03:00:00", 90.0, 10_000), ("09:29:59", 95.0, 10_000)] + rth + [("16:00:00", 120.0, 10_000), ("16:30:00", 130.0, 10_000)]
    assert R1.value_area_of(ticks(noisy, d)) == (100.25, 100.50)
    # equal neighbours: both rows are added; a single price: VAL = VAH; no RTH print: None
    assert R1.value_area_of(ticks([("10:00:00", 99.75, 10), ("10:01:00", 100.0, 30), ("10:02:00", 100.25, 10)], d)) == (99.75, 100.25)
    assert R1.value_area_of(ticks([("10:00:00", 100.0, 7)], d)) == (100.0, 100.0)
    assert R1.value_area_of(ticks([("08:00:00", 100.0, 7)], d)) is None
    # ties for the busiest row: the lowest price; a row with no volume between two prices is a row like any other
    assert R1.value_area_of(ticks([("10:00:00", 100.0, 40), ("10:01:00", 101.0, 40), ("10:02:00", 100.25, 20)], d)) == (100.0, 101.0)
    assert R1.value_area_of(ticks([("10:00:00", 1900.0, 40), ("10:01:00", 1900.3, 30), ("10:02:00", 1899.9, 30)], d, "GC", "GCJ3")) \
        == (1899.9, 1900.0)


def n2_tape(closes, start="09:00"):
    return minute_tape(path(closes, closes[0]), start=start)


def test_n2_a_failed_poke_below_yesterdays_val_is_bought_and_above_vah_sold(monkeypatch):
    monkeypatch.setitem(R1._VA, ("NQ", PREV), (14990.0, 15010.0))
    inside = [15000.0] * 35
    # 09:35 trades down to 14984 (6 below VAL), 09:36 closes back at 14992 (> VAL) -> long at the 09:37 open
    closes = inside + [14984.0, 14992.0] + [14995.0] * 30
    tr, log, st = play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape(closes))
    assert st.va == (14990.0, 15010.0)
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:37:00", "long")] and hms(tr[0]["entry_ms"]) == "09:37:15"
    # the poke must reach D = d_atr x ATR14 below VAL: with a huge d_atr the same path gives nothing
    assert play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 9.0, **WIDE}, n2_tape(closes))[1] == []
    # a touch of VAL that does not trade below it is not a poke
    assert play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape(inside + [14990.0, 14995.0] + inside))[1] == []
    # mirror at VAH
    closes = inside + [15016.0, 15008.0] + [15005.0] * 30
    tr, log, _ = play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape(closes))
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:37:00", "short")] and tr[0]["side"] == "short"
    # a poke before the session, the close back inside it: the session instance takes it
    closes = [15000.0] * 20 + [14984.0] + [14986.0] * 14 + [14992.0] + [14995.0] * 30
    tr, log, _ = play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape(closes))
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:36:00", "long")]
    # one bar through the whole value area, closing inside: both sides at once -> no signal
    wide = path([15000.0] * 35, 15000.0) + [(15000.0, 15020.0, 14980.0, 15000.0, 40)] + path([15000.0] * 20, 15000.0)
    assert play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, minute_tape(wide))[1] == []


def test_n2_one_trade_per_side_per_day(monkeypatch):
    monkeypatch.setitem(R1._VA, ("NQ", PREV), (14990.0, 15010.0))
    one = [14984.0, 14992.0, 14995.0, 14995.0, 14995.0, 14995.0]                  # a poke below VAL and the close back above it
    two = [15016.0, 15008.0, 15005.0, 15005.0, 15005.0, 15005.0]                  # the mirror at VAH
    closes = [15000.0] * 35 + one + one + two + two + one + [15000.0] * 10
    cell = {"tf": "1", "sess": "nyam", "d_atr": 0.0, "stop_mode": "pts", "stop_val": 50.0, "tgt_r": 0.04}      # a 2-point target
    tr, log, _ = play(R1.VaReclaim, cell, n2_tape(closes))
    assert [t["side"] for t in tr] == ["long", "short"] and all(t["exit_reason"] == "tp" for t in tr)
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:37:00", "long"), ("09:49:00", "short")]


def test_n2_yesterdays_value_area_reads_only_yesterdays_rth_prints(monkeypatch):
    prev = dt.date(2023, 3, 13)
    y = [("03:00:00", 14000.0, 9000), ("09:30:00", 14990.0, 30), ("11:00:00", 15000.0, 40), ("15:00:00", 15010.0, 30),
         ("16:10:00", 16000.0, 9000)]
    asked = []

    def fake(d, root="NQ", **kw):
        asked.append(S._date(d).isoformat())
        assert S._date(d) == prev, "only the previous trade date's tape may be read"
        return ticks(y, prev)

    monkeypatch.setattr(S, "load_tape", fake)
    monkeypatch.setitem(R1._VA_FILE, "NQ", {})
    monkeypatch.delitem(R1._VA, ("NQ", PREV), raising=False)
    closes = [15000.0] * 35 + [14984.0, 14992.0] + [14995.0] * 30
    tr, log, st = play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape(closes))
    assert st.va == R1.value_area_of(ticks(y, prev)) == (14990.0, 15010.0) and asked == [PREV]
    assert [s for _, _, s, _, _ in log] == ["long"]
    # today's prints do not move it: a wildly different today, same value area (memoised: no second read)
    _, _, st2 = play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape([17000.0] * 80))
    assert st2.va == st.va and asked == [PREV]
    monkeypatch.delitem(R1._VA, ("NQ", PREV))
    # a contract-roll day: yesterday's prices are another contract -> no value area, no trade
    roll = [{**DAILY[0], "contract": "NQH3"}]
    tr, log, st3 = play(R1.VaReclaim, {"tf": "1", "sess": "nyam", "d_atr": 0.0, **WIDE}, n2_tape(closes), daily=roll)
    assert st3.va is None and log == [] and tr == [] and asked == [PREV]
    # a 2025+ date stays sealed
    monkeypatch.undo()
    with pytest.raises(S.HoldoutSealed):
        R1.value_area("NQ", "2025-01-02")


# ---- N3 orb_confirm ----------------------------------------------------------------------------------------------------------

def n3_bars(after, start="09:00"):
    """15000 before 09:30; the first 15 minutes range 14996 .. 15006 (close 15000); then the closes in `after`."""
    pre = path([15000.0] * 30, 15000.0)
    rng_ = path([15006.0, 14996.0] + [15000.0] * 13, 15000.0)
    return pre + rng_ + path(list(after), 15000.0)


def test_n3_a_bar_close_beyond_the_opening_range_is_followed_one_direction_one_trade():
    after = [15004.0, 15005.0, 15008.0, 15012.0, 15003.0, 15009.0] + [15009.0] * 20
    tape = minute_tape(n3_bars(after))
    base = {"tf": "1", "sess": "nyam", "or_min": "15", "stop_mode": "pts", "stop_val": 4.0, "tgt_r": 0.0}
    tr, log, st = play(R1.OrbConfirm, {**base, "dir": "long"}, tape)
    assert st.r == (15006.0, 14996.0)
    # 09:47 closes at 15008 > 15006 -> long at the 09:48 open; the stop-out at 15003 is not followed by a second trade
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:48:00", "long")]
    assert len(tr) == 1 and tr[0]["exit_reason"] == "sl" and hms(tr[0]["entry_ms"]) == "09:48:15"
    assert play(R1.OrbConfirm, {**base, "dir": "short"}, tape)[1] == []         # the short-only unit never buys
    # the mirror
    down = minute_tape(n3_bars([14998.0, 14994.0] + [14990.0] * 20))
    tr, log, _ = play(R1.OrbConfirm, {**base, "dir": "short"}, down)
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:47:00", "short")] and play(R1.OrbConfirm, {**base, "dir": "long"}, down)[1] == []
    # a close above the high made so far, INSIDE a longer range window, is not a signal: or_min 30 -> the range grows to 15012
    tr, log, st = play(R1.OrbConfirm, {**base, "dir": "long", "or_min": "30"}, tape)
    assert st.r == (15012.0, 14996.0) and log == []
    # the confirm bar is the tf bar: at tf 5 the 09:45-09:50 bar closes at 15003 (inside), the 09:50-09:55 bar at 15009
    tr, log, _ = play(R1.OrbConfirm, {**base, "dir": "long", "tf": "5", "stop_val": 50.0}, tape)
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:55:00", "long")]


def test_n3_author_cell_stop_at_the_other_side_of_the_range_and_flat_at_1530():
    n = (S._sec("16:00") - S._sec("09:45")) // 60
    tape = minute_tape(n3_bars([15008.0] + [15010.0] * (n - 1)))
    cell = {"tf": "1", "sess": "nyam", "or_min": "15", "dir": "long", "auth": "on", "stop_mode": "struct", "stop_val": 1.5, "tgt_r": 0.0}
    tr, log, _ = play(R1.OrbConfirm, cell, tape)
    assert len(tr) == 1 and hms(tr[0]["entry_ms"]) == "09:46:15" and tr[0]["tp"] is None
    slip = tr[0]["entry_price"] - 15008.0                                         # the bracket moves with the fill
    assert tr[0]["sl"] == pytest.approx(14996.0 + slip) and tr[0]["exit_reason"] == "time" and hms(tr[0]["exit_ms"]) == "15:30:00"
    # the menu cell of the same variant holds to 15:58
    tr2 = play(R1.OrbConfirm, {**cell, "auth": "off", "stop_mode": "pts", "stop_val": 400.0}, tape)[0]
    assert hms(tr2[0]["entry_ms"]) == "09:46:15" and hms(tr2[0]["exit_ms"]) == "15:58:00"
    # the author cell takes no entry from 15:30 on
    late = minute_tape(n3_bars([15000.0] * (n - 20) + [15008.0] * 20))
    assert play(R1.OrbConfirm, {**cell, "sess": "pm"}, late)[1] == []
    assert len(play(R1.OrbConfirm, {**cell, "sess": "pm", "auth": "off", "stop_mode": "pts", "stop_val": 40.0}, late)[1]) == 1


# ---- N4 late_mom -------------------------------------------------------------------------------------------------------------

def n4_tape(p10=15030.0, p12=14990.0, p1529=15020.0, after=14000.0):
    """prior close 15000 (DAILY). Prints every 15 s: p10 until 10:00, p12 until 12:00, p1529 until 15:30, `after` from 15:30:00."""
    ts = np.arange(ns("09:00"), ns("16:05"), 15 * S.NS, dtype=np.int64)
    px = np.full(len(ts), p10)
    px[ts >= ns("10:00")] = p12
    px[ts >= ns("12:00")] = p1529
    px[ts >= ns("15:30")] = after
    return S.Tape("NQ", D, "NQM3", ts, px, np.ones(len(ts), np.int64))


def test_n4_at_1530_trade_the_sign_of_the_signal_price_minus_the_prior_close():
    tape = n4_tape()
    for sig_t, side in (("10:00", "long"), ("12:00", "short"), ("15:30", "long")):
        tr, log, st = play(R1.LateMom, {"sig": sig_t, **WIDE}, tape)
        assert [(k, hms(t // 10**6), s) for k, t, s, _, _ in log] == [("mkt", "15:30:00", side)], sig_t
        assert len(tr) == 1 and tr[0]["side"] == side and "15:30:00" < hms(tr[0]["entry_ms"]) <= "15:30:15"
        assert tr[0]["exit_reason"] == "time" and hms(tr[0]["exit_ms"]) == "15:58:00"
    # the threshold: +30 points on 15000 = 0.20 %
    assert len(play(R1.LateMom, {"sig": "10:00", "thr": 0.0, **WIDE}, tape)[0]) == 1
    assert play(R1.LateMom, {"sig": "10:00", "thr": 0.25, **WIDE}, tape)[1] == []
    assert len(play(R1.LateMom, {"sig": "10:00", "thr": 0.25, **WIDE}, n4_tape(p10=15040.0))[0]) == 1
    # no move, no trade; a contract-roll day has no prior close -> no trade
    assert play(R1.LateMom, {"sig": "10:00", **WIDE}, n4_tape(p10=15000.0))[1] == []
    assert play(R1.LateMom, {"sig": "10:00", **WIDE}, tape, daily=[{**DAILY[0], "contract": "NQH3"}])[1] == []


def test_n4_the_signal_price_is_strictly_before_the_entry_time():
    # the 15:30 signal reads the 15:29 close (15020 > prior close): prints AT and after 15:30:00 are far below the prior
    # close and change nothing; the same holds for 10:00 and 12:00 (the bar that starts at the signal time is not read)
    for after in (14000.0, 16000.0):
        tr, log, st = play(R1.LateMom, {"sig": "15:30", **WIDE}, n4_tape(after=after))
        assert st.move()[0] == 15020.0 and [s for _, _, s, _, _ in log] == ["long"]
        assert tr[0]["entry_ms"] > ns("15:30") // 10**6 > (ns("15:29:45")) // 10**6
    st = play(R1.LateMom, {"sig": "10:00", **WIDE}, n4_tape(p10=15030.0, p12=14000.0))[2]
    assert st.move() == (15030.0, pytest.approx(0.2))
    st = play(R1.LateMom, {"sig": "12:00", **WIDE}, n4_tape(p12=14990.0, p1529=17000.0))[2]
    assert st.move()[0] == 14990.0


def test_n4_the_null_is_the_same_trade_with_a_seeded_random_direction():
    tape = n4_tape()
    sides = {}
    for seed in (1, 2, 3, 4, 5, 6, 7, 8):
        a = play(R1.LateMom, {"sig": "10:00", "shift_seed": seed, **WIDE}, tape)[0]
        b = play(R1.LateMom, {"sig": "12:00", "thr": 0.0, "shift_seed": seed, "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}, tape)[0]
        assert len(a) == len(b) == 1 and a[0]["side"] == b[0]["side"] and a[0]["entry_ms"] == b[0]["entry_ms"]      # same for every cell
        sides[seed] = a[0]["side"]
    assert set(sides.values()) == {"long", "short"}                                # it is a coin, not the signal
    real = play(R1.LateMom, {"sig": "10:00", **WIDE}, tape)[0]
    assert real[0]["entry_ms"] == play(R1.LateMom, {"sig": "10:00", "shift_seed": 1, **WIDE}, tape)[0][0]["entry_ms"]
    # the null trades the same days: the threshold still applies
    assert play(R1.LateMom, {"sig": "10:00", "thr": 0.25, "shift_seed": 1, **WIDE}, tape)[1] == []
    g = families.unit_grid("late_mom", "NQ", "30")
    sh = RM.shift_grid(g)
    assert len(sh) == 2 * len(g) == 576 and {c["spec"][1]["shift_seed"] for c in sh} == {1, 2}


# ---- N5 open_fade ------------------------------------------------------------------------------------------------------------

def n5_bars(after, start="06:00"):
    """Before 09:30 every minute cycles 15000 / 15008 / 15004: each 30-minute bar has range 8 and closes at 15004, so
    ATR30 = 8 and ref (the 09:29 close) = 15004. Then the closes in `after`."""
    n0 = (S._sec("09:30") - S._sec(start)) // 60
    pre = [(15004.0, 15008.0, 15000.0, 15004.0, 40)] * n0
    return pre + path(list(after), 15004.0)


def test_n5_atr30_is_the_templates_atr_at_tf_30():
    rng = np.random.default_rng(5)
    closes = 15000.0 + np.cumsum(rng.normal(0, 3.0, 606).round(0) * 0.25)
    tape = minute_tape(path(list(closes), 15000.0), start="00:00")

    class T30(S.Template):
        FEATURES = ()
        seen: list = []

        def fam_update(self, ctx):
            T30.seen.append((R1.bar_end(self), self.atr))

    class F(R1.OpenFade):
        seen: dict = {}

        def fam_update(self, ctx):
            super().fam_update(ctx)
            F.seen[R1.bar_end(self)] = self.a30.atr

    T30.seen, F.seen = [], {}
    S.run_session(T30({"tf": "30"}), tape, daily=DAILY, on_error="raise")
    S.run_session(F({"tf": "5", "sess": "nyam", "hold_to": "day"}), tape, daily=DAILY, on_error="raise")
    assert len(T30.seen) == 20
    for end, atr in T30.seen:
        assert F.seen[end] == pytest.approx(atr, abs=1e-12)
        assert F.seen[end + 300] == pytest.approx(atr, abs=1e-12)                 # between two 30-minute closes: the last completed bar


def test_n5_a_stretch_from_the_0929_close_that_stalls_is_faded_toward_it():
    base = {"tf": "1", "sess": "nyam", "k": 1.0, **WIDE}
    # ATR30 = 8, ref = 15004: 09:32 trades at 15013 (>= ref + 8); 09:34 closes below the 09:33 low -> short at the 09:35 open
    after = [15008.0, 15011.0, 15013.0, 15013.5, 15011.0] + [15010.0] * 20
    tr, log, st = play(R1.OpenFade, base, minute_tape(n5_bars(after), start="06:00"))
    assert st.ref == 15004.0 and st.a30.atr == pytest.approx(8.0)
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:35:00", "short")] and hms(tr[0]["entry_ms"]) == "09:35:15"
    # K = 1.5 needs 12 points: the same path never stretches that far
    assert play(R1.OpenFade, {**base, "k": 1.5}, minute_tape(n5_bars(after), start="06:00"))[1] == []
    assert len(play(R1.OpenFade, {**base, "k": 0.5}, minute_tape(n5_bars(after), start="06:00"))[1]) == 1
    # the mirror: a stretch below ref, then a bar closes above the prior bar's high -> long
    down = [15000.0, 14997.0, 14995.0, 14994.5, 14997.0] + [14998.0] * 20
    tr, log, _ = play(R1.OpenFade, base, minute_tape(n5_bars(down), start="06:00"))
    assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:35:00", "long")]
    # once price has traded back to ref the stretch is over: a later stall bar is no signal
    # (the bar that falls back to ref in one go is not faded either: the move toward ref is already done)
    back = [15008.0, 15011.0, 15013.0, 15013.5, 15013.75, 15014.0, 15004.0, 15008.0, 15009.0, 15007.0] + [15007.0] * 15
    tr, log, st = play(R1.OpenFade, base, minute_tape(n5_bars(back), start="06:00"))
    assert log == [] and st.up is False
    # a stall without a stretch is nothing
    assert play(R1.OpenFade, base, minute_tape(n5_bars([15006.0, 15009.0, 15007.0, 15005.0] + [15005.0] * 20), start="06:00"))[1] == []


def test_n5_max_three_trades_and_the_author_target_is_the_ref_price():
    leg = [15008.0, 15011.0, 15013.0, 15013.5, 15011.0, 15010.0, 15009.0]         # stretch + stall, every 7 minutes
    after = leg * 6 + [15009.0] * 20
    cell = {"tf": "1", "sess": "nyam", "k": 1.0, "stop_mode": "pts", "stop_val": 40.0, "tgt_r": 0.025}        # a 1-point target
    tr, log, _ = play(R1.OpenFade, cell, minute_tape(n5_bars(after), start="06:00"))
    assert len(tr) == 3 == len(log) and all(t["side"] == "short" and t["exit_reason"] == "tp" for t in tr)
    assert len(play(R1.OpenFade, {**cell, "max_tr": 9}, minute_tape(n5_bars(after), start="06:00"))[0]) == 6
    # author cell: the target is the ref price (moved by the entry slip, as every Template price target)
    one = [15008.0, 15011.0, 15013.0, 15013.5, 15011.0] + [15010.0] * 5 + [15003.0] * 10
    tr, log, st = play(R1.OpenFade, {"tf": "1", "sess": "nyam", "k": 1.0, "auth": "on", **WIDE}, minute_tape(n5_bars(one), start="06:00"))
    assert len(tr) == 1 and tr[0]["tp"] == pytest.approx(15004.0 + (tr[0]["entry_price"] - 15011.0)) and tr[0]["exit_reason"] == "tp"
    # only 09:30-11:00: the same stretch at 11:10 is not traded
    late = [15004.0] * 100 + leg + [15009.0] * 10
    assert play(R1.OpenFade, {**cell}, minute_tape(n5_bars(late), start="06:00"))[1] == []


# ---- N6 vol_spike_break ------------------------------------------------------------------------------------------------------

def n6_bars(events, n=60, v=40):
    """Flat 15000 .. 15004 bars of volume v; events = {minute index: (close, volume)}; later bars rest at the new level."""
    out, c = [], 15002.0
    for i in range(n):
        if i in events:
            c2, vol = events[i]
            out.append((c, max(c, c2), min(c, c2), c2, vol))
            c = c2
        else:
            out.append((c, c + 2.0, c - 2.0, c, v))
    return out


def test_n6_a_break_of_the_20_bar_range_on_a_volume_spike_is_followed():
    base = {"tf": "1", "sess": "nyam", **WIDE}
    # minute 40 (09:40): closes at 15010 (> the 20-bar high 15004) on volume 140 = 3.5 x the median 40
    tape = minute_tape(n6_bars({40: (15010.0, 140)}))
    for m, n in ((2.0, 1), (3.0, 1), (4.0, 0)):
        tr, log, _ = play(R1.VolSpikeBreak, {**base, "m": m}, tape)
        assert len(log) == n, m
        if n:
            assert [(hms(t // 10**6), s) for _, t, s, _, _ in log] == [("09:41:00", "long")] and hms(tr[0]["entry_ms"]) == "09:41:15"
    # the same break on normal volume, and a volume spike without a break: nothing
    assert play(R1.VolSpikeBreak, {**base, "m": 2.0}, minute_tape(n6_bars({40: (15010.0, 40)})))[1] == []
    assert play(R1.VolSpikeBreak, {**base, "m": 2.0}, minute_tape(n6_bars({40: (15003.0, 400)})))[1] == []
    # mirror
    tr, log, _ = play(R1.VolSpikeBreak, {**base, "m": 2.0}, minute_tape(n6_bars({40: (14994.0, 140)})))
    assert [s for _, _, s, _, _ in log] == ["short"]
    # the signal bar's own high and volume are not part of "the last 20 bars": a bar that makes the high and closes
    # at it IS a break; and 21 bars are needed -- a spike at bar 15 of the day gives nothing
    assert play(R1.VolSpikeBreak, {**base, "m": 2.0, "sess": "london"}, minute_tape(n6_bars({15: (15010.0, 400)}), start="03:00"))[1] == []
    assert len(play(R1.VolSpikeBreak, {**base, "m": 2.0, "sess": "london"}, minute_tape(n6_bars({25: (15010.0, 400)}), start="03:00"))[1]) == 1


def test_n6_max_two_trades_a_day():
    ev = {40: (15010.0, 200), 70: (15020.0, 200), 100: (15030.0, 200), 130: (15040.0, 200)}
    cell = {"tf": "1", "sess": "nyam", "m": 2.0, "stop_mode": "pts", "stop_val": 40.0, "tgt_r": 0.025}        # a 1-point target
    tape = minute_tape(n6_bars(ev, n=110))
    tr, log, _ = play(R1.VolSpikeBreak, cell, tape)
    assert len(tr) == 2 == len(log) and [hms(t // 10**6) for _, t, _, _, _ in log] == ["09:41:00", "10:11:00"]
    assert len(play(R1.VolSpikeBreak, {**cell, "max_tr": 5}, tape)[1]) == 3


# ---- N7 straddle_tight -------------------------------------------------------------------------------------------------------

def n7_tape(moves=(), root="NQ", base=15000.0, at="09:30", contract="NQM3", step=S.NS):
    """A print every second (`step` ns) from 2 h before `at` to 40 min after it, resting at `base`; a move (hms, price)
    sets every print from that time on."""
    a = S._sec(at)
    ts = np.arange(ns(S._hms(a - 7200)), ns(S._hms(a + 2400)), step, dtype=np.int64)
    px = np.full(len(ts), base)
    for t, p in moves:
        px[ts >= ns(t)] = p
    return S.Tape(root, D, contract, ts, px, np.ones(len(ts), np.int64))


def tight(name, off, stop, r, **kw):
    c, inputs, _, _ = families.REGISTRY[name]
    return c, {**inputs, "off": off, "stop_mode": "pts", "stop_val": stop, "tgt_r": r, **kw}


def test_n7_the_bracket_is_placed_one_second_before_the_time_around_the_last_print():
    c, p = tight("straddle_tight_0930", "B", 8.0, 2.0)
    # the burst starts at 09:30:00: +6 through the +5 leg
    tr, log, _ = play(c, p, n7_tape([("09:30:00", 15006.0), ("09:30:30", 15030.0)]))
    assert [(k, hms(t // 10**6), sides, px) for k, t, sides, px, _ in log] == [("arm", "09:29:59", ("long", "short"), (15005.0, 14995.0))]
    assert len(tr) == 1 and tr[0]["side"] == "long" and tr[0]["order_price"] == 15005.0 and tr[0]["oco"] is True
    assert hms(tr[0]["entry_ms"]) == "09:30:00"
    e = tr[0]["entry_price"]
    assert e - tr[0]["sl"] == pytest.approx(8.0) and tr[0]["tp"] - e == pytest.approx(16.0) and tr[0]["exit_reason"] == "tp"
    # the anchor is the last print BEFORE 09:29:59: a jump at 09:29:59 itself moves no leg; the bracket is live 85 ms
    # later, so the next print (09:29:59.5 on a half-second tape) fills the long leg -- before 09:30, session tag pre
    tr, log, _ = play(c, p, n7_tape([("09:29:59", 15007.0)], step=S.NS // 2))
    assert log[0][3] == (15005.0, 14995.0) and tr[0]["entry_ms"] == ns("09:29:59") // 10**6 + 500
    assert S.session_of(tr[0]["entry_ms"]) == "pre"
    # the short leg; the other leg is cancelled by the fill (one trade, no re-entry after the stop-out)
    tr, log, _ = play(c, p, n7_tape([("09:30:02", 14994.0), ("09:30:10", 15010.0), ("09:31:00", 15030.0)]))
    assert len(tr) == 1 and tr[0]["side"] == "short" and tr[0]["exit_reason"] == "sl" and len(log) == 1
    # offsets A / B / C and the three stops x three targets
    for off, pts in zip("ABC", (3.0, 5.0, 8.0)):
        for stop in (5.0, 8.0, 10.0):
            for r in (1.0, 2.0, 3.0):
                tr, log, _ = play(*tight("straddle_tight_0930", off, stop, r), n7_tape([("09:30:05", 15000.0 + pts + 0.25)]))
                assert log[0][3] == (15000.0 + pts, 15000.0 - pts)
                e = tr[0]["entry_price"]
                assert e - tr[0]["sl"] == pytest.approx(stop) and tr[0]["tp"] - e == pytest.approx(r * stop)


def test_n7_unfilled_legs_are_cancelled_after_five_minutes_and_each_time_has_its_own_entry():
    c, p = tight("straddle_tight_0930", "A", 5.0, 1.0)
    tr, log, _ = play(c, p, n7_tape([("09:34:50", 15004.0)]))                     # a fill 4 min 51 s after the bracket was placed
    assert len(tr) == 1 and hms(tr[0]["entry_ms"]) == "09:34:50"
    tr, log, _ = play(c, p, n7_tape([("09:35:05", 15020.0)]))                     # after the cancel: nothing
    assert tr == [] and len(log) == 1
    for name, at, armed in (("straddle_tight_0830", "08:30", "08:29:59"), ("straddle_tight_1000", "10:00", "09:59:59")):
        cc, pp = tight(name, "A", 5.0, 1.0)
        tr, log, _ = play(cc, pp, n7_tape([(at + ":01", 15004.0)], at=at))
        assert [hms(t // 10**6) for _, t, _, _, _ in log] == [armed] and len(tr) == 1 and hms(tr[0]["entry_ms"]) == at + ":01"
    # ES and GC: the scaled offsets and stops
    for root, base, contract, off, stop in (("ES", 4000.0, "ESM3", 1.25, 2.0), ("GC", 1900.0, "GCJ3", 1.0, 1.6)):
        cc, pp = tight("straddle_tight_0930", "B", stop, 3.0)
        daily = [{**DAILY[0], "contract": contract}]
        st = cc({"hold_to": "day", **pp})
        st.root = root
        res = S.run_session(st, n7_tape([("09:30:03", base + off + S.SPECS[root][1])], root=root, base=base, contract=contract),
                            daily=daily, on_error="raise")
        t, = res.trades
        assert t["order_price"] == pytest.approx(base + off) and t["entry_price"] - t["sl"] == pytest.approx(stop)
        assert t["tp"] - t["entry_price"] == pytest.approx(3.0 * stop)


def test_n7_the_null_fires_the_same_bracket_at_random_minutes():
    c, p = tight("straddle_tight_0930", "B", 8.0, 2.0)
    st = c({**p, "shift_seed": 1})
    ks = [st.shift_of(d) for d in DAYS]
    assert len(set(ks)) > 5 and all(-90 <= k <= 90 for k in ks)
    assert ks == [c({**p, "off": "C", "stop_val": 5.0, "shift_seed": 1}).shift_of(d) for d in DAYS]       # the same minutes for every cell
    assert ks != [c({**p, "shift_seed": 2}).shift_of(d) for d in DAYS]
    st.begin_day(D)
    a, b = st.S["t"]
    assert (a - (S._sec("09:30") - 1)) % 60 == 0 and b - a == S._sec("11:00") - S._sec("09:30") + 1 and st.fam_times()[1] == S._hms(a + 300)
    g = families.unit_grid("straddle_tight_0930", "NQ", "30")
    assert len(RM.shift_grid(g)) == 54


# ---- (ii) no look-ahead: garbage after a cut changes nothing decided before it ------------------------------------------------

def la_tape(seed=11):
    """A whole synthetic day 00:00-16:05, a print every 5 s: a random walk that trends up from 09:30, volume spikes."""
    rng = np.random.default_rng(seed)
    ts = np.arange(ns("00:00"), ns("16:05"), 5 * S.NS, dtype=np.int64)
    step = rng.choice([-0.5, -0.25, 0.0, 0.25, 0.5], len(ts))
    step[(ts >= ns("09:30")) & (ts < ns("12:30"))] += 0.06
    step[(ts >= ns("12:30")) & (ts < ns("14:30"))] -= 0.05
    px = np.round((15000.0 + np.cumsum(step)) / 0.25) * 0.25
    sz = rng.integers(1, 20, len(ts))
    spike = rng.random(len(ts)) < 0.01
    sz[spike] *= 60
    return S.Tape("NQ", D, "NQM3", ts, px, sz.astype(np.int64))


def la_specs():
    cell = {"stop_mode": "pts", "stop_val": 6.0, "tgt_r": 1.0}
    out = [(R1.VwapTrendPull, {"tf": tf, "sess": s, "x": 0.05, **cell}) for tf in ("1", "5") for s in ("nyam", "mid", "pm")]
    out += [(R1.VaReclaim, {"tf": tf, "sess": s, "d_atr": 0.25, **cell}) for tf in ("1", "15") for s in ("asia", "london", "nyam", "pm")]
    out += [(R1.OrbConfirm, {"tf": "5", "sess": s, "or_min": "30", "dir": d, **cell}) for s in ("nyam", "mid") for d in ("long", "short")]
    out += [(R1.OrbConfirm, {"tf": "1", "sess": "nyam", "or_min": "15", "dir": "long", "auth": "on", "stop_mode": "struct", "tgt_r": 0.0})]
    out += [(R1.LateMom, {"sig": s, **cell}) for s in ("10:00", "12:00", "15:30")]
    out += [(R1.OpenFade, {"tf": tf, "sess": "nyam", "k": 0.5, **cell}) for tf in ("1", "5")]
    out += [(R1.VolSpikeBreak, {"tf": tf, "sess": s, "m": 2.0, **cell}) for tf in ("1", "5") for s in ("london", "nyam", "mid", "pm")]
    for name in ("straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000"):
        c, inputs, _, _ = families.REGISTRY[name]
        out.append((c, {**inputs, "off": "A", "stop_mode": "pts", "stop_val": 5.0, "tgt_r": 1.0}))
    return out


def la_run(tape):
    out = []
    for cls, p in la_specs():
        tr, log, _ = play(cls, p, tape)
        out.append((cls.__name__, p, tr, log))
    return out


LA_CUTS = ("03:10", "08:29:59", "08:31", "09:29:59", "09:30", "09:31", "09:47", "10:00", "10:30", "10:31", "11:00", "11:59", "12:00", "12:44",
           "13:30", "14:17", "15:29", "15:30", "15:31", "15:45")


def test_garbage_after_a_cut_changes_no_signal_and_no_entry_before_it(monkeypatch):
    monkeypatch.setitem(R1._VA, ("NQ", PREV), (14996.0, 15004.0))
    tape = la_tape()
    real = la_run(tape)
    per = {}
    for name, p, tr, log in real:
        per[name] = per.get(name, 0) + len(log)
    assert all(per[c] >= 2 for c in ("VwapTrendPull", "VaReclaim", "OrbConfirm", "LateMom", "OpenFade", "VolSpikeBreak", "StraddleTight")), per
    assert sum(len(tr) for _, _, tr, _ in real) > 40
    rng = np.random.default_rng(7)
    rows = 0
    for cut in LA_CUTS:
        c = ns(cut)
        k = int(np.searchsorted(tape.ts, c))
        px, sz = tape.px.copy(), tape.size.copy()
        px[k:] = np.round(tape.px[k:] * rng.uniform(0.9, 1.1, len(px) - k) / 0.25) * 0.25
        sz[k:] = rng.integers(1, 5000, len(sz) - k)
        fake = la_run(S.Tape("NQ", D, "NQM3", tape.ts, px, sz))
        changed = 0
        for (name, p, tr, log), (_, _, tr2, log2) in zip(real, fake):
            # a decision AT the cut reads only prints before it (the bars that end at the cut, the last print before it)
            assert [x for x in log if x[1] <= c] == [x for x in log2 if x[1] <= c], (cut, name, p)
            assert [t for t in tr if t["exit_ms"] < c // 10**6] == [t for t in tr2 if t["exit_ms"] < c // 10**6], (cut, name, p)
            assert sorted(ident(t) for t in tr if t["entry_ms"] < c // 10**6) == sorted(ident(t) for t in tr2 if t["entry_ms"] < c // 10**6)
            rows += len([x for x in log if x[1] <= c])
            changed += tr != tr2
        assert changed > 0 or cut >= "15:45", cut                                 # the garbage really was replayed
    assert rows > 300


def test_entries_are_at_the_next_bar_open_or_later(monkeypatch):
    monkeypatch.setitem(R1._VA, ("NQ", PREV), (14996.0, 15004.0))
    tape = la_tape()
    n = 0
    for name, p, tr, log in la_run(tape):
        dec = sorted(x[1] for x in log)
        if name != "StraddleTight":                  # a market order at a bar close (late_mom: at 15:30:00)
            step = (int(p["tf"]) if name != "LateMom" else 1) * 60 * S.NS
            assert all(x[0] == "mkt" and (x[1] - ns("00:00")) % step == 0 for x in log), name
        for t in tr:
            e = t["entry_ms"] * 10**6
            last = max(x for x in dec if x <= e)     # the decision this entry came from
            k = int(np.searchsorted(tape.ts, last + 85 * 10**6))
            assert e >= last + 85 * 10**6 and e >= tape.ts[k], name                # never before the decision + the latency
            if name != "StraddleTight":
                assert e == tape.ts[k]               # the first print of the next bar after the latency
            n += 1
    assert n > 40


# ---- (iii) identical trades at 1 and 8 workers; counts on real BUILD days --------------------------------------------------------

def parity_specs():
    specs = []
    for name in NAMES:
        cls = families.REGISTRY[name][0]
        tf = "5" if "5" in cls.SCREEN_TFS else cls.SCREEN_TFS[0]
        g = families.unit_grid(name, "NQ", tf)
        cells = g[2::max(1, len(g) // 6)] + [c for c in g if c.get("info")][:2]
        for c in cells:
            specs += RM.cell_specs(c)
        if RM.is_time_fired(cls):
            for c in RM.shift_grid(cells[:3]):
                specs += RM.cell_specs(c)
    return specs


def test_identical_trades_at_1_and_8_workers():
    real_days()
    specs = parity_specs()
    a = S.run_many(specs, days=DAYS, workers=1)
    b = S.run_many(specs, days=DAYS, workers=W)
    assert len(specs) > 100 and a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == min(W, len(DAYS))
    n = {}
    for (cls, p), x, y in zip(specs, a, b):
        assert sig(x["trades"]) == sig(y["trades"]), (cls.__name__, p)             # every field of every trade, in order
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["skipped"] == y["skipped"]
        assert [e["reason"] for e in x["no_trade"]] == [e["reason"] for e in y["no_trade"]]
        n[cls.__name__] = n.get(cls.__name__, 0) + len(x["trades"])
        if cls is not R1.StraddleTight:
            assert x["both_sides_sessions"] == 0 and not any(t["oco"] for t in x["trades"])
    assert all(n[c] > 0 for c in ("VwapTrendPull", "VaReclaim", "OrbConfirm", "LateMom", "OpenFade", "VolSpikeBreak", "StraddleTight")), n


def test_real_days_limits_windows_and_the_flatten_counts_only():
    real_days()
    lim = {"vwap_trend_pull": 4, "va_reclaim": 2, "orb_confirm": 1, "late_mom": 1, "open_fade": 3, "vol_spike_break": 2,
           "straddle_tight_0830": 1, "straddle_tight_0930": 1, "straddle_tight_1000": 1}
    days = DAYS[:6]
    for name in NAMES:
        cls = families.REGISTRY[name][0]
        tf = "1" if "1" in cls.SCREEN_TFS else cls.SCREEN_TFS[0]
        g = families.unit_grid(name, "NQ", tf)
        cells = g[1::max(1, len(g) // 5)]
        res = RM.run_grid(cells, "NQ", features=None, workers=2, days=days)
        assert sum(r["skipped_by_error"] for r in res) == 0, name
        chk = RM.hold_checks(res, "NQ")
        assert chk == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}, (name, chk)
        win = R1.ENTRY_WINDOWS.get(name)
        total = 0
        for c, r in zip(cells, res):
            per = {}
            for t in r["trades"]:
                k = (t["date"], S.session_of(t["entry_ms"]) if not RM.is_time_fired(cls) else "t")
                per[k] = per.get(k, 0) + 1
                if win is not None:
                    assert win[0] <= RM._et_sec(t["entry_ms"]) <= win[1], (name, hms(t["entry_ms"]))
                if name == "orb_confirm":
                    assert t["side"] == c["variant"]["dir"]
                    assert RM._et_sec(t["entry_ms"]) >= R1.OPEN + int(c["variant"]["or_min"]) * 60
            assert max(per.values(), default=0) <= lim[name], (name, c["id"])       # max trades per session instance and day
            if name == "va_reclaim":                                               # one trade per side
                sides = {}
                for t in r["trades"]:
                    k = (t["date"], S.session_of(t["entry_ms"]), t["side"])
                    sides[k] = sides.get(k, 0) + 1
                assert max(sides.values(), default=0) == 1
            total += len(r["trades"])
        assert total > 0, name


def test_a_stored_unit_keeps_the_author_cells_flagged_and_out_of_the_plateau(tmp_path):
    real_days()
    out = RM.run_unit("vwap_trend_pull", "NQ", "15", workers=2, runs_dir=tmp_path / "runs", ledger=tmp_path / "ledger.csv",
                      log=tmp_path / "log.txt", days=DAYS[:3])
    assert [(o["key"], o["ok"], o["cells"]) for o in out] == [("vwap_trend_pull-NQ-tf15", True, 99)]
    u = LB.load_unit("vwap_trend_pull-NQ-tf15", tmp_path / "runs")
    cells = u["meta"]["cells"]
    assert [c.get("info", False) for c in cells] == [False] * 96 + [True] * 3
    assert LB.ledger_used(path=tmp_path / "ledger.csv")["cells"] == 99              # author cells are run: they count as candidate cells
    for sess in ("nyam", "mid", "pm"):
        table = LB.session_table(u, sess)
        assert [r["info"] for r in table] == [False] * 96 + [True] * 3
        pl = LB.plateau(table)
        assert pl["info"] == 3 and pl["cells_all"] == 96 and pl["cells"] + pl["dead"] + pl["duplicates"] == 96
        assert pl["member"] is None or not pl["member"].startswith("authon")
    # a mirror family's judged units still split by the axis, author cells included in neither count
    out = RM.run_unit("orb_confirm", "NQ", "15", workers=2, runs_dir=tmp_path / "runs", ledger=tmp_path / "ledger.csv",
                      log=tmp_path / "log.txt", days=DAYS[:3])
    u = LB.load_unit("orb_confirm-NQ-tf15", tmp_path / "runs")
    units = LB.plateau_units(u, "nyam")
    assert sorted(units) == ["dir=long", "dir=short"] and all(len(t) == 99 for t in units.values())
    assert all(LB.plateau(t)["info"] == 3 and LB.plateau(t)["cells_all"] == 96 for t in units.values())


def test_the_value_area_cache_holds_what_the_tape_gives_and_is_read_instead_of_the_tape(tmp_path, monkeypatch):
    real_days()
    days = [S._date(d) for d in DAYS[:3]]
    monkeypatch.setattr(R1, "_va_path", lambda root: tmp_path / f"va70_{root}.json")
    monkeypatch.setattr(S, "sessions", lambda a, b, root="NQ", **kw: days)
    monkeypatch.setattr(R1, "_VA", {})
    monkeypatch.setattr(R1, "_VA_FILE", {})
    out = R1.VaReclaim.prepare("NQ", workers=1)
    assert out["added"] == 3 and out["dates"] == 3 and R1.build_va("NQ")["added"] == 0          # restartable: nothing twice
    have = json.loads((tmp_path / "va70_NQ.json").read_text())
    assert sorted(have) == [d.isoformat() for d in days]
    for d in days:
        tape = S.load_tape(d)
        val, vah = R1.value_area_of(tape)
        assert have[d.isoformat()] == [val, vah] and val <= vah
        a, b = np.searchsorted(tape.ts, [S.et_ns(d, "09:30"), S.et_ns(d, "16:00")])
        px, sz = tape.px[a:b], tape.size[a:b]
        inside = sz[(px >= val - 1e-9) & (px <= vah + 1e-9)].sum() / sz.sum()
        assert 0.70 <= inside < 0.75 and px.min() <= val and vah <= px.max()                    # 70 % of the RTH volume, no more than needed
    monkeypatch.setattr(S, "load_tape", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the cache holds this date")))
    assert R1.value_area("NQ", days[0].isoformat()) == tuple(have[days[0].isoformat()])
