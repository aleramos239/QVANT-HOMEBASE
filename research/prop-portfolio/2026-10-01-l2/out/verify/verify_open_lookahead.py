"""ADVERSARIAL look-ahead verification of O1 open_dir (families/opendir.py). Verifier's own test, not part of the suite.

Real in-sample days (10, one process), real tape + real L2Features slices, run through l2sim.run_session exactly as
l2sim._run_days does. No P&L is printed or asserted on: only decisions (side / order price / stop), entry / exit stamps.

  1. GARBAGE AFTER A CUT: every feature row not yet usable at the cut and every print stamped >= the cut is replaced by
     garbage (three modes). Every decision taken at or before the cut, every trade closed before it and the entry of
     every trade opened before it must be bit-identical to the clean run.
  2. POWER of 1: the same check must FAIL on a table whose values sit one minute early (row t_utc = M carries minute
     M + 1: a one-minute look-ahead that the family's freshness rule cannot see).
  3. POWER of the family: with that +1 minute table the family's decisions differ from the clean run.
  4. One notch earlier: garbage in the newest USABLE row changes decisions (the newest row is really read).
"""
import datetime as dt
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest

L = Path.home() / "ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
sys.dont_write_bytecode = True
if str(L) not in sys.path:
    sys.path.insert(0, str(L))

import families  # noqa: E402
import l2sim as S  # noqa: E402
from families import opendir as OD  # noqa: E402

DAYS = ["2021-11-17", "2022-02-09", "2022-05-04", "2022-10-19", "2023-02-08", "2023-06-21", "2023-09-14", "2024-01-23",
        "2024-07-11", "2024-11-06"]                                       # in-sample; not the author's six days
VARIANTS = {"book": OD.OpenDirBook, "flow": OD.OpenDirFlow, "both": OD.OpenDirBoth}
COLS = ("imb10", "f_delta", "t_utc")                                      # one table for all three (superset of FEATURES)
LOG: list = []


def spy_of(cls):
    class Spy(cls):
        def fam_time(self, ctx, sec):
            n0 = len(self.orders)
            sid = self.sid
            super().fam_time(ctx, sec)
            if sid in OD.OPENS and sec == OD.OPENS[sid]:
                o = self.orders[-1][0] if len(self.orders) > n0 else None
                LOG.append({"day": self.day, "sid": sid, "now": ctx.now_ns, "atr": self.atr, "lp": ctx.last_price,
                            "nb": self.nb, "order": None if o is None else (o.side, o.price, o.sl, o.tp, o.min_i)})
    Spy.__name__ = cls.__name__
    return Spy


_CACHE: dict = {}


def day_data(iso):
    if iso not in _CACHE:
        d = dt.date.fromisoformat(iso)
        tape = S.load_tape(d)
        feats = S.L2Features(COLS)(d)
        daily = S.load_daily()
        prior = [r for r in daily if r["date"] < iso]
        _CACHE[iso] = (d, tape, feats, prior)
    return _CACHE[iso]


def play(src, iso, tape=None, feats="real"):
    d, tp, ft, prior = day_data(iso)
    tape = tp if tape is None else tape
    feats = ft if isinstance(feats, str) else feats
    st = spy_of(VARIANTS[src])(families.screen_inputs(f"open_dir_{src}", "30"))
    st.ROLLS = S.default_rolls("NQ")
    del LOG[:]
    window = S.effective_session_window(d, tuple(type(st).session_window))
    res = S.run_session(st, tape, S.Costs(), qty=1, daily=prior, features=feats, window=window, on_error="raise")
    assert res.skip is None and res.both_sides is False
    return list(LOG), res.trades


def garbage_tape(tape, cut_ns, rng):
    """Same stamps; every print stamped >= cut gets a random price far away (tick grid) and a random size."""
    ts, px, size = tape.ts, tape.px.copy(), tape.size.copy()
    k = int(np.searchsorted(ts, cut_ns, side="left"))
    n = len(ts) - k
    px[k:] = np.round((px[k - 1] + rng.choice([-1, 1]) * 400 + np.cumsum(rng.integers(-40, 41, n)) * 0.25) * 4) / 4
    size[k:] = rng.integers(1, 500, n)
    return S.Tape(tape.root, tape.date, tape.contract, ts, px, size)


def garbage_feats(f, cut_ns, rng, mode):
    """Rows NOT usable at the cut (usable_ns > cut) are garbage. mode: 'loud' = values of the opposite extreme,
    'random' = random values AND random t_utc, 'cut' = the rows do not exist."""
    k = int(np.searchsorted(f.usable_ns, cut_ns, side="right"))
    if mode == "cut":
        return S.Features(f.usable_ns[:k], {c: v[:k] for c, v in f.cols.items()})
    cols = {c: v.copy() for c, v in f.cols.items()}
    n = len(f.usable_ns) - k
    if mode == "loud":
        cols["imb10"][k:] = np.float32(0.99) * rng.choice([-1, 1])
        cols["f_delta"][k:] = np.float32(1e7) * rng.choice([-1, 1])
    else:
        cols["imb10"][k:] = rng.uniform(-1, 1, n).astype(np.float32)
        cols["f_delta"][k:] = rng.normal(0, 1e6, n).astype(np.float32)
        cols["t_utc"][k:] = rng.integers(0, 2 ** 40, n)
    return S.Features(f.usable_ns, cols)


def shift_plus_1min(f):
    """Row stamped M carries the VALUES of minute M + 1 (t_utc and usable_ns untouched): a one-minute look-ahead."""
    t = f.cols["t_utc"]
    pos = {int(x): i for i, x in enumerate(t)}
    src = np.array([pos.get(int(x) + 60, -1) for x in t])
    cols = {"t_utc": t.copy()}
    for c in ("imb10", "f_delta"):
        v = f.cols[c]
        cols[c] = np.where(src >= 0, v[np.maximum(src, 0)], np.float32("nan")).astype(v.dtype)
    return S.Features(f.usable_ns, cols)


