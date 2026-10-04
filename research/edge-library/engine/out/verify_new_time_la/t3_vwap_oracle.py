"""ADVERSARIAL VERIFIER, vwap_ema_x: a from-scratch oracle (raw prints -> 1-minute bars -> tf bars -> EMA(n), session / rth VWAP
-> crosses -> the trades a flat, max_tr-3, one-position-at-a-time instance must take), compared with the simulator's trades as a
COMPLETE SET (entry instant + side): no extra trade, no missing trade. The simulator's own exit instants are used only to
know when the instance was flat again. Every quantity the oracle uses at a decision comes from prints strictly before it.
Then a garbage test: all prints at / after a cut are replaced, entries decided before the cut must be identical.
Entry timing / side only: no P&L. BUILD days, <= 10 days, 1 process."""
import sys
import datetime as dt

sys.dont_write_bytecode = True
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine")
import numpy as np  # noqa: E402
import l2sim as S  # noqa: E402
import families  # noqa: E402
from families import timed as T  # noqa: E402
from t1_straddle_oracle import wall  # noqa: E402

NS = 10**9
MIN = 60 * NS
# session windows, ET seconds from 00:00 of the trade date (EDGE_SPEC "PROPER RE-RUN" 5 + the tester's five)
WIN = {"eve": (-6 * 3600, -60), "asia": (0, 3 * 3600), "london": (3 * 3600, 8 * 3600 + 25 * 60), "pre": (8 * 3600 + 25 * 60, 9 * 3600 + 30 * 60),
       "nyam": (9 * 3600 + 30 * 60, 11 * 3600), "mid": (11 * 3600, 13 * 3600 + 30 * 60), "pm": (13 * 3600 + 30 * 60, 15 * 3600 + 58 * 60)}
REAL_LOAD = S.load_tape


def oracle(tape, root, tf, n, anchor, sess, sim_trades):
    """-> (expected [(entry_ns, side)], n_crosses). sim_trades: this session's simulator trades (entry_ns, exit_ns, side)."""
    d = tape.date
    mid = wall(d, "00:00", False)
    eve = sess == "eve"
    if eve:
        w0, w1 = wall(d, "18:00", True), mid
    else:
        half = root in ("NQ", "ES") and d in S.EARLY_CLOSES
        w0, w1 = mid, wall(d, "13:15" if half else "16:10", False)
    a, b = np.searchsorted(tape.ts, [w0, w1])
    ts, px, sz = tape.ts[a:b], tape.px[a:b], tape.size[a:b].astype(float)
    s0, s1 = WIN[sess]
    a0 = WIN["nyam"][0] if (anchor == "rth" and sess in ("nyam", "mid", "pm")) else s0
    minute = (ts - mid) // MIN                                   # minute index relative to 00:00 ET (negative in the evening)
    um, first = np.unique(minute, return_index=True)
    last = np.r_[first[1:], len(minute)] - 1
    mh, ml = np.maximum.reduceat(px, first), np.minimum.reduceat(px, first)
    mc, mv = px[last], np.add.reduceat(sz, first)
    mtyp = (mh + ml + mc) / 3.0
    # tf bars: a bar is "seen" (closed) at the END instant of its last minute if that minute is the bucket's last one,
    # otherwise at the end instant of the first later minute that has a print (it closes before that minute is counted)
    alpha = 2.0 / (n + 1)
    ema, nb, side_prev, n_ent, exp, n_cross = None, 0, 0, 0, [], 0
    sim = sorted(sim_trades)
    open_until = -1                                              # exit instant of the last matched trade
    buckets = um // tf
    order = np.unique(buckets)
    for bk in order.tolist():
        idx = np.flatnonzero(buckets == bk)
        j = int(idx[-1])
        close_px = float(mc[j])
        nominal_end_min = (bk + 1) * tf
        if int(um[j]) == nominal_end_min - 1:
            dec = mid + nominal_end_min * MIN
        elif j + 1 < len(um):
            dec = mid + (int(um[j + 1]) + 1) * MIN
        else:
            dec = None
        if dec is None or dec >= w1:
            continue                                             # an event at / after the window end never fires
        ema = close_px if ema is None else ema + alpha * (close_px - ema)
        nb += 1
        end_s = nominal_end_min * 60
        # the session is active from its start instant up to (and including the bar event AT) its end instant
        active = mid + s0 * NS < dec <= mid + s1 * NS
        if not (s0 < end_s <= s1 and active):
            continue
        sel = (um * 60 >= a0) & (um * 60 < s1) & (um <= um[j])
        vol = float(mv[sel].sum())
        if vol <= 0:
            continue
        vwap = float((mv[sel] * mtyp[sel]).sum()) / vol
        sd = (ema > vwap) - (ema < vwap)
        if sd == 0:
            continue
        crossed = side_prev != 0 and sd != side_prev
        side_prev = sd
        if not crossed:
            continue
        n_cross += 1
        if nb < 3 or dec - mid >= (s1 - 300) * NS or n_ent >= 3 or open_until >= dec:
            continue
        k = int(np.searchsorted(tape.ts, dec + 85 * 10**6))
        if k >= b:
            continue
        ent = int(tape.ts[k])
        exp.append((ent, "long" if sd > 0 else "short"))
        n_ent += 1
        m = [t for t in sim if t[0] == ent]
        open_until = m[0][1] if m else 2**62                     # an expected trade the simulator does not have: stop expecting more
    return exp, n_cross


