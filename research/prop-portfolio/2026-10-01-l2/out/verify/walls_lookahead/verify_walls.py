"""ADVERSARIAL look-ahead verification of families/walls.py (B4 wall_bounce, B5 wall_break). Verifier's own test.

Real in-sample days only (<= 10 days, ONE process, no P&L printed: only equality / counts).

  T1  garbage-after-cut: every print with ts >= cut and every feature row with usable_ns > cut is replaced by garbage.
      Everything the family saw / read / asked for at decisions <= cut, every trade closed before the cut and the entry
      side of every trade opened before the cut must be bit-identical.
  T2  power: (a) the same T1 comparison on a table whose VALUES are shifted by +1 minute (row M carries minute M+1's
      book: a one-minute leak) must FAIL; (b) a mutant family that peeks one row ahead must FAIL T1; (c) the family's
      output on the leaked table differs from the real one (the family is sensitive to a +1 minute shift); (d) a pure
      clock shift (rows usable one minute early / late) is caught by the family's own freshness check (no order).
  T3  independent oracle: every decision's last price, ATR, order request and bracket recomputed from the raw parquet
      tape (pyarrow) and the raw feature cache (l2data.load_features, pandas) without ctx; every entry fill re-derived
      from the tape (first trigger print after decision + 85 ms, before the order's cancel time).
"""
import datetime as dt
import math
import sys
import time
import zlib

sys.dont_write_bytecode = True
L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
sys.path.insert(0, L)

import numpy as np
import pyarrow.parquet as pq

import families.walls as W
import l2data as D
import l2sim as S

NS, MIN, TICK = S.NS, S.MIN_NS, 0.25
DAYS = ["2021-11-10", "2022-03-14", "2022-03-22", "2022-08-17", "2023-05-18", "2023-07-03", "2023-11-06", "2024-09-18",
        "2024-11-04", "2024-12-05"]      # 03-14 = roll block (book masked); 03-22 / 11-06 / 11-04 = weeks after a DST change;
#                                          07-03 = half day; 09-18 = FOMC; 2023-11 / 2024-12 = the thin-margin months
assert len(DAYS) <= 10
assert all(d < "2025-01-01" for d in DAYS)
READS: list = []
N_RAND = int(sys.argv[2]) if len(sys.argv) > 2 else 3
POWER_EVERY = int(sys.argv[3]) if len(sys.argv) > 3 else 2
_real_feat = S.Ctx.feat


def _spy_feat(self, name, back=0, default=None):
    v = _real_feat(self, name, back, default)
    f, now = self._feat, self._s.now
    if f is not None:                                        # independent of the guard: the row index actually read
        k = int(np.searchsorted(f.usable_ns, now, side="right")) - 1 - back
        assert back >= 0 and (k < 0 or f.usable_ns[k] <= now), ("read of a row not usable yet", now, name, back)
    READS.append((now, name, back, v))
    return v


def _no_window(self, name, n=None):
    raise AssertionError("walls must not read feat_window")


S.Ctx.feat = _spy_feat
S.Ctx.feat_window = _no_window


class Spy:
    def __init__(self, params=None):
        super().__init__(params)
        self.seen, self.calls, self.recs = [], [], []

    def fam_signal(self, ctx):
        self.seen.append((ctx.now_ns, ctx.last_price, self.atr, self.nb))
        super().fam_signal(ctx)

    def _note(self, ctx, kind, side, px, struct, ttl, o):
        self.calls.append({"t": ctx.now_ns, "kind": kind, "side": side, "px": px, "struct": struct, "ttl": ttl,
                           "placed": o is not None, "o_px": o.price if o else None, "o_sl": o.sl if o else None,
                           "o_tp": o.tp if o else None})
        if o is not None:
            self.recs.append({"o": o, "t": ctx.now_ns, "cancel": None})

    def _lim(self, ctx, side, px, struct=None, tp_px=None, ttl=None, tag=None):
        o = super()._lim(ctx, side, px, struct=struct, tp_px=tp_px, ttl=ttl, tag=tag)
        self._note(ctx, "limit", side, px, struct, ttl, o)
        return o

    def _arm(self, ctx, legs, ttl=None, imm=False, tag=None):
        os_ = super()._arm(ctx, legs, ttl=ttl, imm=imm, tag=tag)
        assert len(legs) == 1 and not imm
        self._note(ctx, "stop", legs[0][0], legs[0][1], legs[0][2], ttl, os_[0] if os_ else None)
        return os_

    def _mkt(self, *a, **k):
        raise AssertionError("walls never enter at market")

    def _stamp(self, ctx):
        for r in self.recs:
            if r["cancel"] is None and r["o"].status == "cancelled":
                r["cancel"] = ctx.now_ns

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        self._stamp(ctx)

    def on_time(self, ctx, et_time):
        super().on_time(ctx, et_time)
        self._stamp(ctx)


