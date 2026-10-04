"""B4 wall_bounce / B5 wall_break (families/walls.py) on REAL in-sample days: the look-ahead verifier's adversarial test,
kept with the suite (out/verify/walls_lookahead/verify_walls.py, trimmed). 10 fixed in-sample days, ONE process, equality
and counts only: no P&L is computed, printed or asserted.

  cut     every print with ts >= cut and every feature row usable after the cut is replaced by garbage (other times,
          other prices, other books; a tempting wall right at the cut). Every decision, every feature value read and
          every order request at t <= cut, every trade closed before the cut and the entry side of every trade opened
          before it must be bit-identical.
  power   the same comparison on a table with a ONE-MINUTE LEAK (row M carries the book of minute M + 1) must FAIL at
          every decision that reads the newest row.
  oracle  every decision's last price and order request (side, price, structure stop, brackets) recomputed without ctx
          from the raw parquet tape and the raw feature cache (l2data.load_features), with an ATR of its own; every
          entry fill re-derived from the tape (first trigger print at / after decision + 85 ms, before the cancel).
Skipped when the tape / feature cache is not on this machine, or inside an offline compute window."""
import datetime as dt
import math
import zlib
from bisect import bisect_left

import numpy as np
import pytest

import families.walls as W
import l2sim as S

NS, MIN, TICK, LIVE = S.NS, S.MIN_NS, 0.25, 85_000_000
DAYS = ("2021-11-10", "2022-03-14", "2022-03-22", "2022-08-17", "2023-05-18", "2023-07-03", "2023-11-06", "2024-09-18",
        "2024-11-04", "2024-12-05")     # 03-14 = roll block (book masked); 03-22 / 11-06 / 11-04 = weeks after a DST change;
#                                         07-03 = half day; 09-18 = FOMC; 2023-11 / 2024-12 = the thin-margin months
BUSY = {"max_tr": 20, "m": 3.0}         # more decisions fire; the screened config is {}
CONFIGS = (("1", {}), ("5", {}), ("1", BUSY), ("5", BUSY))
READS: list = []
assert len(DAYS) <= 10 and all(d < "2025-01-01" for d in DAYS)


class Spy:
    """Records every decision (`seen`), every order request (`calls`) and the life of every order placed (`recs`)."""

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
        raise AssertionError("the wall families never enter at market")

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