ENTRY = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ns", "entry_ms", "oco", "both_sides")


def compare(base, test, cut_ns):
    """-> list of differences in what was decided / done before the cut."""
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


def cuts(d):
    t0 = S.et_ns(d, "00:00")
    out = []
    for s, o in OD.OPENS.items():
        out += [t0 + o * S.NS,                      # exactly the decision time
                t0 + (o + 1) * S.NS,                # one second after it (the order is live)
                t0 + (o + 17 * 60 + 13) * S.NS,     # inside the order's life
                t0 + (o + 3600) * S.NS]             # the cancel time
    return out


@pytest.mark.parametrize("src", list(VARIANTS))
def test_garbage_after_the_cut_never_changes_what_was_decided_before_it(src):
    if S.compute_window_end() is not None:
        pytest.skip("offline compute window")
    n_dec = n_ord = n_cmp = 0
    for iso in DAYS:
        d, tape, feats, _ = day_data(iso)
        base = play(src, iso)
        n_dec += len(base[0])
        n_ord += sum(x["order"] is not None for x in base[0])
        for j, cut in enumerate(cuts(d)):
            for mode in ("loud", "random", "cut"):
                rng = np.random.default_rng(zlib.crc32(f'{iso}{j}{mode}'.encode()))
                test = play(src, iso, garbage_tape(tape, cut, rng), garbage_feats(feats, cut, rng, mode))
                bad = compare(base, test, cut)
                assert not bad, (src, iso, j, mode, bad[0][0], bad[0][1][:2], bad[0][2][:2])
                n_cmp += 1
    print(f"\n[{src}] days {len(DAYS)} decisions {n_dec} orders {n_ord} garbage runs compared {n_cmp}")
    assert n_dec >= 30 and n_ord >= 5              # the check is not vacuous


@pytest.mark.parametrize("src", list(VARIANTS))
def test_power_the_garbage_check_catches_a_one_minute_leak(src):
    """The same comparison on a table whose values sit one minute early MUST find changed decisions at the cut = open."""
    if S.compute_window_end() is not None:
        pytest.skip("offline compute window")
    caught = total = 0
    for iso in DAYS:
        d, tape, feats, _ = day_data(iso)
        leaky = shift_plus_1min(feats)
        base = play(src, iso, feats=leaky)
        t0 = S.et_ns(d, "00:00")
        for j, o in enumerate(OD.OPENS.values()):
            cut = t0 + o * S.NS
            rng = np.random.default_rng(zlib.crc32(f'{iso}{j}'.encode()))
            # garbage the CLEAN table's unusable rows, then apply the leak: the leaked row now shows garbage
            test = play(src, iso, garbage_tape(tape, cut, rng), shift_plus_1min(garbage_feats(feats, cut, rng, "loud")))
            total += 1
            caught += bool(compare(base, test, cut))
    print(f"\n[{src}] one-minute leak: {caught} of {total} day x open cuts flagged")
    assert caught >= 3


@pytest.mark.parametrize("src", list(VARIANTS))
def test_power_plus_one_minute_shift_changes_the_family_output(src):
    if S.compute_window_end() is not None:
        pytest.skip("offline compute window")
    changed = total = 0
    for iso in DAYS:
        _, _, feats, _ = day_data(iso)
        d0, _ = play(src, iso)
        d1, _ = play(src, iso, feats=shift_plus_1min(feats))
        assert [(x["sid"], x["now"], x["atr"], x["lp"]) for x in d0] == [(x["sid"], x["now"], x["atr"], x["lp"]) for x in d1]
        for a, b in zip(d0, d1):
            total += 1
            sa = None if a["order"] is None else a["order"][0]
            sb = None if b["order"] is None else b["order"][0]
            changed += sa != sb
    print(f"\n[{src}] +1 minute value shift: {changed} of {total} decisions change side / existence")
    assert changed >= 1


@pytest.mark.parametrize("src", list(VARIANTS))
def test_power_the_newest_usable_row_is_read(src):
    """Garbage one row EARLIER than allowed (the row usable exactly at the open) drives the decision: a NaN book row
    kills the book / both signal; a huge +/- delta in it dictates the flow side."""
    if S.compute_window_end() is not None:
        pytest.skip("offline compute window")
    n = 0
    for iso in DAYS:
        d, tape, feats, _ = day_data(iso)
        d0, _ = play(src, iso)
        t0 = S.et_ns(d, "00:00")
        ks = [int(np.searchsorted(feats.usable_ns, t0 + o * S.NS, side="right")) - 1 for o in OD.OPENS.values()]
        if src == "flow":
            for sgn, want in ((1, 1), (-1, -1)):
                cols = {c: v.copy() for c, v in feats.cols.items()}
                cols["f_delta"][ks] = np.float32(sgn * 1e7)
                d1, _ = play(src, iso, feats=S.Features(feats.usable_ns, cols))
                for a, b in zip(d0, d1):
                    if a["order"] is not None:
                        n += 1
                        assert b["order"] is not None and b["order"][0] == want, (iso, a, b)
        else:
            cols = {c: v.copy() for c, v in feats.cols.items()}
            cols["imb10"][ks] = np.float32("nan")
            d1, _ = play(src, iso, feats=S.Features(feats.usable_ns, cols))
            assert all(b["order"] is None for b in d1), (iso, d1)
            n += sum(a["order"] is not None for a in d0)
    print(f"\n[{src}] newest usable row corrupted: {n} order decisions all follow the corrupted row")
    assert n >= 5
