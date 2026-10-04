"""Shared harness of the verifier's look-ahead checks on the flow group F1-F4 (families/flow.py).
Verifier's own code (not part of the suite). Real in-sample days, ONE process, no P&L printed or asserted on:
only decision instants, sides, order prices (sl / tp / ref) and entry / exit stamps are compared for equality."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

L = Path.home() / "ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
sys.dont_write_bytecode = True
if str(L) not in sys.path:
    sys.path.insert(0, str(L))

import families  # noqa: E402
import l2sim as S  # noqa: E402
from families import flow as F  # noqa: E402

NS = S.NS
# in-sample; not the author's smoke days. 2023-06-12 = roll day (book_ok False all day), 2023-11-24 = CME half day,
# 2022-08-25 / 2024-11-06 hold one in-session row with book_valid False, 2022-03-10 = two sessions before a roll.
DAYS = ["2021-10-14", "2022-01-19", "2022-04-27", "2022-08-25", "2023-01-11", "2023-06-12", "2023-11-24", "2024-02-15",
        "2024-08-07", "2024-11-06"]
FAMS = {"delta_follow": F.DeltaFollow, "absorption": F.Absorption, "cvd_div": F.CvdDiv, "sweep_follow": F.SweepFollow}
TFS = ("1", "5")
COLS = ("f_delta", "f_sweep_buy_vol", "f_sweep_sell_vol", "t_utc", "book_ok")       # superset of every FEATURES tuple
FLOW = ("f_delta", "f_sweep_buy_vol", "f_sweep_sell_vol")


def spy_of(cls, flat: bool):
    """flat=True: the order is replaced by a note, the strategy stays flat -> EVERY in-session decision instant is logged.
    flat=False: real orders; the log holds what was sent."""
    class Spy(cls):
        def on_session(self, ctx):
            super().on_session(ctx)
            self.log = []

        def fam_signal(self, ctx):
            self._hit = None
            super().fam_signal(ctx)
            sn = self.sn
            ext = 0
            if sn >= 2:
                c = self.C[-1]
                ext = 1 if c > max(self.H[-sn:-1]) else -1 if c < min(self.L[-sn:-1]) else 0
            self.log.append({"now": ctx.now_ns, "sid": self.sid, "sn": sn, "nb": self.nb, "c": self.C[-1], "o": self.O[-1],
                             "atr": self.atr, "ext": ext, "hit": self._hit})

        def _mkt(self, ctx, side, **kw):
            if flat:
                self._hit = (side,)
                return None
            o = super()._mkt(ctx, side, **kw)
            self._hit = None if o is None else (side, o.kind, o.sl, o.tp, o.ref, o.min_i)
            return o
    Spy.__name__ = cls.__name__
    return Spy


_CACHE: dict = {}
_DAILY: list = []


def day_data(iso):
    if iso not in _CACHE:
        d = dt.date.fromisoformat(iso)
        S.check_holdout(d)
        if not _DAILY:
            _DAILY.extend(S.load_daily())
        _CACHE[iso] = (d, S.load_tape(d), S.L2Features(COLS)(d), [r for r in _DAILY if r["date"] < iso])
    return _CACHE[iso]


def play(name, tf, iso, flat=True, tape=None, feats=None):
    """One real session through l2sim.run_session exactly as l2sim._run_days does. -> (decision log, trades)."""
    d, tp, ft, prior = day_data(iso)
    st = spy_of(FAMS[name], flat)(families.screen_inputs(name, tf))
    st.ROLLS = S.default_rolls("NQ")
    window = S.effective_session_window(d, tuple(type(st).session_window))
    res = S.run_session(st, tp if tape is None else tape, S.Costs(), qty=1, daily=prior,
                        features=ft if feats is None else feats, window=window, on_error="raise")
    assert res.skip is None, res.skip
    assert res.both_sides is False
    return st.log, res.trades


def garbage_tape(tape, cut_ns, rng):
    """Same stamps; every print stamped >= cut gets a random price far away (on the tick grid) and a random size."""
    ts, px, size = tape.ts, tape.px.copy(), tape.size.copy()
    k = int(np.searchsorted(ts, cut_ns, side="left"))
    n = len(ts) - k
    if n:
        base = px[k - 1] if k else px[0]
        px[k:] = np.round((base + rng.choice([-1, 1]) * 400 + np.cumsum(rng.integers(-40, 41, n)) * 0.25) * 4) / 4
        size[k:] = rng.integers(1, 500, n)
    return S.Tape(tape.root, tape.date, tape.contract, ts, px, size)


def garbage_feats(f, cut_ns, rng, mode, side="right"):
    """Rows NOT usable at the cut (usable_ns > cut) become garbage (side='left': usable_ns >= cut, i.e. the row that
    becomes usable exactly AT the cut is garbage too -- used by the power test only).
    'loud+' / 'loud-': huge flow of one sign, book_ok True; 'random': random flow with NaNs, random book_ok, random
    t_utc; 'cut': the rows do not exist."""
    k = int(np.searchsorted(f.usable_ns, cut_ns, side=side))
    if mode == "cut":
        return S.Features(f.usable_ns[:k], {c: v[:k] for c, v in f.cols.items()})
    cols = {c: v.copy() for c, v in f.cols.items()}
    n = len(f.usable_ns) - k
    if mode.startswith("loud"):
        sg = 1.0 if mode.endswith("+") else -1.0
        cols["f_delta"][k:] = np.float32(sg * 1e7)
        cols["f_sweep_buy_vol"][k:] = np.float32(1e7 if sg > 0 else 0.0)
        cols["f_sweep_sell_vol"][k:] = np.float32(0.0 if sg > 0 else 1e7)
        cols["book_ok"][k:] = True
    elif mode == "random":
        for c in FLOW:
            v = rng.normal(0, 1e6, n)
            if c != "f_delta":
                v = np.abs(v)
            v[rng.random(n) < 0.1] = np.nan
            cols[c][k:] = v.astype(np.float32)
        cols["book_ok"][k:] = rng.random(n) < 0.5
        cols["t_utc"][k:] = rng.integers(0, 2 ** 40, n)
    else:
        raise ValueError(mode)
    return S.Features(f.usable_ns, cols)


def leak_plus_1min(f):
    """Row stamped M carries the FLOW VALUES of minute M + 1 (t_utc, book_ok and usable_ns untouched): a one-minute
    look-ahead that the family's own freshness rule (t_utc + 60 == T) cannot see."""
    t = f.cols["t_utc"]
    pos = {int(x): i for i, x in enumerate(t)}
    src = np.array([pos.get(int(x) + 60, -1) for x in t])
    cols = {c: v.copy() for c, v in f.cols.items()}
    for c in FLOW:
        v = f.cols[c]
        cols[c] = np.where(src >= 0, v[np.maximum(src, 0)], np.float32("nan")).astype(v.dtype)
    return S.Features(f.usable_ns, cols)


ENTRY = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ns", "entry_ms", "oco", "both_sides")


def compare(base, test, cut_ns):
    """Differences in what was decided / done up to the cut (decisions at now <= cut; trades closed before it; entries
    filled before it)."""
    (d0, t0), (d1, t1) = base, test
    bad = []
    a = [x for x in d0 if x["now"] <= cut_ns]
    b = [x for x in d1 if x["now"] <= cut_ns]
    if a != b:
        bad.append(("decisions", a, b))
    a = [t for t in t0 if t["exit_ns"] < cut_ns]
    b = [t for t in t1 if t["exit_ns"] < cut_ns]
    if a != b:
        bad.append(("closed trades", a, b))
    a = [tuple(t[k] for k in ENTRY) for t in t0 if t["entry_ns"] < cut_ns]
    b = [tuple(t[k] for k in ENTRY) for t in t1 if t["entry_ns"] < cut_ns]
    if a != b:
        bad.append(("entries", a, b))
    return bad