def run(root, days, combos):
    specs = [(T.VwapEmaX, {"tf": str(tf), "n": n, "anchor": an, "sess": s, **ex}) for tf, n, an, ex in combos for s in ("all", "pre", "eve")]
    res = S.run_many(specs, days=days, root=root, workers=1, keep_ns=True)
    assert all(r["skipped_by_error"] == 0 for r in res)
    return specs, res


def main(root, days):
    menu = S.menu(root)
    combos = [(1, 9, "session", menu[0]), (1, 21, "rth", menu[13]), (1, 50, "session", menu[30]), (5, 9, "rth", menu[7]), (5, 21, "session", menu[18]),
              (5, 50, "rth", menu[25]), (15, 9, "session", menu[4]), (15, 21, "rth", menu[21]), (15, 50, "rth", menu[10])]
    specs, res = run(root, days, combos)
    tapes = {iso: REAL_LOAD(iso, root) for iso in days}
    bad, n_tr, n_exp, n_cross, per_sess = [], 0, 0, 0, {}
    for (cls, p), r in zip(specs, res):
        skipped = {s["date"] for s in r["skipped"]}
        eve_sk = {s["date"] for s in r.get("eve_skipped", [])}
        sessions = ["asia", "london", "nyam", "mid", "pm"] if p["sess"] == "all" else [p["sess"]]
        seen = 0
        for iso in days:
            tp = tapes[iso]
            for sess in sessions:
                mine = [(t["entry_ns"], t["exit_ns"], t["side"]) for t in r["trades"] if t["date"] == iso and S.session_of(t["entry_ms"]) == sess]
                seen += len(mine)
                if (sess == "eve" and iso in eve_sk) or (sess != "eve" and iso in skipped):
                    if mine:
                        bad.append((root, iso, sess, "trades on a skipped session"))
                    continue
                exp, nc = oracle(tp, root, int(p["tf"]), p["n"], p["anchor"], sess, mine)
                n_cross += nc
                n_exp += len(exp)
                n_tr += len(mine)
                per_sess[sess] = per_sess.get(sess, 0) + len(mine)
                if sorted((a, s) for a, _, s in mine) != sorted(exp):
                    bad.append((root, iso, sess, p["tf"], p["n"], p["anchor"], "sim", [(a, s) for a, _, s in mine][:4], "oracle", exp[:4]))
        if seen != len(r["trades"]):
            bad.append((root, p, "trades outside the instance's sessions / days", seen, len(r["trades"])))
    print(f"{root} oracle: days={len(days)} specs={len(specs)} sim trades={n_tr} oracle trades={n_exp} crosses seen={n_cross} per session={per_sess} MISMATCHES={len(bad)}")
    for x in bad[:12]:
        print("  BAD", x)
    # ---- garbage at / after a cut: entries decided before the cut are identical
    rng = np.random.default_rng(5)
    cuts = ("19:07", "22:41", "00:33", "02:16", "04:52", "08:27", "08:44", "09:30", "09:47", "10:58", "11:00", "12:13", "13:30", "14:59")
    nb, chk = 0, 0
    base = {i: [(t["date"], t["entry_ns"], t["side"], t["entry_price"], t["sl"], t["tp"]) for t in r["trades"]] for i, r in enumerate(res)}
    for cut in cuts:
        fake, cns = {}, {}
        for iso in days:
            d = dt.date.fromisoformat(iso)
            tp = tapes[iso]
            c = wall(d, cut, cut >= "18:00")
            k = int(np.searchsorted(tp.ts, c))
            px, sz = tp.px.copy(), tp.size.copy()
            tick = S.SPECS[root][1]
            px[k:] = np.round(tp.px[k:] * rng.uniform(0.7, 1.3, len(px) - k) / tick) * tick
            sz[k:] = rng.integers(1, 300, len(sz) - k)
            fake[iso], cns[iso] = S.Tape(root, d, tp.contract, tp.ts, px, sz), c
        S.load_tape = lambda dd, r=root, **kw: fake[S._date(dd).isoformat()]      # noqa: E731
        try:
            _, g = run(root, days, combos)
        finally:
            S.load_tape = REAL_LOAD
        for i, r in enumerate(g):
            got = [(t["date"], t["entry_ns"], t["side"], t["entry_price"], t["sl"], t["tp"]) for t in r["trades"]]
            # an entry is decided >= 85 ms before its fill print: compare every entry whose fill print is before the cut
            a = sorted(x for x in base[i] if x[1] < cns[x[0]])
            b = sorted(x for x in got if x[1] < cns[x[0]])
            chk += len(a)
            if a != b:
                nb += 1
                bad.append((root, cut, specs[i][1], "entries before the cut changed", len(a), len(b)))
    print(f"{root} garbage: cuts={len(cuts)} entries compared={chk} MISMATCHES={nb}")
    return bad


if __name__ == "__main__":
    root, days = sys.argv[1], sys.argv[2].split(",")
    assert len(days) <= 10 and all(S.BUILD[0] <= dt.date.fromisoformat(x) <= S.BUILD[1] for x in days)
    sys.exit(1 if main(root, days) else 0)