class Bounce(Spy, W.WallBounce):
    pass


class Break(Spy, W.WallBreak):
    pass


# ---- mutants: a family that peeks at the row still forming (bypasses ctx.feat) -------------------------------------
def _peek_wall(ctx, side, m, back=0):
    f = ctx._feat
    n = f.n_usable(ctx.now_ns)
    k = n - back                                             # ONE ROW AHEAD of ctx.feat's n - 1 - back
    if k < 0 or k >= len(f.usable_ns) or not f.cols["book_ok"][k]:
        return None
    px, dist, sz, med = (float(f.cols[c][k]) for c in W.COLS[side])
    if not all(math.isfinite(v) for v in (px, dist, sz, med)) or med <= 0:
        return None
    return round(px / ctx.tick) + (-1 if side == "bid" else 1) * round(dist), sz >= m * med


class PeekBounce(Bounce):
    def fam_signal(self, ctx):
        old, W.wall = W.wall, _peek_wall
        try:
            super().fam_signal(ctx)
        finally:
            W.wall = old


class PeekBreak(Break):
    def fam_signal(self, ctx):
        old, W.wall = W.wall, _peek_wall
        try:
            super().fam_signal(ctx)
        finally:
            W.wall = old


# ---- data ----------------------------------------------------------------------------------------------------------
DAILY = S.load_daily("NQ")
DATES = [r["date"] for r in DAILY]
LOADER = S.L2Features(W.FEATURES)


def load(iso):
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d)
    tape = S.load_tape(d)
    feats = LOADER(d)
    from bisect import bisect_left
    prior = DAILY[:bisect_left(DATES, iso)]
    return d, tape, feats, prior


def run(cls, params, d, tape, feats, prior):
    READS.clear()
    st = cls(params)
    st.ROLLS = S.rolls(DAILY)
    costs = S.Costs(strict_limit=issubclass(cls, W.WallBounce))
    window = S.effective_session_window(d, tuple(cls.session_window))
    res = S.run_session(st, tape, costs, daily=prior, features=feats, window=window, on_error="raise")
    assert res.skip is None and res.both_sides is False
    return st, res.trades, list(READS)


def garbage(tape, feats, cut, seed):
    """Prints with ts >= cut and rows with usable_ns > cut replaced by garbage (other times, other prices, other books)."""
    g = np.random.default_rng(seed)
    keep = int(np.searchsorted(tape.ts, cut, side="left"))
    end = max(int(tape.ts[-1]), cut + 3600 * NS)
    n_tail = max(len(tape.ts) - keep, 5000)
    ts_tail = np.sort(g.integers(cut, end + 1, size=n_tail))
    ts_tail[0] = cut                                         # a garbage print exactly AT the cut
    base = float(tape.px[keep - 1]) if keep else float(tape.px[0])
    px_tail = base + TICK * np.cumsum(g.integers(-6, 7, size=n_tail))
    px_tail = np.maximum(px_tail, 100.0)
    t2 = S.Tape(tape.root, tape.date, tape.contract, np.concatenate([tape.ts[:keep], ts_tail]),
                np.concatenate([tape.px[:keep], px_tail]), np.concatenate([tape.size[:keep], g.integers(1, 50, size=n_tail)]))
    tail = feats.usable_ns > cut
    n = int(tail.sum())
    cols = {k: v.copy() for k, v in feats.cols.items()}
    if n:
        bid = np.round(base / TICK) + g.integers(-8, 9, size=n)
        ask = bid + g.integers(1, 4, size=n)
        bid[0], ask[0] = np.round(base / TICK) - 1, np.round(base / TICK) + 1       # tempting: walls 2 ticks either side
        cols["bid_px"][tail] = bid * TICK
        cols["ask_px"][tail] = ask * TICK
        for s in ("bid", "ask"):
            dist = g.integers(0, 10, size=n).astype(np.float32)
            dist[0] = 1
            sz = g.choice([500.0, 40.0, 6.0], size=n).astype(np.float32)
            med = g.choice([1.0, 5.0, np.nan], size=n, p=[0.6, 0.35, 0.05]).astype(np.float32)
            sz[0], med[0] = (500.0, 1.0) if s == "bid" else (3.0, 5.0)
            cols[f"{s}_wall_dist"][tail], cols[f"{s}_wall_sz"][tail], cols[f"{s}_med_sz"][tail] = dist, sz, med
        ok = g.random(n) < 0.9
        ok[0] = True
        cols["book_ok"][tail] = ok
    return t2, S.Features(feats.usable_ns.copy(), cols)


