"""Differential tests: l2sim's engine vs the tester's OWN engine (homebase/backtest/engine.py, imported
read-only, no bytecode written) on identical tapes with identical strategy objects. In-sample days only."""
import datetime as dt
import random
from array import array

import numpy as np
import pytest

import l2ref
import l2sim as S

E = pytest.importorskip("homebase.backtest.engine")
from homebase.backtest.tape import Tape as HBTape          # noqa: E402

KEYS = ("date", "side", "qty", "entry_ns", "entry_price", "exit_ns", "exit_price", "exit_reason", "order_price",
        "sl", "tp", "gross", "commission", "net", "mae_pts", "mfe_pts", "mae_usd", "mfe_usd", "bars", "seconds")
REAL_DAYS = ["2021-11-26", "2022-06-13", "2023-03-13", "2023-11-24", "2024-08-05", "2024-12-31"]
#            half day      roll day      DST week+roll half day     high vol     last in-sample day


def hb_tape(t: S.Tape) -> HBTape:
    return HBTape(t.root, t.date, t.contract, array("q", t.ts.tolist()), array("d", t.px.tolist()),
                  array("i", t.size.tolist()), dict(t.daily))


def both(make, tape: S.Tape, daily=None, window=None):
    """Run a fresh strategy instance on each engine; returns (tester trades, l2sim trades) as dict lists."""
    a = make()
    window = window or a.session_window
    a.session_window = window                                  # as the tester's runner does
    ra = E.run_session(a, hb_tape(tape), E.Costs(), qty=1, daily=list(daily or []))
    assert ra.skip is None, ra.skip                             # a crash inside the tester engine would hide here
    b = make()
    rb = S.run_session(b, tape, S.Costs(), qty=1, daily=list(daily or []), window=window)
    ta = [t.to_dict() for t in ra.trades]
    tb = [{k: t[k] for k in KEYS} for t in rb.trades]
    return ta, tb, a, b


class Fuzz(S.Strategy):
    """Random order flow through the whole ctx API (market / stop / limit, sl / tp / tp_rr / ref, OCO, cancel,
    flatten, off-grid prices, overlapping positions). Deterministic per (seed, date)."""
    session_window = ("09:30", "11:00")
    bar_minutes = 1
    DEFAULTS = {"seed": 0, "rate": 0.5}

    def times(self):
        return ["09:45:30", "10:30", "10:55"]

    def on_session(self, ctx):
        self.r = random.Random(f"{self.p['seed']}|{ctx.date}")
        self.live = []

    def on_bar(self, ctx, bar):
        if self.r.random() < self.p["rate"]:
            self._act(ctx)

    def on_time(self, ctx, t):
        if t == "10:55":
            ctx.flatten("time")
        else:
            self._act(ctx)

    def _act(self, ctx):
        r, lp, t = self.r, ctx.last_price, ctx.tick
        if lp is None:
            return
        ctx.move_brackets_to_fill = r.random() < 0.5
        u = r.random()
        side = r.choice(("long", "short"))
        sd = 1 if side == "long" else -1
        noise = r.choice((0.0, 0.0, 0.07, -0.11))
        d, g = r.randint(1, 40) * t, r.randint(1, 60) * t
        kw = {}
        if r.random() < 0.85:
            kw["sl"] = lp - sd * d + noise
        if r.random() < 0.5:
            kw["tp"] = lp + sd * g
        elif r.random() < 0.5:
            kw["tp_rr"] = r.choice((0.5, 1.0, 2.0))
        if u < 0.12:
            if r.random() < 0.7:
                kw["ref"] = lp
            self.live.append(ctx.market(side, **kw))
        elif u < 0.26:
            self.live.append(ctx.stop_entry(side, lp + sd * r.randint(-3, 12) * t + noise, **kw))
        elif u < 0.40:
            self.live.append(ctx.limit_entry(side, lp - sd * r.randint(-3, 12) * t + noise, **kw))
        elif u < 0.50:
            k = r.randint(1, 10) * t
            a = ctx.stop_entry("long", lp + k, sl=lp + k - d, tp=lp + k + g)
            b = ctx.stop_entry("short", lp - k, sl=lp - k + d, tp_rr=1.5)
            ctx.oco(a, b)
            self.live += [a, b]
        elif u < 0.62 and self.live:
            ctx.cancel(r.choice(self.live))
        elif u < 0.68:
            ctx.flatten(r.choice(("time", "bars", "trail")))


def order_state(strat):
    return [(o.side, o.kind, o.price, o.status, o.fill_px, o.fill_sl, o.fill_tp, o.fill_ms) for o in strat.live]