# ---- data (loaded once; skipped when it is not on this machine) -----------------------------------------------------
@pytest.fixture(scope="module")
def real():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    import l2data as D
    import pyarrow.parquet as pq
    try:
        daily = S.load_daily("NQ", build=False)
        if not daily:
            pytest.skip("daily cache not built")
        dates, loader, days = [r["date"] for r in daily], S.L2Features(W.FEATURES), []
        for iso in DAYS:
            d = dt.date.fromisoformat(iso)
            S.check_holdout(d)
            tape = S.load_tape(d)
            if tape is None:
                pytest.skip(f"tape of {iso} not cached")
            t = pq.ParquetFile(S.tape_path(d)).read(columns=["ts_ns", "price"])
            rts, rpx = t["ts_ns"].to_numpy(), t["price"].to_numpy()
            assert len(rts) == len(tape.ts) and (rts == tape.ts).all()
            df = D.load_features(d - dt.timedelta(days=1), d, columns=list(W.FEATURES))
            idx = df.index.as_unit("ns").asi8
            assert ((idx // NS) == df["t_utc"].to_numpy() + 60).all()          # the table's own law: usable_at = stamp + 60 s
            days.append({"iso": iso, "d": d, "tape": tape, "feats": loader(d), "prior": daily[:bisect_left(dates, iso)],
                         "rts": rts, "rpx": rpx, "df": {c: df[c].to_numpy() for c in W.FEATURES},
                         "row": {int(u): i for i, u in enumerate(idx)}})
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    return {"rolls": S.rolls(daily), "days": days}


@pytest.fixture
def reads(monkeypatch):
    """Every ctx.feat call of the test is logged in READS and checked against the table's own usable_ns."""
    real_feat = S.Ctx.feat

    def spy(self, name, back=0, default=None):
        v = real_feat(self, name, back, default)
        f, now = self._feat, self._s.now
        k = int(np.searchsorted(f.usable_ns, now, side="right")) - 1 - back
        assert back >= 0 and (k < 0 or f.usable_ns[k] <= now), ("read of a row not usable yet", now, name, back)
        READS.append((now, name, back, v))
        return v

    def window(self, name, n=None):
        raise AssertionError("the wall families read single rows only")
    monkeypatch.setattr(S.Ctx, "feat", spy)
    monkeypatch.setattr(S.Ctx, "feat_window", window)
    return READS


def run(cls, params, day, rolls, tape=None, feats=None):
    READS.clear()
    st = cls(params)
    st.ROLLS = rolls
    window = S.effective_session_window(day["d"], tuple(cls.session_window))
    res = S.run_session(st, tape or day["tape"], S.Costs(strict_limit=issubclass(cls, W.WallBounce)), daily=day["prior"],
                        features=feats or day["feats"], window=window, on_error="raise")
    assert res.skip is None and res.both_sides is False
    assert not any(t["oco"] or t["both_sides"] for t in res.trades)
    return st, res.trades, list(READS)


# ---- cut: garbage after it ------------------------------------------------------------------------------------------
def garbage(tape, feats, cut, seed):
    """Prints with ts >= cut and rows with usable_ns > cut replaced by garbage (other times, other prices, other books)."""
    g = np.random.default_rng(seed)
    keep = int(np.searchsorted(tape.ts, cut, side="left"))
    end = max(int(tape.ts[-1]), cut + 3600 * NS)
    n_tail = max(len(tape.ts) - keep, 5000)
    ts_tail = np.sort(g.integers(cut, end + 1, size=n_tail))
    ts_tail[0] = cut                                         # a garbage print exactly AT the cut
    base = float(tape.px[keep - 1]) if keep else float(tape.px[0])
    px_tail = np.maximum(base + TICK * np.cumsum(g.integers(-6, 7, size=n_tail)), 100.0)
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
        w = v.copy()
        if k != "t_utc":
            w[:-1] = v[1:]
        cols[k] = w
    return S.Features(feats.usable_ns.copy(), cols)


def eqv(a, b):
    return (a != a and b != b) if isinstance(a, float) and isinstance(b, float) and a != a else a == b


def same_rows(xs, ys):
    return len(xs) == len(ys) and all(len(x) == len(y) and all(eqv(p, q) for p, q in zip(x, y)) for x, y in zip(xs, ys))


def callkey(c):
    return tuple(c[k] for k in ("t", "kind", "side", "px", "struct", "ttl", "placed", "o_px", "o_sl", "o_tp"))


ENTRY = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ns", "entry_ms", "oco")


def violated(base, other, cut):
    """The invariants broken by a replacement after `cut` (empty = everything up to the cut is identical)."""
    (sa, ta, ra), (sb, tb, rb) = base, other
    bad = []
    if not same_rows([x for x in sa.seen if x[0] <= cut], [x for x in sb.seen if x[0] <= cut]):
        bad.append("decisions")
    if not same_rows([callkey(c) for c in sa.calls if c["t"] <= cut], [callkey(c) for c in sb.calls if c["t"] <= cut]):
        bad.append("orders")
    if not same_rows([r for r in ra if r[0] <= cut], [r for r in rb if r[0] <= cut]):
        bad.append("reads")
    closed = lambda ts: [{k: v for k, v in t.items() if k != "both_sides"} for t in ts if t["exit_ns"] < cut]
    if closed(ta) != closed(tb):
        bad.append("closed_trades")
    opened = lambda ts: sorted(tuple(t[k] for k in ENTRY) for t in ts if t["entry_ns"] < cut)
    if opened(ta) != opened(tb):
        bad.append("entries")
    return bad


def cuts_for(d, st, trades, seed):
    """<= 7 cuts: a minute boundary, an instant inside a minute, around one signal, around one trade."""
    g = np.random.default_rng(seed)
    t0 = S.et_ns(d, "00:00")
    out = {t0 + int(g.integers(20, 950)) * MIN, t0 + int(g.integers(20, 950)) * MIN + int(g.integers(1, 60 * NS))}
    if st.calls:
        t = int(g.choice([c["t"] for c in st.calls]))
        out.update((t, t - 1, t + LIVE))                     # at / just before a signal, when its order goes live
    if trades:
        tr = trades[int(g.integers(len(trades)))]
        out.update((tr["entry_ns"], tr["exit_ns"] + 1))
    return sorted(out)


# ---- oracle (raw parquet + raw cache, no ctx) -----------------------------------------------------------------------
def atr_series(ts, px, lo_ns, hi_ns, tf):
    """Own Wilder ATR(14) over the tf bars built from the prints of [00:00 ET, window end): (bar end ns, ATR once that
    bar is closed, bars closed). Bars only for buckets that have a print."""
    step = tf * MIN
    a, b = np.searchsorted(ts, [lo_ns, hi_ns], side="left")
    k, seg = ts[a:b] // step, px[a:b]
    st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
    en = np.concatenate((st[1:], [len(k)]))
    h, l, c = np.maximum.reduceat(seg, st), np.minimum.reduceat(seg, st), seg[en - 1]
    atrs, trs, atr = [], [], None
    for n in range(len(st)):
        tr = h[n] - l[n] if n == 0 else max(h[n] - l[n], abs(h[n] - c[n - 1]), abs(l[n] - c[n - 1]))
        if n < 14:
            trs.append(tr)
            atr = sum(trs) / (n + 1)
        else:
            atr = (atr * 13.0 + tr) / 14.0
        atrs.append(float(atr))
    return (k[st] + 1) * step, np.array(atrs), np.arange(1, len(st) + 1)


def side_of(df, i, s, m):
    px, dist, sz, med = (float(df[c][i]) for c in W.COLS[s])
    if not bool(df["book_ok"][i]) or not all(map(math.isfinite, (px, dist, sz, med))) or med <= 0:
        return None
    return round(px / TICK + (-dist if s == "bid" else dist)), sz >= m * med


def oracle(kind, df, row, now, last, atr, p):
    """The definition (FAMILIES.md "Walls" + addendum) straight from the raw arrays -> the expected order, or None."""
    lt, hits = round(last / TICK), []
    if kind == "limit":
        i = row.get(now)
        for s, sd in (("bid", 1), ("ask", -1)):
            w = side_of(df, i, s, p["m"]) if i is not None else None
            if w and w[1] and 1 <= sd * (lt - w[0]) <= p["near"]:
                hits.append((sd, (w[0] + sd) * TICK, (w[0] - 4 * sd) * TICK))
    else:
        idx = [row.get(now - k * MIN) for k in range(p["stand"] + 1)]
        if None not in idx:
            for s, sd in (("bid", -1), ("ask", 1)):
                new, old = side_of(df, idx[0], s, p["m"]), [side_of(df, i, s, p["m"]) for i in idx[1:]]
                if any(o is None or not o[1] for o in old) or len({o[0] for o in old}) != 1 or new is None:
                    continue
                w = old[0][0]
                if not (new[0] == w and new[1]) and sd * (lt - w) > 0:
                    hits.append((sd, (lt + sd) * TICK, (w - 4 * sd) * TICK))
    if len(hits) != 1:
        return None
    sd, px, struct = hits[0]
    dist = max(abs(px - struct), 0.25 * atr, 2 * TICK)
    return ("long" if sd > 0 else "short", px, struct, True, S.to_tick(px - sd * dist, TICK), S.to_tick(px + sd * 2.0 * dist, TICK))


def check_fills(st, trades, ts, px, kind, hi_ns):
    """Every placed order: its fill (or no fill) re-derived from the raw tape between decision + 85 ms and its cancel."""
    by_entry = {t["entry_ns"]: t for t in trades}
    n_fill = 0
    for r in st.recs:
        o, t = r["o"], r["t"]
        a = int(np.searchsorted(ts, t + LIVE, side="left"))
        stop = r["cancel"] if r["cancel"] is not None else hi_ns
        seg = px[a:int(np.searchsorted(ts, stop, side="left"))]
        if kind == "limit":                                  # a 1-tick trade-through: a print AT the limit never fills
            hit = np.flatnonzero(seg <= o.price - TICK + 1e-9) if o.side > 0 else np.flatnonzero(seg >= o.price + TICK - 1e-9)
        else:
            hit = np.flatnonzero(seg >= o.price - 1e-9) if o.side > 0 else np.flatnonzero(seg <= o.price + 1e-9)
        if o.status == "filled":
            assert len(hit), ("filled without a trigger print in its life", t)
            k = a + int(hit[0])
            tr = by_entry.get(int(ts[k]))
            assert tr is not None and int(ts[k]) >= t + LIVE, ("fill print is not the first trigger after the decision", t)
            want = o.price if kind == "limit" else (max(o.price, px[k]) + TICK) if o.side > 0 else (min(o.price, px[k]) - TICK)
            assert tr["entry_price"] == want, (tr["entry_price"], want)
            n_fill += 1
        else:
            assert o.status == "cancelled" and stop > t and not len(hit), ("an unfilled order had a trigger print", t)
    assert n_fill == len(trades), (n_fill, len(trades))
    return n_fill


# ---- the tests ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cls,kind", [(Bounce, "limit"), (Break, "stop")], ids=["wall_bounce", "wall_break"])
def test_real_days_oracle_and_garbage_after_a_cut(cls, kind, real, reads):
    n = {"decisions": 0, "calls": 0, "fills": 0, "cuts": 0, "post_cut_differs": 0, "late_closes": 0}
    gaps = set()
    for day in real["days"]:
        d, rts, rpx = day["d"], day["rts"], day["rpx"]
        lo_ns = S.et_ns(d, "00:00")
        hi_ns = S.et_ns(d, S.effective_session_window(d, tuple(cls.session_window))[1])
        for tf, extra in CONFIGS:
            params = {"tf": tf, **extra}
            base = st, trades, rd = run(cls, params, day, real["rolls"])
            assert all(now % MIN == 0 and b in (0, 1, 2) for now, _, b, _ in rd)           # minute boundaries, newest rows
            n["late_closes"] += sum(1 for x in st.seen if x[0] % (int(tf) * MIN) != 0)
            # -- oracle: last price, ATR, order request and brackets at every decision; then every fill
            ends, atrs, bars = atr_series(rts, rpx, lo_ns, hi_ns, int(tf))
            calls = {c["t"]: c for c in st.calls}
            assert len(calls) == len(st.calls)                                             # at most one request per decision
            for now, last, atr, nb in st.seen:
                i = int(np.searchsorted(rts, now, side="left"))
                assert i > 0 and lo_ns <= rts[i - 1] < now and float(rpx[i - 1]) == last   # the last print strictly before
                j = int(np.searchsorted(ends, now, side="right")) - 1
                assert j >= 0 and int(bars[j]) == nb and abs(float(atrs[j]) - atr) < 1e-9
                c = calls.get(now)
                got = None if c is None else (c["side"], c["px"], c["struct"], c["placed"], c["o_sl"], c["o_tp"])
                assert got == oracle(kind, day["df"], day["row"], now, last, float(atrs[j]), st.p), (day["iso"], tf, extra, now)
                if c is not None:
                    gaps.add(round((last - c["px"]) * (1 if c["side"] == "long" else -1) / TICK))
            n["decisions"] += len(st.seen)
            n["calls"] += len(st.calls)
            n["fills"] += check_fills(st, trades, rts, rpx, kind, hi_ns)
            for tr in trades:                                                              # an entry never precedes its order
                assert tr["entry_ns"] >= max(c["t"] for c in st.calls if c["placed"] and c["t"] < tr["entry_ns"]) + LIVE
            # -- cut: nothing at / after it can change anything before it
            seed = zlib.crc32(repr((day["iso"], cls.__name__, tf, sorted(extra.items()))).encode())
            for k, cut in enumerate(cuts_for(d, st, trades, seed)):
                t2, f2 = garbage(day["tape"], day["feats"], cut, seed=k + 17)
                other = run(cls, params, day, real["rolls"], t2, f2)
                assert violated(base, other, cut) == [], (day["iso"], tf, extra, (cut - lo_ns) / MIN)
                n["cuts"] += 1
                n["post_cut_differs"] += ([callkey(c) for c in st.calls if c["t"] > cut]
                                          != [callkey(c) for c in other[0].calls if c["t"] > cut])
    assert n["decisions"] > 15000 and n["calls"] >= 20 and n["fills"] >= 10 and n["cuts"] >= 150     # not vacuous
    assert n["post_cut_differs"] >= n["cuts"] // 3                                         # the garbage does matter after
    assert gaps == ({0, 1} if kind == "limit" else {-1})     # B4: the 1-tick (limit AT the last print) and the 2-tick case


@pytest.mark.parametrize("cls", [Bounce, Break], ids=["wall_bounce", "wall_break"])
def test_real_days_a_one_minute_leak_in_the_table_fails_the_cut_comparison(cls, real, reads):
    """Power: with row M carrying minute M + 1's book, a cut AT a decision that reads the newest row must be caught."""
    eligible = caught = 0
    for day in real["days"]:
        lk = leak_values(day["feats"])
        params = {"tf": "1", **BUSY}
        base = run(cls, params, day, real["rolls"], feats=lk)
        newest = sorted({now for now, name, back, _ in base[2] if back == 0 and name not in ("t_utc", "book_ok")})
        for k, cut in enumerate(newest[len(newest) // 3::max(1, len(newest) // 3)][:2]):   # two such decisions a day
            t2, f2 = garbage(day["tape"], day["feats"], cut, seed=k + 5)
            eligible += 1
            caught += bool(violated(base, run(cls, params, day, real["rolls"], t2, leak_values(f2)), cut))
    assert eligible >= 10 and caught == eligible