def leak_values(feats):
    """A ONE-MINUTE LEAK in the data layer: row M carries the book of minute M + 1 (t_utc / usable_ns unchanged)."""
    cols = {}
    for k, v in feats.cols.items():
        if k == "t_utc":
            cols[k] = v.copy()
        else:
            w = v.copy()
            w[:-1] = v[1:]
            cols[k] = w
    return S.Features(feats.usable_ns.copy(), cols)


def clock_shift(feats, minutes):
    """A clock shift in the adapter: every row becomes usable `minutes` earlier (< 0) or later (> 0); values unchanged."""
    return S.Features(feats.usable_ns + minutes * MIN, {k: v.copy() for k, v in feats.cols.items()})


def eqv(a, b):
    if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
        return True
    return a == b


def same_rows(xs, ys):
    return len(xs) == len(ys) and all(len(x) == len(y) and all(eqv(p, q) for p, q in zip(x, y)) for x, y in zip(xs, ys))


def callkey(c):
    return tuple(c[k] for k in ("t", "kind", "side", "px", "struct", "ttl", "placed", "o_px", "o_sl", "o_tp"))


ENTRY = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ns", "entry_ms", "oco")


def invariant(base, other, cut):
    """-> list of violated invariants (empty = everything up to the cut is identical)."""
    (sa, ta, ra), (sb, tb, rb) = base, other
    bad = []
    if not same_rows([x for x in sa.seen if x[0] <= cut], [x for x in sb.seen if x[0] <= cut]):
        bad.append("decisions")
    if not same_rows([callkey(c) for c in sa.calls if c["t"] <= cut], [callkey(c) for c in sb.calls if c["t"] <= cut]):
        bad.append("orders")
    if not same_rows([r for r in ra if r[0] <= cut], [r for r in rb if r[0] <= cut]):
        bad.append("reads")
    drop = ("both_sides",)
    ca = [{k: v for k, v in t.items() if k not in drop} for t in ta if t["exit_ns"] < cut]
    cb = [{k: v for k, v in t.items() if k not in drop} for t in tb if t["exit_ns"] < cut]
    if ca != cb:
        bad.append("closed_trades")
    ea = sorted(tuple(t[k] for k in ENTRY) for t in ta if t["entry_ns"] < cut)
    eb = sorted(tuple(t[k] for k in ENTRY) for t in tb if t["entry_ns"] < cut)
    if ea != eb:
        bad.append("entries")
    return bad


def cuts_for(d, st, trades, seed, n_rand=6):
    g = np.random.default_rng(seed)
    t0 = S.et_ns(d, "00:00")
    out = set()
    for _ in range(n_rand):                                   # random minute boundaries and off-boundary instants
        m = int(g.integers(20, 950))
        out.add(t0 + m * MIN)
        out.add(t0 + m * MIN + int(g.integers(1, 60 * NS)))
    calls = [c["t"] for c in st.calls]
    for t in (list(g.choice(calls, size=min(4, len(calls)), replace=False)) if calls else []):
        out.update((int(t), int(t) + 1, int(t) - 1, int(t) + 85_000_000, int(t) + MIN))      # at / around a signal
    for tr in trades[:3]:
        out.update((tr["entry_ns"], tr["entry_ns"] + 1, tr["exit_ns"], tr["exit_ns"] + 1))
    return sorted(out)