def synth(seed: int, n: int = 40_000) -> S.Tape:
    """A random-walk tape 09:30-11:00 with bursts sharing one timestamp, gaps and empty minutes."""
    rng = np.random.default_rng(seed)
    d = dt.date(2024, 1, 9)
    t0 = S.et_ns(d, "09:30")
    gaps = rng.exponential(5400e9 / (0.62 * n), n)             # ~0.7 of the gaps survive: the walk overruns 11:00
    gaps[rng.random(n) < 0.3] = 0                               # same-ns bursts
    gaps[rng.integers(0, n, 6)] += 150e9                        # holes: minutes with no print
    ts = t0 + np.cumsum(gaps).astype(np.int64)
    step = rng.choice([-1, 0, 0, 1], n) * (1 + (rng.random(n) < 0.02) * rng.integers(1, 30, n))
    px = 17000.0 + np.cumsum(step) * 0.25
    keep = ts < S.et_ns(d, "11:00")
    return S.Tape("NQ", d, "NQH4", ts[keep], px[keep], rng.integers(1, 20, n)[keep])


@pytest.mark.parametrize("seed", range(12))
def test_fuzz_synthetic_tapes_match_the_tester_engine(seed):
    tape = synth(seed)
    ta, tb, a, b = both(lambda: Fuzz({"seed": seed, "rate": 1.0}), tape)
    assert len(ta) >= 10
    assert ta == tb
    assert order_state(a) == order_state(b)


def test_fuzz_covers_every_order_kind_and_exit_reason():
    """The fuzz is only evidence if it exercises the law: across seeds every entry kind fills and gets cancelled,
    every exit reason occurs, brackets move to the fill, and same-timestamp bursts are present."""
    reasons, kinds, n, moved = set(), set(), 0, 0
    for seed in range(12):
        tape = synth(seed)
        assert (np.diff(tape.ts) == 0).mean() > 0.2
        ta, tb, a, _ = both(lambda: Fuzz({"seed": seed, "rate": 1.0}), tape)
        assert ta == tb
        n += len(ta)
        reasons |= {t["exit_reason"] for t in ta}
        kinds |= {(o.kind, o.status) for o in a.live}
        moved += sum(1 for o in a.live if o.status == "filled" and o.sl is not None and o.fill_sl != o.sl)
    assert reasons >= {"sl", "tp", "time", "bars", "trail"}
    assert kinds >= {(k, st) for k in ("market", "stop", "limit") for st in ("filled", "cancelled")} - {("market", "cancelled")}
    assert n > 300 and moved > 20


@pytest.mark.parametrize("iso", REAL_DAYS)
def test_fuzz_real_days_match_the_tester_engine(iso):
    tape = S.load_tape(iso)
    assert tape is not None
    window = S.effective_session_window(tape.date, Fuzz.session_window)
    ta, tb, a, b = both(lambda: Fuzz({"seed": 7, "rate": 1.0}), tape, window=window)
    assert len(ta) >= 10 and ta == tb
    assert order_state(a) == order_state(b)


CASES = [("straddle", {"tf": "30", "off_atr": 0.25, "stop_val": 3.0, "tgt_r": 2.0}),
         ("orb", {"tf": "5", "or_min": "5", "stop_val": 3.0, "tgt_r": 2.0}),
         ("donchian", {"tf": "15", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": 0.6}),
         ("donchian", {"tf": "5", "n": 10, "stop_mode": "struct", "tgt_r": 1.0, "trail_atr": 1.0, "exit_bars": 6,
                       "f_trend": "with", "f_vwap": "with"}),
         ("straddle", {"tf": "1", "off_atr": 1.0, "stop_val": 1.0, "tgt_r": 0.5, "delay_min": 5, "dir": "long"})]


@pytest.mark.parametrize("fam,params", CASES)
def test_reference_families_match_on_the_tester_engine(fam, params):
    """The l2ref families (l2sim.Template) produce the same trades on the tester's engine and on l2sim."""
    daily = S.load_daily()
    roll = S.rolls(daily)
    dates = [r["date"] for r in daily]
    n = 0
    for iso in REAL_DAYS[:4]:
        tape = S.load_tape(iso)
        prior = daily[:dates.index(iso)]

        def make():
            s = l2ref.FAMILIES[fam](params)
            s.ROLLS = roll
            return s
        window = S.effective_session_window(tape.date, l2ref.FAMILIES[fam].session_window)
        ta, tb, _, _ = both(make, tape, daily=prior, window=window)
        assert ta == tb
        n += len(ta)
    assert n > 0


def test_bars_equal_the_tester_build_bars():
    tape = S.load_tape("2022-06-13")
    hb = hb_tape(tape)
    for w0, w1, m in (("00:00", "16:10", 1), ("09:30", "16:00", 5), ("09:25", "13:17", 15), ("03:00", "08:25", 30)):
        t0, t1 = S.et_ns(tape.date, w0), S.et_ns(tape.date, w1)
        lo, hi = int(np.searchsorted(tape.ts, t0)), int(np.searchsorted(tape.ts, t1))
        ref = E.build_bars(hb.ts, hb.px, hb.size, lo, hi, t0, t1, m)
        got = S.build_bars(tape.ts, tape.px, tape.size, lo, hi, t0, t1, m)
        assert [(b.start_ns, b.end_ns, b.o, b.h, b.l, b.c, b.v) for b in ref] == \
               [(b.start_ns, b.end_ns, b.o, b.h, b.l, b.c, b.v) for b in got]
        assert len(got) > 10