# ---- T3 oracle (raw parquet + raw cache, no ctx) ---------------------------------------------------------------------
def raw_day(iso):
    d = dt.date.fromisoformat(iso)
    t = pq.ParquetFile(S.tape_path(d)).read(columns=["ts_ns", "price", "size"])
    ts, px = t["ts_ns"].to_numpy(), t["price"].to_numpy()
    df = D.load_features(d - dt.timedelta(days=1), d, columns=list(W.FEATURES))
    idx = df.index.as_unit("ns").asi8
    assert ((idx // NS) == df["t_utc"].to_numpy() + 60).all()         # the table's own law: usable_at = stamp + 60 s
    return d, ts, px, {c: df[c].to_numpy() for c in W.FEATURES}, {int(u): i for i, u in enumerate(idx)}


def atr_series(ts, px, lo_ns, hi_ns, tf):
    """Own Wilder ATR(14) over tf bars built from the prints in [00:00 ET, window end): -> (bar end ns, ATR once that bar
    is closed, bars closed). Bars only for buckets that have a print."""
    step = tf * MIN
    a, b = np.searchsorted(ts, [lo_ns, hi_ns], side="left")
    k, seg = ts[a:b] // step, px[a:b]
    st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
    en = np.concatenate((st[1:], [len(k)]))
    h, l, c = np.maximum.reduceat(seg, st), np.minimum.reduceat(seg, st), seg[en - 1]
    ends, atrs, trs, atr = (k[st] + 1) * step, [], [], None
    for n in range(len(st)):
        tr = h[n] - l[n] if n == 0 else max(h[n] - l[n], abs(h[n] - c[n - 1]), abs(l[n] - c[n - 1]))
        if n < 14:
            trs.append(tr)
            atr = sum(trs) / (n + 1)
        else:
            atr = (atr * 13.0 + tr) / 14.0
        atrs.append(float(atr))
    return ends, np.array(atrs), np.arange(1, len(st) + 1)


def my_atr(series, now):
    ends, atrs, ns = series
    j = int(np.searchsorted(ends, now, side="right")) - 1          # the last bar that ended at or before the decision
    return (None, 0) if j < 0 else (float(atrs[j]), int(ns[j]))


def side_of(df, i, s, m):
    px, dist, sz, med = (float(df[c][i]) for c in W.COLS[s])
    if not bool(df["book_ok"][i]) or not all(map(math.isfinite, (px, dist, sz, med))) or med <= 0:
        return None
    return round(px / TICK + (-dist if s == "bid" else dist)), sz >= m * med


def oracle(kind, df, row, now, last, atr, p):
    lt, hits = round(last / TICK), []
    if kind == "limit":
        i = row.get(now)
        for s, sd in (("bid", 1), ("ask", -1)):
            w = side_of(df, i, s, p["m"]) if i is not None else None
            if w and w[1] and 1 <= sd * (lt - w[0]) <= p["near"]:
                lim = (w[0] + sd) * TICK
                hits.append((sd, lim, (w[0] - 4 * sd) * TICK, sd * (last - lim) > 0))
    else:
        idx = [row.get(now - k * MIN) for k in range(p["stand"] + 1)]
        if None not in idx:
            for s, sd in (("bid", -1), ("ask", 1)):
                new, old = side_of(df, idx[0], s, p["m"]), [side_of(df, i, s, p["m"]) for i in idx[1:]]
                if any(o is None or not o[1] for o in old) or len({o[0] for o in old}) != 1 or new is None:
                    continue
                w = old[0][0]
                if not (new[0] == w and new[1]) and sd * (lt - w) > 0:
                    hits.append((sd, (lt + sd) * TICK, (w - 4 * sd) * TICK, True))
    if len(hits) != 1:
        return None
    sd, px, struct, placed = hits[0]
    dist = max(abs(px - struct), 0.25 * atr, 2 * TICK)
    sl, tp = S.to_tick(px - sd * dist, TICK), S.to_tick(px + sd * 2.0 * dist, TICK)
    return ("long" if sd > 0 else "short", px, struct, placed, sl if placed else None, tp if placed else None)


def check_fills(st, trades, ts, px, kind, hi_ns):
    """Every placed order: its fill (or no fill) re-derived from the raw tape between decision + 85 ms and its cancel."""
    by_entry = {t["entry_ns"]: t for t in trades}
    n_fill = 0
    for r in st.recs:
        o, t = r["o"], r["t"]
        a = int(np.searchsorted(ts, t + 85_000_000, side="left"))
        stop = r["cancel"] if r["cancel"] is not None else hi_ns
        b = int(np.searchsorted(ts, stop, side="left"))
        seg = px[a:b]
        if kind == "limit":
            hit = np.flatnonzero(seg <= o.price - TICK + 1e-9) if o.side > 0 else np.flatnonzero(seg >= o.price + TICK - 1e-9)
        else:
            hit = np.flatnonzero(seg >= o.price - 1e-9) if o.side > 0 else np.flatnonzero(seg <= o.price + 1e-9)
        if o.status == "filled":
            assert len(hit), ("filled without a trigger print in its life", t)
            k = a + int(hit[0])
            tr = by_entry.get(int(ts[k]))
            assert tr is not None and int(ts[k]) > t, ("fill print not the first trigger after the decision", t)
            if kind == "limit":
                assert tr["entry_price"] == o.price
            else:
                want = (max(o.price, px[k]) + TICK) if o.side > 0 else (min(o.price, px[k]) - TICK)
                assert tr["entry_price"] == want, (tr["entry_price"], want)
            n_fill += 1
        else:
            assert o.status == "cancelled" and stop > t and not len(hit), ("unfilled order had a trigger", t)
    assert n_fill == len(trades), (n_fill, len(trades))
    return n_fill


# ---- main ------------------------------------------------------------------------------------------------------------
def main():
    S.wait_compute_window()
    configs = []
    for cls, peek, kind in ((Bounce, PeekBounce, "limit"), (Break, PeekBreak, "stop")):
        for tf in ("1", "5"):
            configs.append((cls, peek, kind, {"tf": tf}, "default"))
            configs.append((cls, peek, kind, {"tf": tf, "max_tr": 20, "m": 3.0}, "busy"))      # more decisions that fire
    tot = {"runs": 0, "cuts": 0, "T1_viol": 0, "post_cut_differs": 0, "leak_cuts": 0, "leak_eligible": 0, "leak_eligible_detected": 0, "peek_eligible_bounce": 0, "peek_eligible_bounce_detected": 0, "leak_detected": 0, "leak_out_detected": 0,
           "peek_cuts": 0, "peek_detected": 0, "peek_out_detected": 0}
    per, day_calls = {}, {}
    t_start = time.time()
    for iso in (DAYS[:int(sys.argv[1])] if len(sys.argv) > 1 else DAYS):
        d, tape, feats, prior = load(iso)
        rd, rts, rpx, rdf, rrow = raw_day(iso)
        assert len(rts) == len(tape.ts) and (rts == tape.ts).all()
        lo_ns = S.et_ns(d, "00:00")
        hi_ns = S.et_ns(d, S.effective_session_window(d, ("00:00", "16:10"))[1])
        for cls, peek, kind, params, label in configs:
            key = (cls.__name__, params["tf"], label)
            c = per.setdefault(key, {"days": 0, "decisions": 0, "calls": 0, "placed": 0, "trades": 0, "reads": 0, "cuts": 0,
                                     "viol": 0, "oracle_checked": 0, "fills_checked": 0, "late_closes": 0,
                                     "leak_changes_output_days": 0, "early_clock_calls": 0, "late_clock_calls": 0,
                                     "stale_values_same_days": 0})
            base = run(cls, params, d, tape, feats, prior)
            st, trades, reads = base
            tot["runs"] += 1
            c["days"] += 1
            day_calls[iso] = day_calls.get(iso, 0) + len(st.calls)
            c["decisions"] += len(st.seen)
            c["calls"] += len(st.calls)
            c["placed"] += sum(x["placed"] for x in st.calls)
            c["trades"] += len(trades)
            c["reads"] += len(reads)
            # -- direct checks on the base run: every read row usable, decisions on minute boundaries
            assert all(now % MIN == 0 for now, *_ in reads) and all(b in (0, 1, 2) for _, _, b, _ in reads)
            tf = int(params["tf"])
            c["late_closes"] += sum(1 for x in st.seen if x[0] % (tf * MIN) != 0)
            # -- T3 oracle
            series = atr_series(rts, rpx, lo_ns, hi_ns, tf)
            calls = {x["t"]: x for x in st.calls}
            assert len(calls) == len(st.calls)
            for now, last, atr, nb in st.seen:
                i = int(np.searchsorted(rts, now, side="left"))
                assert i > 0 and rts[i - 1] < now and float(rpx[i - 1]) == last and rts[i - 1] >= lo_ns, "last price"
                a2, n2 = my_atr(series, now)
                assert n2 == nb and abs(a2 - atr) < 1e-9, ("ATR", a2, atr, n2, nb)
                want = oracle(kind, rdf, rrow, now, last, a2, st.p)
                got = calls.get(now)
                got = None if got is None else (got["side"], got["px"], got["struct"], got["placed"], got["o_sl"], got["o_tp"])
                assert got == want, (iso, key, (now - lo_ns) // MIN, got, want)
                c["oracle_checked"] += 1
            c["fills_checked"] += check_fills(st, trades, rts, rpx, kind, hi_ns)
            for tr in trades:                                 # an entry is strictly after its decision + 85 ms
                prev = max(x["t"] for x in st.calls if x["placed"] and x["t"] < tr["entry_ns"])
                assert tr["entry_ns"] >= prev + 85_000_000
            # -- T1 garbage after the cut
            cuts = cuts_for(d, st, trades, seed=zlib.crc32(repr((iso,) + key).encode()), n_rand=N_RAND)
            lk = leak_values(feats)
            base_lk = run(cls, params, d, tape, lk, prior)
            base_pk = run(peek, params, d, tape, feats, prior)
            for n, cut in enumerate(cuts):
                t2, f2 = garbage(tape, feats, cut, seed=n + 17)
                other = run(cls, params, d, t2, f2, prior)
                bad = invariant(base, other, cut)
                tot["cuts"] += 1
                c["cuts"] += 1
                if bad:
                    tot["T1_viol"] += 1
                    c["viol"] += 1
                    print("T1 VIOLATION", iso, key, (cut - lo_ns) / MIN, bad, flush=True)
                tot["post_cut_differs"] += ([callkey(x) for x in st.calls if x["t"] > cut] !=
                                            [callkey(x) for x in other[0].calls if x["t"] > cut])
                if n % POWER_EVERY:
                    continue
                # -- T2a: the same comparison on a leaked table must fail
                bad_lk = invariant(base_lk, run(cls, params, d, t2, leak_values(f2), prior), cut)
                tot["leak_cuts"] += 1
                last_b = cut - cut % MIN
                el = any(r[0] == last_b and r[2] == 0 and r[1] not in ("t_utc",) for r in base_lk[2])   # newest row was read
                tot["leak_eligible"] += el
                tot["leak_eligible_detected"] += el and bool(bad_lk)
                tot["leak_detected"] += bool(bad_lk)
                tot["leak_out_detected"] += bool(set(bad_lk) & {"orders", "entries", "closed_trades"})
                # -- T2b: a peeking mutant of the family must fail
                bad_pk = invariant(base_pk, run(peek, params, d, t2, f2, prior), cut)
                tot["peek_cuts"] += 1
                el = kind == "limit" and any(x[0] == last_b for x in base_pk[0].seen)
                tot["peek_eligible_bounce"] += el
                tot["peek_eligible_bounce_detected"] += el and bool(bad_pk)
                tot["peek_detected"] += bool(bad_pk)
                tot["peek_out_detected"] += bool(set(bad_pk) & {"orders", "entries", "closed_trades"})
            # -- T2c: output sensitivity to a +1 minute value shift; T2d clock shifts are caught by freshness
            c["leak_changes_output_days"] += [callkey(x) for x in base_lk[0].calls] != [callkey(x) for x in st.calls]
            c["early_clock_calls"] += len(run(cls, params, d, tape, clock_shift(feats, -1), prior)[0].calls)
            c["late_clock_calls"] += len(run(cls, params, d, tape, clock_shift(feats, +1), prior)[0].calls)
        print("day done", iso, round(time.time() - t_start), "s", flush=True)
    print("\nper config (counts only):")
    for k, v in per.items():
        print(" ", k, v)
    print("\ncalls per day (all 8 configs):", day_calls)
    print("\nTOTAL", tot)
    return 1 if tot["T1_viol"] else 0


if __name__ == "__main__":
    sys.exit(main())
